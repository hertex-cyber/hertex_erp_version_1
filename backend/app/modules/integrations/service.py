"""Channel-agnostic conversational bridge.

Business modules call ``send_message`` instead of talking to Meta directly.
WhatsApp is the first adapter; Instagram/Messenger can be added without touching
CRM, Sales or Support code (see the ERP technical plan, Sprint 5).
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError
from app.modules.integrations.adapters import DeliveryResult, WhatsAppCloudAdapter
from app.modules.integrations.models import ChannelMessage

logger = logging.getLogger("hertex.engage_bridge")


def _phone_digits(value: str | None) -> str:
    return "".join(char for char in (value or "") if char.isdigit())


async def _whatsapp_consent(
    db: AsyncSession, tenant_id: UUID | None, to: str
) -> Optional[bool]:
    """Return opt-in state for a known contact/lead, or ``None`` if unknown."""
    from app.modules.crm.models import Contact, Lead

    target = _phone_digits(to)
    if not target:
        return None
    for model in (Contact, Lead):
        stmt = select(model).where(model.phone.is_not(None), model.is_active.is_(True))
        if tenant_id:
            stmt = stmt.where(model.tenant_id == tenant_id)
        for record in (await db.scalars(stmt.limit(1000))).all():
            if _phone_digits(record.phone) == target:
                return bool(record.whatsapp_opt_in)
    return None


async def send_message(
    db: AsyncSession,
    *,
    tenant_id: UUID | None,
    channel: str,
    to: str,
    body: str,
    template: str | None = None,
    module: str | None = None,
    related_id: UUID | None = None,
    payload: dict[str, Any] | None = None,
) -> ChannelMessage:
    consent: Optional[bool] = None
    if channel == "whatsapp":
        consent = await _whatsapp_consent(db, tenant_id, to)
        if consent is False:
            raise ForbiddenError("Recipient has not opted in to WhatsApp messages")

    data = {"body": body, "template": template, **(payload or {})}
    if consent is not None:
        data["consent"] = "opted_in" if consent else "unknown"
    message = ChannelMessage(
        tenant_id=tenant_id,
        channel=channel,
        direction="outbound",
        contact_phone=to,
        module=module,
        related_id=related_id,
        payload=data,
        status="queued",
    )
    db.add(message)
    await db.flush()

    if channel == "whatsapp":
        result: DeliveryResult = await WhatsAppCloudAdapter().send(
            to=to, body=body, template=template
        )
        message.status = result.status
        message.external_id = result.external_id
        if result.status == "sent":
            message.sent_at = datetime.now(timezone.utc)
        message.payload = {
            **data,
            "delivery": {"status": result.status, "detail": result.detail},
        }
        await db.flush()

    logger.info(
        "engage.send channel=%s to=%s template=%s status=%s",
        channel,
        to,
        template,
        message.status,
    )
    return message
