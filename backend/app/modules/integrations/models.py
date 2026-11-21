from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, TenantBaseModel, TenantMixin


class ChannelMessage(BaseModel, TenantMixin):
    __tablename__ = "channel_messages"

    channel: Mapped[str] = mapped_column(String(30), default="whatsapp", index=True)
    direction: Mapped[str] = mapped_column(String(10), default="inbound", index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    contact_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    contact_phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    module: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    related_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="received", index=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class ChannelBinding(TenantBaseModel):
    __tablename__ = "integration_channel_bindings"
    __table_args__ = (
        UniqueConstraint(
            "provider", "external_ref", name="uq_integration_channel_binding_provider_ref",
        ),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    external_ref: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    label: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class WebhookEvent(BaseModel, TenantMixin):
    __tablename__ = "integration_webhook_events"
    __table_args__ = (
        UniqueConstraint(
            "provider", "event_type", "external_event_id",
            name="uq_integration_webhook_event_provider_type_external",
        ),
    )

    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    external_event_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    payload_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_valid: Mapped[bool] = mapped_column(default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="received", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
