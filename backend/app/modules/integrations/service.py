import hashlib
import hmac
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ForbiddenError
from app.modules.integrations.adapters import DeliveryResult, WhatsAppCloudAdapter
from app.modules.integrations.models import ChannelBinding, ChannelMessage, WebhookEvent

logger = logging.getLogger("hertex.engage_bridge")


def _phone_digits(value: str | None) -> str:
    return "".join(char for char in (value or "") if char.isdigit())


def verify_meta_signature(raw: bytes, header: str | None) -> bool:
    secret = settings.META_APP_SECRET
    if not secret:
        if settings.ENVIRONMENT == "production":
            raise ForbiddenError("META_APP_SECRET is not configured")
        return True
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    return bool(header and hmac.compare_digest(header, expected))


def payload_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


async def resolve_tenant_id(
    db: AsyncSession, provider: str, external_ref: str | None
) -> Optional[UUID]:
    if not external_ref:
        return None
    binding = await db.scalar(
        select(ChannelBinding).where(
            ChannelBinding.provider == provider,
            ChannelBinding.external_ref == external_ref,
            ChannelBinding.is_active.is_(True),
        )
    )
    return binding.tenant_id if binding else None


async def record_webhook_event(
    db: AsyncSession,
    *,
    tenant_id: Optional[UUID],
    provider: str,
    event_type: str,
    external_event_id: str,
    payload: dict[str, Any],
    signature_valid: bool,
) -> Optional[WebhookEvent]:
    existing = await db.scalar(
        select(WebhookEvent.id).where(
            WebhookEvent.provider == provider,
            WebhookEvent.event_type == event_type,
            WebhookEvent.external_event_id == external_event_id,
        )
    )
    if existing is not None:
        return None
    event = WebhookEvent(
        tenant_id=tenant_id,
        provider=provider,
        event_type=event_type,
        external_event_id=external_event_id,
        payload_hash=payload_hash(payload),
        signature_valid=signature_valid,
        payload=payload,
        status="received",
    )
    db.add(event)
    await db.flush()
    return event


async def _whatsapp_consent(
    db: AsyncSession, tenant_id: UUID | None, to: str
) -> Optional[bool]:
    from app.modules.crm.models import ConsentRecord, Contact, Lead

    target = _phone_digits(to)
    if not target:
        return None
    subject: Contact | Lead | None = None
    for model in (Contact, Lead):
        stmt = select(model).where(model.phone.is_not(None), model.is_active.is_(True))
        if tenant_id:
            stmt = stmt.where(model.tenant_id == tenant_id)
        records = (await db.scalars(stmt.limit(1000))).all()
        subject = next(
            (record for record in records if _phone_digits(record.phone) == target), None
        )
        if subject is not None:
            break
    if subject is None:
        return None
    consent = await db.scalar(
        select(ConsentRecord)
        .where(
            ConsentRecord.tenant_id == subject.tenant_id,
            ConsentRecord.subject_type == ("lead" if isinstance(subject, Lead) else "contact"),
            ConsentRecord.subject_id == subject.id,
            ConsentRecord.channel == "whatsapp",
        )
        .order_by(ConsentRecord.captured_at.desc(), ConsentRecord.created_at.desc())
        .limit(1)
    )
    if consent is None:
        return bool(subject.whatsapp_opt_in)
    if consent.status in {"opted_out", "revoked"}:
        return False
    if consent.status != "opted_in":
        return None
    captured_at = consent.captured_at
    if captured_at is None:
        return True
    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=timezone.utc)
    age = datetime.now(timezone.utc) - captured_at
    return age <= timedelta(hours=24)


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
