from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.crm.models import Deal, Lead
from app.modules.finance.models import Invoice, Payment
from app.modules.hr.models import Employee
from app.modules.identity.models import AuditLog, User
from app.modules.inventory.models import Product, StockMove
from app.modules.procurement.models import VendorInvoice
from app.modules.projects.models import Project
from app.modules.sales.models import SalesOrder
from app.modules.support.models import Ticket


def _scope(stmt, model, user: User):
    if hasattr(model, "tenant_id") and not user.is_superuser and user.tenant_id:
        stmt = stmt.where(model.tenant_id == user.tenant_id)
    return stmt


async def _scalar(db: AsyncSession, stmt, default=0):
    value = await db.scalar(stmt)
    return value if value is not None else default


async def dashboard_payload(db: AsyncSession, user: User) -> dict[str, Any]:
    revenue_invoice = await _scalar(
        db,
        _scope(
            select(func.coalesce(func.sum(Invoice.total), 0)).where(
                Invoice.status.in_(("sent", "partially_paid", "paid", "overdue")),
                Invoice.is_active.is_(True),
            ),
            Invoice,
            user,
        ),
    )
    receivables = await _scalar(
        db,
        _scope(
            select(func.coalesce(func.sum(Invoice.total - Invoice.amount_paid), 0)).where(
                Invoice.status.in_(("sent", "partially_paid", "overdue")),
                Invoice.is_active.is_(True),
            ),
            Invoice,
            user,
        ),
    )
    payables = await _scalar(
        db,
        _scope(
            select(
                func.coalesce(func.sum(VendorInvoice.amount + VendorInvoice.tax_amount), 0)
            ).where(VendorInvoice.status.notin_(("paid", "rejected")), VendorInvoice.is_active.is_(True)),
            VendorInvoice,
            user,
        ),
    )
    cash_collected = await _scalar(
        db,
        _scope(select(func.coalesce(func.sum(Payment.amount), 0)), Payment, user),
    )
    pipeline_value = await _scalar(
        db,
        _scope(
            select(func.coalesce(func.sum(Deal.amount), 0)).where(
                Deal.stage.notin_(("won", "lost")), Deal.is_active.is_(True)
            ),
            Deal,
            user,
        ),
    )

    on_hand_subq = select(
        Product.id.label("product_id"),
        func.coalesce(func.sum(StockMove.quantity), 0).label("on_hand"),
        Product.purchase_price.label("purchase_price"),
        Product.reorder_level.label("reorder_level"),
    )
    if not user.is_superuser and user.tenant_id:
        on_hand_subq = on_hand_subq.where(Product.tenant_id == user.tenant_id)
    on_hand_subq = on_hand_subq.outerjoin(
        StockMove,
        (StockMove.product_id == Product.id) & (StockMove.status == "posted"),
    ).group_by(
        Product.id, Product.purchase_price, Product.reorder_level
    )
    stock_subq = on_hand_subq.subquery()
    stock_value = await _scalar(
        db,
        select(func.coalesce(func.sum(stock_subq.c.on_hand * stock_subq.c.purchase_price), 0)),
    )
    low_stock = await _scalar(
        db,
        select(func.count()).select_from(stock_subq).where(
            stock_subq.c.on_hand <= stock_subq.c.reorder_level
        ),
    )

    lead_count = await _scalar(
        db,
        _scope(
            select(func.count()).select_from(Lead).where(
                Lead.status.notin_(("won", "lost")), Lead.is_active.is_(True)
            ),
            Lead,
            user,
        ),
    )
    open_deals = await _scalar(
        db,
        _scope(
            select(func.count()).select_from(Deal).where(
                Deal.stage.notin_(("won", "lost")), Deal.is_active.is_(True)
            ),
            Deal,
            user,
        ),
    )
    open_tickets = await _scalar(
        db,
        _scope(
            select(func.count()).select_from(Ticket).where(
                Ticket.status.in_(("open", "pending")), Ticket.is_active.is_(True)
            ),
            Ticket,
            user,
        ),
    )
    active_projects = await _scalar(
        db,
        _scope(
            select(func.count()).select_from(Project).where(
                Project.status.in_(("active", "planning")), Project.is_active.is_(True)
            ),
            Project,
            user,
        ),
    )
    employee_count = await _scalar(
        db,
        _scope(
            select(func.count()).select_from(Employee).where(
                Employee.status == "active", Employee.is_active.is_(True)
            ),
            Employee,
            user,
        ),
    )

    today = date.today()
    months: list[str] = []
    year, month = today.year, today.month
    for _ in range(6):
        months.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            month = 12
            year -= 1
    months.reverse()

    trend: dict[str, dict[str, Any]] = {
        key: {"month": key, "revenue": Decimal("0"), "orders": 0} for key in months
    }
    invoice_stmt = select(Invoice.issue_date, Invoice.total).where(
        Invoice.status.in_(("sent", "partially_paid", "paid", "overdue")), Invoice.is_active.is_(True)
    )
    invoice_stmt = _scope(invoice_stmt, Invoice, user)
    for issue_date, total in (await db.execute(invoice_stmt)).all():
        key = issue_date.strftime("%Y-%m")
        if key in trend:
            trend[key]["revenue"] += Decimal(total or 0)
    order_stmt = select(SalesOrder.order_date, SalesOrder.total).where(SalesOrder.is_active.is_(True))
    order_stmt = _scope(order_stmt, SalesOrder, user)
    for order_date, _total in (await db.execute(order_stmt)).all():
        key = order_date.strftime("%Y-%m")
        if key in trend:
            trend[key]["orders"] += 1

    stage_stmt = select(Deal.stage, func.count(), func.coalesce(func.sum(Deal.amount), 0)).where(
        Deal.is_active.is_(True)
    )
    stage_stmt = _scope(stage_stmt, Deal, user).group_by(Deal.stage)
    pipeline = [
        {"stage": row[0], "count": int(row[1]), "amount": Decimal(row[2] or 0)}
        for row in (await db.execute(stage_stmt)).all()
    ]

    channel_stmt = select(
        SalesOrder.channel, func.count(), func.coalesce(func.sum(SalesOrder.total), 0)
    ).where(SalesOrder.is_active.is_(True))
    channel_stmt = _scope(channel_stmt, SalesOrder, user).group_by(SalesOrder.channel)
    channels = [
        {"channel": row[0], "orders": int(row[1]), "revenue": Decimal(row[2] or 0)}
        for row in (await db.execute(channel_stmt)).all()
    ]

    activity_stmt = select(AuditLog).order_by(AuditLog.created_at.desc()).limit(8)
    if not user.is_superuser and user.tenant_id:
        activity_stmt = activity_stmt.where(AuditLog.tenant_id == user.tenant_id)
    activity = list((await db.scalars(activity_stmt)).all())

    return {
        "kpis": {
            "revenue": Decimal(str(revenue_invoice or 0)),
            "receivables": Decimal(str(receivables or 0)),
            "payables": Decimal(str(payables or 0)),
            "cash_collected": Decimal(str(cash_collected or 0)),
            "pipeline_value": Decimal(str(pipeline_value or 0)),
            "stock_value": Decimal(str(stock_value or 0)),
            "lead_count": int(lead_count or 0),
            "open_deals": int(open_deals or 0),
            "low_stock_count": int(low_stock or 0),
            "open_tickets": int(open_tickets or 0),
            "active_projects": int(active_projects or 0),
            "employee_count": int(employee_count or 0),
        },
        "revenue_trend": list(trend.values()),
        "pipeline": pipeline,
        "channels": channels,
        "recent_activity": [
            {
                "id": log.id,
                "actor_email": log.actor_email,
                "action": log.action,
                "module": log.module,
                "entity": log.entity,
                "entity_id": log.entity_id,
                "created_at": log.created_at,
            }
            for log in activity
        ],
    }
