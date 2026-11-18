from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class TicketMessageCreate(ORMModel):
    body: str = Field(min_length=1)
    is_internal: bool = False
    channel: str = "web"


class TicketMessageRead(ORMModel):
    id: UUID
    ticket_id: UUID
    author_id: Optional[UUID] = None
    author_name: str
    body: str
    is_internal: bool
    channel: str
    created_at: datetime


class TicketBase(ORMModel):
    subject: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    customer_id: Optional[UUID] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    channel: str = "web"
    priority: str = "medium"
    status: str = "open"
    assignee_id: Optional[UUID] = None
    sla_due_at: Optional[datetime] = None
    needs_project_work: bool = False


class TicketCreate(TicketBase):
    pass


class TicketUpdate(ORMModel):
    subject: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assignee_id: Optional[UUID] = None
    sla_due_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    needs_project_work: Optional[bool] = None
    is_active: Optional[bool] = None


class TicketRead(ORMModel):
    id: UUID
    ticket_number: str
    subject: str
    description: Optional[str] = None
    customer_id: Optional[UUID] = None
    requester_name: Optional[str] = None
    requester_email: Optional[str] = None
    channel: str
    priority: str
    status: str
    assignee_id: Optional[UUID] = None
    sla_due_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    needs_project_work: bool
    project_work_item_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    messages: list[TicketMessageRead] = []
