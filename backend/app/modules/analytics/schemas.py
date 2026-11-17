from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.core.schemas import ORMModel


class DashboardKpis(ORMModel):
    revenue: Decimal
    receivables: Decimal
    payables: Decimal
    cash_collected: Decimal
    pipeline_value: Decimal
    stock_value: Decimal
    lead_count: int
    open_deals: int
    low_stock_count: int
    open_tickets: int
    active_projects: int
    employee_count: int


class MonthPoint(ORMModel):
    month: str
    revenue: Decimal
    orders: int


class StagePoint(ORMModel):
    stage: str
    count: int
    amount: Decimal


class ChannelPoint(ORMModel):
    channel: str
    orders: int
    revenue: Decimal


class ActivityItem(ORMModel):
    id: UUID
    actor_email: str
    action: str
    module: str
    entity: str
    entity_id: Optional[str] = None
    created_at: datetime


class DashboardResponse(ORMModel):
    kpis: DashboardKpis
    revenue_trend: list[MonthPoint]
    pipeline: list[StagePoint]
    channels: list[ChannelPoint]
    recent_activity: list[ActivityItem]
