import json
import math
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import require_permissions
from app.core.events import publish
from app.core.exceptions import ConflictError, ForbiddenError
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.crm.service import ingest_channel_message, ingest_meta_lead
from app.modules.identity.models import Tenant, User
from app.modules.integrations.adapters import MetaLeadAdapter
from app.modules.integrations.models import ChannelBinding, ChannelMessage, WebhookEvent
from app.modules.integrations.schemas import (
    ChannelBindingCreate,
    ChannelBindingRead,
    ChannelMessageRead,
    SendMessageRequest,
    SendMessageResponse,
    WebhookEventRead,
)
from app.modules.integrations.service import (
    record_webhook_event,
    resolve_tenant_id,
    send_message,
    verify_meta_signature,
)

router = APIRouter(prefix="/integrations")


async def _default_tenant_id(db: AsyncSession) -> Optional[UUID]:
    tenant = await db.scalar(select(Tenant).order_by(Tenant.created_at).limit(1))
    return tenant.id if tenant else None


def _parse_timestamp(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _first_value(data: dict[str, Any], *keys: str) -> Optional[str]:
    for key in keys:
        value = data.get(key)
        if isinstance(value, list):
            value = value[0] if value else None
        if value:
            return str(value)
    return None


def _field_map(value: dict[str, Any], fetched: dict[str, Any]) -> dict[str, Any]:
    rows = fetched.get("field_data") or value.get("field_data") or []
    fields: dict[str, Any] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "").lower()
        values = row.get("values") or []
        if name and values:
            fields[name] = values[0]
    raw = value.get("leadgen_data") or value.get("lead") or {}
    if isinstance(raw, dict):
        fields.update(raw)
    return fields


@router.get("/whatsapp/webhook", response_class=PlainTextResponse, tags=["Integrations · WhatsApp"])
async def whatsapp_verify(request: Request):
    params = request.query_params
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")
    if mode == "subscribe" and token and token == settings.WHATSAPP_VERIFY_TOKEN:
        return PlainTextResponse(challenge)
    return PlainTextResponse("verification failed", status_code=403)


@router.post("/whatsapp/webhook", tags=["Integrations · WhatsApp"])
async def whatsapp_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    raw = await request.body()
    signature_valid = verify_meta_signature(raw, request.headers.get("x-hub-signature-256"))
    if not signature_valid:
        raise ForbiddenError("Invalid WhatsApp webhook signature")
    payload = json.loads(raw or b"{}")
    created = 0
    duplicates = 0
    message_ids: list[str] = []

    for entry in payload.get("entry", []):
        external_ref = (
            (entry.get("metadata") or {}).get("phone_number_id") or entry.get("id")
        )
        tenant_id = (
            await resolve_tenant_id(db, "whatsapp", external_ref)
            or await resolve_tenant_id(db, "meta", external_ref)
            or await _default_tenant_id(db)
        )
        if tenant_id is None:
            raise ForbiddenError("No tenant mapping for webhook")
        for change in entry.get("changes", []):
            value = change.get("value", {}) or {}
            if change.get("field") == "leadgen" or value.get("leadgen_id"):
                leadgen_id = str(value.get("leadgen_id") or "")
                if not leadgen_id:
                    continue
                event = await record_webhook_event(
                    db,
                    tenant_id=tenant_id,
                    provider="meta",
                    event_type="meta.leadgen",
                    external_event_id=leadgen_id,
                    payload=value,
                    signature_valid=signature_valid,
                )
                if event is None:
                    duplicates += 1
                    continue
                try:
                    fetched = await MetaLeadAdapter().fetch(leadgen_id) or {}
                    fields = _field_map(value, fetched)
                    name = (
                        _first_value(fields, "full_name", "name")
                        or " ".join(
                            filter(
                                None,
                                [
                                    _first_value(fields, "first_name"),
                                    _first_value(fields, "last_name"),
                                ],
                            )
                        )
                        or f"Meta Lead {leadgen_id}"
                    )
                    await ingest_meta_lead(
                        db,
                        tenant_id,
                        external_ref=leadgen_id,
                        name=name,
                        email=_first_value(fields, "email", "email_address"),
                        phone=_first_value(fields, "phone_number", "phone", "whatsapp"),
                        utm_source="meta_lead_ads",
                        utm_medium=str(value.get("form_id") or "lead_ads"),
                        utm_campaign=str(value.get("ad_id") or value.get("campaign_id") or ""),
                        payload={**value, "fetched": fetched, "fields": fields},
                    )
                    event.status = "processed"
                    event.processed_at = datetime.now(timezone.utc)
                    event.attempts = 1
                    created += 1
                except Exception as exc:
                    event.status = "failed"
                    event.attempts += 1
                    event.last_error = str(exc)[:500]
                continue

            contact = (value.get("contacts") or [{}])[0]
            for message in value.get("messages", []):
                external_id = message.get("id")
                if not external_id:
                    continue
                event = await record_webhook_event(
                    db,
                    tenant_id=tenant_id,
                    provider="whatsapp",
                    event_type="whatsapp.message",
                    external_event_id=str(external_id),
                    payload=message,
                    signature_valid=signature_valid,
                )
                if event is None or await db.scalar(
                    select(ChannelMessage.id).where(ChannelMessage.external_id == str(external_id))
                ):
                    duplicates += 1
                    continue
                phone = str(message.get("from") or "")
                body = (
                    (message.get("text") or {}).get("body")
                    or message.get("caption")
                    or (message.get("button") or {}).get("text")
                    or ""
                )
                contact_name = (contact.get("profile") or {}).get("name")
                try:
                    lead, _ = await ingest_channel_message(
                        db,
                        tenant_id,
                        message_id=str(external_id),
                        phone=phone,
                        contact_name=contact_name,
                        body=str(body),
                        occurred_at=_parse_timestamp(message.get("timestamp")),
                        payload=message,
                    )
                    record = ChannelMessage(
                        tenant_id=tenant_id,
                        channel="whatsapp",
                        direction="inbound",
                        external_id=str(external_id),
                        contact_name=contact_name,
                        contact_phone=phone,
                        module="crm",
                        related_id=lead.id,
                        payload=message,
                        status="received",
                        sent_at=_parse_timestamp(message.get("timestamp")),
                    )
                    db.add(record)
                    await db.flush()
                    message_ids.append(str(record.id))
                    event.status = "processed"
                    event.processed_at = datetime.now(timezone.utc)
                    event.attempts = 1
                    created += 1
                except Exception as exc:
                    event.status = "failed"
                    event.attempts += 1
                    event.last_error = str(exc)[:500]

    await db.commit()
    if message_ids:
        await publish(
            "channel_message.received",
            {
                "channel": "whatsapp",
                "count": len(message_ids),
                "message_ids": message_ids,
            },
        )
    return {"status": "ok", "received": created, "duplicates": duplicates}


