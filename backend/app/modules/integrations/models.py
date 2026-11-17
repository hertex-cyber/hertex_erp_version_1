from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, TenantMixin


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
