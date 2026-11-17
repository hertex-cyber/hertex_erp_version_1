from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class CampaignBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    channel: str = "whatsapp"
    status: str = "draft"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Decimal = Decimal("0")
    spend: Decimal = Decimal("0")
    goal: Optional[str] = None
    description: Optional[str] = None


class CampaignCreate(CampaignBase):
    pass


class CampaignUpdate(ORMModel):
    name: Optional[str] = None
    channel: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[Decimal] = None
    spend: Optional[Decimal] = None
    goal: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CampaignRead(ORMModel):
    id: UUID
    name: str
    channel: str
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Decimal
    spend: Decimal
    goal: Optional[str] = None
    is_active: bool
    created_at: datetime


class SegmentBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    filters: dict[str, Any] = {}


class SegmentCreate(SegmentBase):
    pass


class SegmentUpdate(ORMModel):
    name: Optional[str] = None
    description: Optional[str] = None
    filters: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class SegmentRead(ORMModel):
    id: UUID
    name: str
    description: Optional[str] = None
    filters: dict[str, Any]
    is_active: bool
    created_at: datetime


class CampaignSendBase(ORMModel):
    campaign_id: UUID
    segment_id: Optional[UUID] = None
    channel: str = "whatsapp"
    status: str = "scheduled"
    scheduled_at: Optional[datetime] = None


class CampaignSendCreate(CampaignSendBase):
    pass


class CampaignSendUpdate(ORMModel):
    status: Optional[str] = None
    sent_count: Optional[int] = None
    delivered_count: Optional[int] = None
    failed_count: Optional[int] = None
    scheduled_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class CampaignSendRead(ORMModel):
    id: UUID
    campaign_id: UUID
    segment_id: Optional[UUID] = None
    channel: str
    status: str
    scheduled_at: Optional[datetime] = None
    sent_count: int
    delivered_count: int
    failed_count: int
    created_at: datetime
