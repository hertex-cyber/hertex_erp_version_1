from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.events import publish
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.support.models import Ticket, TicketMessage
from app.modules.support.schemas import (
    TicketCreate,
    TicketMessageCreate,
    TicketMessageRead,
    TicketRead,
    TicketUpdate,
)

router = APIRouter(prefix="/support")


def _include(**kwargs):
    child, _ = build_crud_router(module="support", **kwargs)
    router.include_router(child)


_include(
    model=Ticket,
    read_schema=TicketRead,
    create_schema=TicketCreate,
    update_schema=TicketUpdate,
    prefix="/tickets",
    tags=["Support · Tickets"],
    permission_prefix="support.ticket",
    entity="Ticket",
    search_fields=("ticket_number", "subject", "requester_name", "requester_email"),
    filter_fields=("status", "priority", "channel", "assignee_id", "customer_id"),
    load_options=(selectinload(Ticket.messages),),
    number_field="ticket_number",
    number_prefix="TKT",
)


@router.post(
    "/tickets/{ticket_id}/messages",
    response_model=TicketMessageRead,
    status_code=201,
    tags=["Support · Tickets"],
)
async def add_message(
    ticket_id: UUID,
    payload: TicketMessageCreate,
    request: Request,
    user: User = Depends(require_permissions("support.ticketmessage.create")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    ticket = await db.scalar(stmt)
    if ticket is None:
        raise NotFoundError("Ticket not found")
    if not user.is_superuser and ticket.tenant_id != user.tenant_id:
        raise NotFoundError("Ticket not found")
    message = TicketMessage(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        ticket_id=ticket.id,
        author_id=user.id,
        author_name=user.full_name,
        body=payload.body,
        is_internal=payload.is_internal,
        channel=payload.channel,
    )
    db.add(message)
    if ticket.status == "resolved" and not payload.is_internal:
        ticket.status = "open"
        ticket.resolved_at = None
    await record_audit(
        db,
        user=user,
        action="reply",
        module="support",
        entity="Ticket",
        entity_id=ticket.id,
        request=request,
    )
    await db.commit()
    await db.refresh(message)
    await publish("ticket.message.created", {"ticket_id": str(ticket.id), "message_id": str(message.id)})
    return message


@router.post("/tickets/{ticket_id}/resolve", response_model=TicketRead, tags=["Support · Tickets"])
async def resolve_ticket(
    ticket_id: UUID,
    request: Request,
    user: User = Depends(require_permissions("support.ticket.update")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Ticket).options(selectinload(Ticket.messages)).where(Ticket.id == ticket_id)
    ticket = await db.scalar(stmt)
    if ticket is None:
        raise NotFoundError("Ticket not found")
    if not user.is_superuser and ticket.tenant_id != user.tenant_id:
        raise NotFoundError("Ticket not found")
    ticket.status = "resolved"
    ticket.resolved_at = datetime.now(timezone.utc)
    await record_audit(
        db,
        user=user,
        action="resolve",
        module="support",
        entity="Ticket",
        entity_id=ticket.id,
        request=request,
    )
    await db.commit()
    await db.refresh(ticket)
    return ticket
