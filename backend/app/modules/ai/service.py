import re
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.analytics.service import dashboard_payload
from app.modules.finance.models import Invoice
from app.modules.identity.models import User
from app.modules.inventory.models import Product, StockMove
from app.modules.support.models import Ticket


def _money(value: Any) -> str:
    return f"{Decimal(str(value or 0)):,.2f}"


def _detect_intent(question: str) -> str:
    q = question.lower()
    if re.search(r"receivable|outstanding|owed|collect|overdue", q):
        return "receivables"
    if re.search(r"low stock|reorder|stock out|inventory", q):
        return "inventory"
    if re.search(r"revenue|sales|income|turnover", q):
        return "revenue"
    if re.search(r"ticket|support|complaint|sla", q):
        return "support"
    if re.search(r"lead|deal|pipeline|crm", q):
        return "pipeline"
    if re.search(r"project|task", q):
        return "projects"
    if re.search(r"payable|vendor|supplier|bill", q):
        return "payables"
    return "overview"


async def _low_stock_rows(db: AsyncSession, user: User, limit: int = 10) -> list[dict[str, Any]]:
    subq = select(
        Product.id.label("product_id"),
        Product.name.label("name"),
        Product.sku.label("sku"),
        Product.reorder_level.label("reorder_level"),
        func.coalesce(func.sum(StockMove.quantity), 0).label("on_hand"),
    )
    if not user.is_superuser and user.tenant_id:
        subq = subq.where(Product.tenant_id == user.tenant_id)
    subq = (
        subq.outerjoin(StockMove, StockMove.product_id == Product.id)
        .group_by(Product.id, Product.name, Product.sku, Product.reorder_level)
        .subquery()
    )
    stmt = (
        select(subq)
        .where(subq.c.on_hand <= subq.c.reorder_level)
        .order_by(subq.c.on_hand.asc())
        .limit(limit)
    )
    return [
        {
            "product": row.name,
            "sku": row.sku,
            "on_hand": int(row.on_hand),
            "reorder_level": int(row.reorder_level),
        }
        for row in (await db.execute(stmt)).all()
    ]


async def _open_invoice_rows(db: AsyncSession, user: User, limit: int = 10) -> list[dict[str, Any]]:
    stmt = select(Invoice).where(
        Invoice.status.in_(("sent", "partially_paid", "overdue")), Invoice.is_active.is_(True)
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Invoice.tenant_id == user.tenant_id)
    stmt = stmt.order_by(Invoice.due_date.asc()).limit(limit)
    rows = list((await db.scalars(stmt)).all())
    today = date.today()
    return [
        {
            "invoice": inv.invoice_number,
            "customer_id": str(inv.customer_id),
            "balance": str((inv.total or 0) - (inv.amount_paid or 0)),
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "overdue": bool(inv.due_date and inv.due_date < today),
        }
        for inv in rows
    ]


