from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class ChannelMessageRead(ORMModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    channel: str
    direction: str
    external_id: Optional[str] = None
    contact_name: Optional[str] = None
    contact_phone: Optional[str] = None
    module: Optional[str] = None
    payload: dict[str, Any]
    status: str
    sent_at: Optional[datetime] = None
    created_at: datetime


class SendMessageRequest(ORMModel):
    channel: str = "whatsapp"
    to: str = Field(min_length=5)
    body: str = Field(min_length=1)
    template: Optional[str] = None
    module: Optional[str] = None
    related_id: Optional[UUID] = None


class SendMessageResponse(ORMModel):
    message_id: UUID
    channel: str
    status: str
    detail: str


class ChannelBindingCreate(ORMModel):
    provider: str = Field(min_length=1, max_length=40)
    external_ref: str = Field(min_length=1, max_length=160)
    label: Optional[str] = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class ChannelBindingRead(ORMModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    provider: str
    external_ref: str
    label: Optional[str] = None
    metadata_json: dict[str, Any]
    is_active: bool
    created_at: datetime


class WebhookEventRead(ORMModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    provider: str
    event_type: str
    external_event_id: str
    signature_valid: bool
    status: str
    attempts: int
    processed_at: Optional[datetime] = None
    created_at: datetime
