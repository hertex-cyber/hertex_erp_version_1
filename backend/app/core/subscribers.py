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
