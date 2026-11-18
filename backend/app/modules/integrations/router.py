import hashlib
import hmac
import json
import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import require_permissions
from app.core.events import publish
from app.core.exceptions import ForbiddenError
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.identity.models import Tenant, User
from app.modules.integrations.models import ChannelMessage
from app.modules.integrations.schemas import (
    ChannelMessageRead,
    SendMessageRequest,
    SendMessageResponse,
)
from app.modules.integrations.service import send_message

router = APIRouter(prefix="/integrations")


async def _default_tenant_id(db: AsyncSession) -> Optional[UUID]:
    tenant = await db.scalar(select(Tenant).order_by(Tenant.created_at).limit(1))
    return tenant.id if tenant else None


def _verify_meta_signature(request: Request, raw: bytes) -> None:
    secret = settings.META_APP_SECRET
    if not secret:
        if settings.ENVIRONMENT == "production":
            raise ForbiddenError("META_APP_SECRET is not configured")
        return
    header = request.headers.get("x-hub-signature-256", "")
    expected = "sha256=" + hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    if not header or not hmac.compare_digest(header, expected):
        raise ForbiddenError("Invalid WhatsApp webhook signature")


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
    _verify_meta_signature(request, raw)
    payload = json.loads(raw or b"{}")
    tenant_id = await _default_tenant_id(db)
    created = 0
    stored: list[ChannelMessage] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            contact = (value.get("contacts") or [{}])[0]
            for message in value.get("messages", []):
                external_id = message.get("id")
                if external_id:
                    duplicate = await db.scalar(
                        select(ChannelMessage.id).where(
                            ChannelMessage.external_id == external_id
                        )
                    )
                    if duplicate:
                        continue
                record = ChannelMessage(
                    tenant_id=tenant_id,
                    channel="whatsapp",
                    direction="inbound",
                    external_id=external_id,
                    contact_name=(contact.get("profile") or {}).get("name"),
                    contact_phone=message.get("from"),
                    payload=message,
                    status="received",
                )
                db.add(record)
                stored.append(record)
                created += 1
    await db.commit()
    if created:
        await publish(
            "channel_message.received",
            {
                "channel": "whatsapp",
                "count": created,
                "message_ids": [str(record.id) for record in stored],
            },
        )
    return {"status": "ok", "received": created}


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
