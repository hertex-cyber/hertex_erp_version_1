from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.identity.models import User
from app.modules.projects import models as pm
from app.modules.projects.services import enqueue_event, record_activity, sequence_number, utcnow
from app.modules.sales.models import Customer
from app.modules.support.models import Ticket

PROJECT_WORK_TAGS = ("needs_project_work", "#needs_project_work", "[needs_project_work]")


def _priority(ticket: Ticket) -> str:
    priority = (ticket.priority or "medium").lower()
    if priority in ("urgent", "critical"):
        return "critical"
    if priority in ("high",):
        return "high"
    return "medium"


def _customer_context(customer: Customer | None, ticket: Ticket) -> str:
    if customer is not None:
        return f"{customer.name} ({customer.id})"
    if ticket.customer_id is not None:
        return f"Customer {ticket.customer_id}"
    return ticket.requester_name or "Unassigned"


async def _resolve_project(
    db: AsyncSession, user: User, ticket: Ticket, customer: Customer | None
) -> pm.Project:
    stmt = select(pm.Project).where(
        pm.Project.is_active.is_(True),
        pm.Project.status.notin_(("completed", "cancelled")),
    )
    if user.tenant_id:
        stmt = stmt.where(pm.Project.tenant_id == user.tenant_id)
    if customer is not None:
        stmt = stmt.where(pm.Project.customer_id == customer.id)
    else:
        stmt = stmt.where(pm.Project.code == "SUPPORT-GENERAL")
    project = await db.scalar(stmt.order_by(pm.Project.created_at.desc()))
    if project is not None:
        return project
    suffix = customer.id.hex[:8].upper() if customer is not None else ticket.id.hex[:8].upper()
    project = pm.Project(
        tenant_id=ticket.tenant_id or user.tenant_id,
        created_by_id=user.id,
        name=f"Support delivery - {_customer_context(customer, ticket)}",
        code=f"SUP-{suffix}",
        number=await sequence_number(db, user, "project", "SUP"),
        description="Project work arising from support tickets",
        customer_id=customer.id if customer is not None else None,
        client_name=customer.name if customer is not None else ticket.requester_name,
        priority=_priority(ticket),
        status="active",
        state_changed_at=utcnow(),
    )
    db.add(project)
    await db.flush()
    return project


async def ensure_project_work_item(db: AsyncSession, user: User, ticket: Ticket) -> Ticket:
    if ticket.project_work_item_id is not None:
        existing = await db.scalar(
            select(pm.Task).where(
                pm.Task.id == ticket.project_work_item_id,
                pm.Task.is_active.is_(True),
            )
        )
        if existing is not None:
            return ticket
    customer = None
    if ticket.customer_id is not None:
        customer = await db.scalar(
            select(Customer).where(
                Customer.id == ticket.customer_id,
                Customer.is_active.is_(True),
            )
        )
    project = await _resolve_project(db, user, ticket, customer)
    sla = ticket.sla_due_at.isoformat() if ticket.sla_due_at else "not set"
    description = "\n".join(
        [
            f"Support ticket: {ticket.ticket_number} ({ticket.id})",
            f"Customer: {_customer_context(customer, ticket)}",
            f"Requester: {ticket.requester_name or 'not provided'} "
            f"({ticket.requester_email or 'no email'})",
            f"Channel: {ticket.channel}; Priority: {ticket.priority}",
            f"SLA due: {sla}",
            f"Issue: {ticket.description or ticket.subject}",
        ]
    )
    work_item = pm.Task(
        tenant_id=ticket.tenant_id or user.tenant_id,
        created_by_id=user.id,
        project_id=project.id,
        title=f"Support: {ticket.subject}"[:255],
        number=await sequence_number(db, user, "work_item", "PRJ-T"),
        description=description,
        status="todo",
        state_changed_at=utcnow(),
        work_item_type="support",
        priority=_priority(ticket),
        due_date=ticket.sla_due_at.date() if ticket.sla_due_at else None,
    )
    db.add(work_item)
    await db.flush()
    ticket.needs_project_work = True
    ticket.project_work_item_id = work_item.id
    details: dict[str, Any] = {
        "ticket_id": str(ticket.id),
        "ticket_number": ticket.ticket_number,
        "project_id": str(project.id),
        "work_item_id": str(work_item.id),
        "customer_id": str(ticket.customer_id) if ticket.customer_id else None,
        "sla_due_at": sla,
    }
    await record_activity(
        db, user, "work_item", work_item.id, "support.work_item_linked", details
    )
    await enqueue_event(db, user, "support.work_item_created", details)
    await db.commit()
    await publish(
        "support.work_item_created",
        details,
        correlation_id=str(user.id),
    )
    return ticket
