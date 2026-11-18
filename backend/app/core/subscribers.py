"""Domain-event subscribers registered at application startup."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.events import subscribe
from app.db.session import AsyncSessionLocal

logger = logging.getLogger("hertex.events")


def _phone_digits(value: str | None) -> str:
    return "".join(char for char in (value or "") if char.isdigit())


def _uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


@subscribe("channel_message.received")
async def link_inbound_messages(payload: dict[str, Any]) -> None:
    from app.modules.crm.models import Lead
    from app.modules.integrations.models import ChannelMessage

    try:
        message_ids = [UUID(str(value)) for value in payload.get("message_ids") or []]
    except ValueError:
        return
    if not message_ids:
        return

    async with AsyncSessionLocal() as db:
        messages = (
            await db.scalars(
                select(ChannelMessage).where(
                    ChannelMessage.id.in_(message_ids),
                    ChannelMessage.direction == "inbound",
                )
            )
        ).all()
        linked = 0
        for message in messages:
            target = _phone_digits(message.contact_phone)
            if not target:
                continue
            leads = (
                await db.scalars(
                    select(Lead).where(
                        Lead.phone.is_not(None), Lead.is_active.is_(True)
                    )
                )
            ).all()
            lead = next(
                (item for item in leads if _phone_digits(item.phone) == target), None
            )
            if lead is None:
                continue
            body = (message.payload or {}).get("text", {}).get("body", "")
            note = f"WhatsApp received: {body[:200]}".strip()
            lead.notes = f"{lead.notes}\n{note}" if lead.notes else note
            if lead.status == "new":
                lead.status = "contacted"
            message.module = "crm"
            message.related_id = lead.id
            linked += 1
        if linked:
            await db.commit()
            logger.info("event.inbound_linked count=%s", linked)


async def _record_project_integration_activity(
    payload: dict[str, Any], *, entity_type: str, entity_key: str, action: str
) -> None:
    from app.modules.projects.models import ProjectActivity

    raw_id = payload.get(entity_key)
    if not raw_id:
        return
    try:
        entity_id = UUID(str(raw_id))
        tenant_id = UUID(str(payload["tenant_id"])) if payload.get("tenant_id") else None
    except (ValueError, TypeError, KeyError):
        return

    async with AsyncSessionLocal() as db:
        existing = select(ProjectActivity.id).where(
            ProjectActivity.entity_type == entity_type,
            ProjectActivity.entity_id == entity_id,
            ProjectActivity.action == action,
        )
        if tenant_id is not None:
            existing = existing.where(ProjectActivity.tenant_id == tenant_id)
        if await db.scalar(existing) is not None:
            return
        db.add(
            ProjectActivity(
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                changes_json={key: value for key, value in payload.items() if key != "tenant_id"},
                correlation_id=payload.get("correlation_id"),
            )
        )
        try:
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.warning("event.project_integration_failed action=%s error=%s", action, exc)


@subscribe("project.started")
async def project_started_integration(payload: dict[str, Any]) -> None:
    await _record_project_integration_activity(
        payload, entity_type="project", entity_key="project_id", action="project.started.integration"
    )


@subscribe("work_item.done")
async def support_project_work_completed(payload: dict[str, Any]) -> None:
    from app.core.events import publish
    from app.modules.projects.models import ProjectActivity
    from app.modules.support.models import Ticket, TicketMessage

    work_item_id = _uuid(payload.get("entity_id"))
    if work_item_id is None:
        return
    async with AsyncSessionLocal() as db:
        tickets = (
            await db.scalars(
                select(Ticket).where(
                    Ticket.project_work_item_id == work_item_id,
                    Ticket.is_active.is_(True),
                )
            )
        ).all()
        notified = False
        for ticket in tickets:
            existing = await db.scalar(
                select(TicketMessage.id).where(
                    TicketMessage.ticket_id == ticket.id,
                    TicketMessage.body.contains(str(work_item_id)),
                )
            )
            if existing is not None:
                continue
            db.add(
                TicketMessage(
                    tenant_id=ticket.tenant_id,
                    author_name="Project Management",
                    body=f"Linked project work item {work_item_id} has been completed.",
                    is_internal=True,
                    channel="system",
                    ticket_id=ticket.id,
                )
            )
            db.add(
                ProjectActivity(
                    tenant_id=ticket.tenant_id,
                    entity_type="ticket",
                    entity_id=ticket.id,
                    action="support.work_item_completed",
                    changes_json={"work_item_id": str(work_item_id), "ticket_id": str(ticket.id)},
                    correlation_id=payload.get("correlation_id"),
                )
            )
            notified = True
            await publish(
                "ticket.project_work_completed",
                {
                    "tenant_id": str(ticket.tenant_id) if ticket.tenant_id else None,
                    "ticket_id": str(ticket.id),
                    "work_item_id": str(work_item_id),
                },
            )
        if notified:
            await db.commit()


@subscribe("billing.posted")
async def billing_posted_integration(payload: dict[str, Any]) -> None:
    await _record_project_integration_activity(
        payload,
        entity_type="billing_run",
        entity_key="billing_run_id",
        action="billing.posted.integration",
    )


@subscribe("po.approved")
async def notify_vendor_of_approval(payload: dict[str, Any]) -> None:
    from app.modules.integrations.service import send_message
    from app.modules.procurement.models import PurchaseOrder

    po_id = payload.get("po_id")
    if not po_id:
        return

    async with AsyncSessionLocal() as db:
        po = await db.scalar(
            select(PurchaseOrder)
            .options(selectinload(PurchaseOrder.vendor))
            .where(PurchaseOrder.id == po_id)
        )
        if po is None or po.vendor is None or not po.vendor.phone:
            return
        body = (
            f"Your purchase order {po.po_number} for {po.total} has been approved "
            f"and is ready for fulfilment."
        )
        try:
            await send_message(
                db,
                tenant_id=po.tenant_id,
                channel="whatsapp",
                to=po.vendor.phone,
                body=body,
                template="purchase_order_approved",
                module="procurement",
                related_id=po.id,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.warning("event.po_notification_failed po=%s error=%s", po.po_number, exc)


async def _once(payload: dict[str, Any], *, entity_type: str, entity_id: str, action: str) -> bool:
    from app.modules.projects.models import ProjectActivity

    try:
        tenant_id = UUID(str(payload["tenant_id"])) if payload.get("tenant_id") else None
        parsed_id = UUID(str(entity_id))
    except (KeyError, TypeError, ValueError):
        return False
    async with AsyncSessionLocal() as db:
        exists = select(ProjectActivity.id).where(
            ProjectActivity.entity_type == entity_type,
            ProjectActivity.entity_id == parsed_id,
            ProjectActivity.action == action,
        )
        if tenant_id is not None:
            exists = exists.where(ProjectActivity.tenant_id == tenant_id)
        if await db.scalar(exists) is not None:
            return False
        db.add(
            ProjectActivity(
                tenant_id=tenant_id,
                entity_type=entity_type,
                entity_id=parsed_id,
                action=action,
                changes_json={key: value for key, value in payload.items() if key != "tenant_id"},
                correlation_id=payload.get("correlation_id"),
            )
        )
        try:
            await db.commit()
            return True
        except Exception as exc:
            await db.rollback()
            logger.warning("event.project_subscriber_failed action=%s error=%s", action, exc)
            return False


@subscribe("invoice.paid")
async def project_invoice_paid(payload: dict[str, Any]) -> None:
    from datetime import datetime, timezone
    from decimal import Decimal

    from app.modules.projects.models import Project, ProjectInvoiceLink

    invoice_id = _uuid(payload.get("invoice_id"))
    if invoice_id is None or not await _once(
        payload,
        entity_type="invoice",
        entity_id=str(invoice_id),
        action="invoice.paid.project",
    ):
        return
    try:
        amount = Decimal(str(payload.get("amount") or 0))
        status = "paid" if payload.get("invoice_status") == "paid" else "partially_paid"
        raw_paid_at = payload.get("paid_at")
        paid_at = datetime.fromisoformat(str(raw_paid_at)) if raw_paid_at else datetime.now(timezone.utc)
    except Exception:
        return
    async with AsyncSessionLocal() as db:
        links = (
            await db.scalars(
                select(ProjectInvoiceLink).where(
                    ProjectInvoiceLink.finance_invoice_id == invoice_id
                )
            )
        ).all()
        for link in links:
            link.status = status
            link.paid_at = paid_at
            project = await db.scalar(
                select(Project).where(Project.id == link.project_id)
            )
            if project is not None:
                project.wip_amount = max(Decimal("0"), (project.wip_amount or Decimal("0")) - amount)
        if links:
            await db.commit()


@subscribe("employee.onboarded")
async def project_employee_onboarded(payload: dict[str, Any]) -> None:
    from datetime import date, timedelta
    from decimal import Decimal

    from app.modules.projects.models import ProjectCapacityCalendar

    employee_id = _uuid(payload.get("employee_id"))
    if employee_id is None or not await _once(
        payload,
        entity_type="employee",
        entity_id=str(employee_id),
        action="employee.onboarded.project",
    ):
        return
    week = date.today() - timedelta(days=date.today().weekday())
    async with AsyncSessionLocal() as db:
        exists = await db.scalar(
            select(ProjectCapacityCalendar.id).where(
                ProjectCapacityCalendar.employee_id == employee_id,
                ProjectCapacityCalendar.week_start == week,
            )
        )
        if exists is None:
            db.add(
                ProjectCapacityCalendar(
                    tenant_id=_uuid(payload.get("tenant_id")),
                    employee_id=employee_id,
                    week_start=week,
                    capacity_hours=Decimal("40"),
                    source="hr",
                )
            )
            await db.commit()


@subscribe("employee.exited")
async def project_employee_exited(payload: dict[str, Any]) -> None:
    from datetime import date

    from app.modules.projects.models import ProjectResourceBooking

    employee_id = _uuid(payload.get("employee_id"))
    if employee_id is None or not await _once(
        payload,
        entity_type="employee",
        entity_id=str(employee_id),
        action="employee.exited.project",
    ):
        return
    try:
        exit_date = date.fromisoformat(str(payload.get("date_of_exit"))[:10])
    except (TypeError, ValueError):
        return
    async with AsyncSessionLocal() as db:
        bookings = (
            await db.scalars(
                select(ProjectResourceBooking).where(
                    ProjectResourceBooking.employee_id == employee_id,
                    ProjectResourceBooking.start_date >= exit_date,
                    ProjectResourceBooking.is_active.is_(True),
                )
            )
        ).all()
        for booking in bookings:
            booking.is_active = False
        if bookings:
            await db.commit()


@subscribe("leave.approved")
async def project_leave_approved(payload: dict[str, Any]) -> None:
    from datetime import date, timedelta
    from decimal import Decimal

    from app.modules.projects.models import ProjectCapacityCalendar, ProjectWorkloadSnapshot

    employee_id = _uuid(payload.get("employee_id"))
    if employee_id is None or not await _once(
        payload,
        entity_type="employee",
        entity_id=str(employee_id),
        action="leave.approved.project",
    ):
        return
    try:
        start = date.fromisoformat(str(payload.get("start_date"))[:10])
        end = date.fromisoformat(str(payload.get("end_date"))[:10])
        hours = Decimal(str(payload.get("hours") or 0))
    except (TypeError, ValueError):
        return
    if end < start:
        end = start
    weeks: list[date] = []
    cursor = start - timedelta(days=start.weekday())
    while cursor <= end:
        weeks.append(cursor)
        cursor += timedelta(days=7)
    if not weeks:
        return
    per_week = hours / Decimal(len(weeks))
    async with AsyncSessionLocal() as db:
        for week in weeks:
            capacity = await db.scalar(
                select(ProjectCapacityCalendar).where(
                    ProjectCapacityCalendar.employee_id == employee_id,
                    ProjectCapacityCalendar.week_start == week,
                )
            )
            if capacity is not None:
                capacity.planned_leave_hours = (
                    capacity.planned_leave_hours or Decimal("0")
                ) + per_week
            workload = await db.scalar(
                select(ProjectWorkloadSnapshot).where(
                    ProjectWorkloadSnapshot.employee_id == employee_id,
                    ProjectWorkloadSnapshot.week_start == week,
                )
            )
            if workload is not None:
                workload.available_hours = max(
                    Decimal("0"), (workload.available_hours or Decimal("0")) - per_week
                )
                workload.overallocated = False
        await db.commit()