async def answer_question(db: AsyncSession, user: User, question: str) -> dict[str, Any]:
    intent = _detect_intent(question)
    dashboard = await dashboard_payload(db, user)
    kpis = dashboard["kpis"]
    data: dict[str, Any] = {}
    suggestions = [
        "Show overdue receivables",
        "Which products need reordering?",
        "Summarise this month's revenue",
    ]

    if intent == "receivables":
        invoices = await _open_invoice_rows(db, user)
        overdue = sum(1 for row in invoices if row["overdue"])
        answer = (
            f"Receivables stand at {_money(kpis['receivables'])} across open invoices. "
            f"{overdue} of the top open invoices are past due."
        )
        data = {"receivables": str(kpis["receivables"]), "invoices": invoices}
        suggestions = ["Draft payment reminders", "List customers with the largest balances"]
    elif intent == "inventory":
        low = await _low_stock_rows(db, user)
        answer = (
            f"{kpis['low_stock_count']} product(s) are at or below their reorder level. "
            f"Estimated stock value is {_money(kpis['stock_value'])}."
        )
        data = {"low_stock_count": kpis["low_stock_count"], "products": low}
        suggestions = ["Create purchase requisitions for low stock", "Show stock value by category"]
    elif intent == "revenue":
        answer = (
            f"Booked revenue is {_money(kpis['revenue'])} with {_money(kpis['cash_collected'])} "
            f"collected so far. The six-month trend is attached."
        )
        data = {"revenue": str(kpis["revenue"]), "trend": dashboard["revenue_trend"]}
        suggestions = ["Compare revenue by channel", "Show the sales pipeline"]
    elif intent == "support":
        answer = f"There are {kpis['open_tickets']} open support tickets right now."
        stmt = select(Ticket).where(Ticket.status.in_(("open", "pending"))).limit(10)
        if not user.is_superuser and user.tenant_id:
            stmt = stmt.where(Ticket.tenant_id == user.tenant_id)
        tickets = list((await db.scalars(stmt.order_by(Ticket.created_at.asc()))).all())
        data = {
            "open_tickets": kpis["open_tickets"],
            "tickets": [
                {"number": t.ticket_number, "subject": t.subject, "priority": t.priority}
                for t in tickets
            ],
        }
        suggestions = ["Show high priority tickets", "Which tickets are breaching SLA?"]
    elif intent == "pipeline":
        answer = (
            f"The pipeline holds {kpis['open_deals']} open deals worth "
            f"{_money(kpis['pipeline_value'])}, fed by {kpis['lead_count']} active leads."
        )
        data = {"deals": kpis["open_deals"], "value": str(kpis["pipeline_value"]), "stages": dashboard["pipeline"]}
        suggestions = ["Show deals closing this month", "List stale leads"]
    elif intent == "projects":
        answer = f"{kpis['active_projects']} projects are active across the organisation."
        data = {"active_projects": kpis["active_projects"]}
        suggestions = ["Show projects behind schedule", "List tasks due this week"]
    elif intent == "payables":
        answer = f"Outstanding vendor payables are {_money(kpis['payables'])}."
        data = {"payables": str(kpis["payables"])}
        suggestions = ["Show bills due this week", "Summarise vendor spend"]
    else:
        answer = (
            f"Revenue is {_money(kpis['revenue'])}, receivables {_money(kpis['receivables'])}, "
            f"pipeline {_money(kpis['pipeline_value'])} and stock value {_money(kpis['stock_value'])}. "
            f"You have {kpis['open_tickets']} open tickets and {kpis['low_stock_count']} low-stock items."
        )
        data = kpis
        suggestions = ["Explain my cash position", "Where should I focus this week?"]

    return {
        "question": question,
        "intent": intent,
        "answer": answer,
        "data": data,
        "suggestions": suggestions,
    }


async def insights(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    kpis = (await dashboard_payload(db, user))["kpis"]
    results: list[dict[str, Any]] = []
    if Decimal(kpis["receivables"]) > 0:
        results.append(
            {
                "severity": "warning",
                "title": "Cash is locked in receivables",
                "detail": f"{_money(kpis['receivables'])} is still outstanding from customers.",
                "metric": "receivables",
                "action": "Review ageing and send payment reminders",
            }
        )
    if kpis["low_stock_count"]:
        results.append(
            {
                "severity": "critical",
                "title": "Replenishment needed",
                "detail": f"{kpis['low_stock_count']} SKUs are at or below reorder level.",
                "metric": "low_stock_count",
                "action": "Raise purchase requisitions",
            }
        )
    if kpis["open_tickets"]:
        results.append(
            {
                "severity": "warning",
                "title": "Support queue is growing",
                "detail": f"{kpis['open_tickets']} tickets are open or pending.",
                "metric": "open_tickets",
                "action": "Triage and assign owners",
            }
        )
    if Decimal(kpis["payables"]) > 0:
        results.append(
            {
                "severity": "info",
                "title": "Vendor obligations",
                "detail": f"{_money(kpis['payables'])} is payable to vendors.",
                "metric": "payables",
                "action": "Schedule payments against cash on hand",
            }
        )
    if not results:
        results.append(
            {
                "severity": "success",
                "title": "All clear",
                "detail": "No urgent operational risks were detected.",
                "metric": "health",
                "action": "Keep monitoring the dashboard",
            }
        )
    return results
