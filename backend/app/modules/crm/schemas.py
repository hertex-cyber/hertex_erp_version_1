from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class CompanyBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    industry: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "India"
    annual_revenue: Decimal = Decimal("0")
    notes: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(ORMModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    annual_revenue: Optional[Decimal] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CompanyRead(ORMModel):
    id: UUID
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str
    annual_revenue: Decimal
    is_active: bool
    created_at: datetime


class ContactBase(ORMModel):
    company_id: Optional[UUID] = None
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    whatsapp_opt_in: bool = False
    notes: Optional[str] = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(ORMModel):
    company_id: Optional[UUID] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    whatsapp_opt_in: Optional[bool] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ContactRead(ORMModel):
    id: UUID
    company_id: Optional[UUID] = None
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    whatsapp_opt_in: bool
    is_active: bool
    created_at: datetime
    company: Optional[CompanyRead] = None


class LeadBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: str = "manual"
    status: str = "new"
    score: int = 0
    estimated_value: Decimal = Decimal("0")
    owner_id: Optional[UUID] = None
    whatsapp_opt_in: bool = False
    notes: Optional[str] = None
    next_follow_up: Optional[date] = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(ORMModel):
    name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    score: Optional[int] = None
    estimated_value: Optional[Decimal] = None
    owner_id: Optional[UUID] = None
    whatsapp_opt_in: Optional[bool] = None
    notes: Optional[str] = None
    next_follow_up: Optional[date] = None
    is_active: Optional[bool] = None


class LeadRead(ORMModel):
    id: UUID
    name: str
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: str
    status: str
    score: int
    estimated_value: Decimal
    owner_id: Optional[UUID] = None
    whatsapp_opt_in: bool
    next_follow_up: Optional[date] = None
    is_active: bool
    created_at: datetime


class DealBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    company_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    stage: str = "qualification"
    amount: Decimal = Decimal("0")
    probability: int = 20
    expected_close_date: Optional[date] = None
    owner_id: Optional[UUID] = None
    notes: Optional[str] = None


class DealCreate(DealBase):
    pass


class DealUpdate(ORMModel):
    name: Optional[str] = None
    company_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    stage: Optional[str] = None
    amount: Optional[Decimal] = None
    probability: Optional[int] = None
    expected_close_date: Optional[date] = None
    owner_id: Optional[UUID] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class DealRead(ORMModel):
    id: UUID
    name: str
    company_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    stage: str
    amount: Decimal
    probability: int
    expected_close_date: Optional[date] = None
    owner_id: Optional[UUID] = None
    won_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime


class ActivityBase(ORMModel):
    activity_type: str = "task"
    subject: str = Field(min_length=1, max_length=255)
    notes: Optional[str] = None
    related_entity: Optional[str] = None
    related_id: Optional[UUID] = None
    due_at: Optional[datetime] = None
    completed: bool = False
    owner_id: Optional[UUID] = None


class ActivityCreate(ActivityBase):
    pass


class ActivityUpdate(ORMModel):
    activity_type: Optional[str] = None
    subject: Optional[str] = None
    notes: Optional[str] = None
    related_entity: Optional[str] = None
    related_id: Optional[UUID] = None
    due_at: Optional[datetime] = None
    completed: Optional[bool] = None
    owner_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class ActivityRead(ORMModel):
    id: UUID
    activity_type: str
    subject: str
    notes: Optional[str] = None
    related_entity: Optional[str] = None
    related_id: Optional[UUID] = None
    due_at: Optional[datetime] = None
    completed: bool
    owner_id: Optional[UUID] = None
    created_at: datetime