@router.get("/messages", response_model=Page[ChannelMessageRead], tags=["Integrations · Channels"])
async def list_messages(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    channel: Optional[str] = None,
    direction: Optional[str] = None,
    user: User = Depends(require_permissions("integrations.channel.manage")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ChannelMessage)
    count_stmt = select(func.count()).select_from(ChannelMessage)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(ChannelMessage.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(ChannelMessage.tenant_id == user.tenant_id)
    if channel:
        stmt = stmt.where(ChannelMessage.channel == channel)
        count_stmt = count_stmt.where(ChannelMessage.channel == channel)
    if direction:
        stmt = stmt.where(ChannelMessage.direction == direction)
        count_stmt = count_stmt.where(ChannelMessage.direction == direction)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (await db.scalars(stmt.order_by(ChannelMessage.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


@router.post("/send", response_model=SendMessageResponse, tags=["Integrations · Channels"])
async def send_channel_message(
    payload: SendMessageRequest,
    user: User = Depends(require_permissions("integrations.channel.manage")),
    db: AsyncSession = Depends(get_db),
):
    message = await send_message(
        db,
        tenant_id=user.tenant_id,
        channel=payload.channel,
        to=payload.to,
        body=payload.body,
        template=payload.template,
        module=payload.module,
        related_id=payload.related_id,
    )
    await db.commit()
    await publish("channel_message.queued", {"message_id": str(message.id), "channel": payload.channel})
    delivery = (message.payload or {}).get("delivery") or {}
    return SendMessageResponse(
        message_id=message.id,
        channel=message.channel,
        status=message.status,
        detail=delivery.get("detail", "Queued through the Engage bridge"),
    )


@router.get(
    "/channel-bindings",
    response_model=Page[ChannelBindingRead],
    tags=["Integrations · Channels"],
)
async def list_channel_bindings(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permissions("integrations.channel.manage")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(ChannelBinding)
    count_stmt = select(func.count()).select_from(ChannelBinding)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(ChannelBinding.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(ChannelBinding.tenant_id == user.tenant_id)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (await db.scalars(stmt.order_by(ChannelBinding.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


@router.post(
    "/channel-bindings",
    response_model=ChannelBindingRead,
    status_code=201,
    tags=["Integrations · Channels"],
)
async def create_channel_binding(
    payload: ChannelBindingCreate,
    user: User = Depends(require_permissions("integrations.channel.manage")),
    db: AsyncSession = Depends(get_db),
):
    if user.tenant_id is None:
        raise ForbiddenError("Tenant context required")
    binding = ChannelBinding(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        provider=payload.provider,
        external_ref=payload.external_ref,
        label=payload.label,
        metadata_json=payload.metadata_json,
    )
    db.add(binding)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Channel binding already exists") from exc
    await db.refresh(binding)
    return binding


@router.get(
    "/webhook-events",
    response_model=Page[WebhookEventRead],
    tags=["Integrations · Webhooks"],
)
async def list_webhook_events(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    provider: Optional[str] = None,
    user: User = Depends(require_permissions("integrations.channel.manage")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(WebhookEvent)
    count_stmt = select(func.count()).select_from(WebhookEvent)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(WebhookEvent.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(WebhookEvent.tenant_id == user.tenant_id)
    if provider:
        stmt = stmt.where(WebhookEvent.provider == provider)
        count_stmt = count_stmt.where(WebhookEvent.provider == provider)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (await db.scalars(stmt.order_by(WebhookEvent.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }
