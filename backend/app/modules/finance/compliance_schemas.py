from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class ControlList(ORMModel):
    id: UUID
    event_type: Optional[str] = None
    action: Optional[str] = None
    status: str
    created_at: datetime


class OutboxEventRead(ORMModel):
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_id: UUID
    status: str
    attempts: int
    published_at: Optional[datetime] = None
    created_at: datetime


class DispatchResult(ORMModel):
    processed: int
    delivered: int
    retried: int
    dead: int


class GstReturnBuild(ORMModel):
    registration_id: UUID
    return_type: str = Field(pattern="^(GSTR1|GSTR3B)$")
    filing_period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")


class GstReturnRead(ORMModel):
    id: UUID
    registration_id: UUID
    return_type: str
    filing_period: str
    status: str
    summary: dict[str, Any]
    acknowledgement_number: Optional[str] = None
    created_at: datetime


class GstReturnFile(ORMModel):
    acknowledgement_number: str = Field(min_length=4, max_length=60)


class EInvoiceGenerate(ORMModel):
    invoice_id: UUID


class EInvoiceCancel(ORMModel):
    reason: str = Field(min_length=3, max_length=500)


class EWaybillCreate(ORMModel):
    invoice_id: UUID
    transport_mode: str = "road"
    valid_days: int = Field(default=10, ge=1, le=90)


class BankFeedCreate(ORMModel):
    name: str = Field(min_length=1, max_length=120)
    provider: str = Field(pattern="^(csv|ofx|webhook)$")
    bank_account_id: UUID
    config: dict[str, Any] = Field(default_factory=dict)
    webhook_secret: Optional[str] = Field(default=None, min_length=16, max_length=128)
    is_enabled: bool = True


class BankFeedRead(ORMModel):
    id: UUID
    name: str
    provider: str
    bank_account_id: UUID
    is_enabled: bool
    last_imported_at: Optional[datetime] = None
    created_at: datetime


class BankFeedImportResult(ORMModel):
    import_id: str
    status: str
    row_count: int
    imported_count: int
    duplicate_count: int


class LegalEntityCreate(ORMModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    gstin: Optional[str] = Field(default=None, max_length=15)
    currency: str = "INR"
    is_default: bool = False


class LegalEntityRead(LegalEntityCreate):
    id: UUID
    created_at: datetime


class NamedDimensionCreate(ORMModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=150)
    legal_entity_id: Optional[UUID] = None
    gstin: Optional[str] = Field(default=None, max_length=15)
    parent_id: Optional[UUID] = None


class DimensionCreate(ORMModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=150)


class LegalEntityUpdate(ORMModel):
    code: Optional[str] = None
    name: Optional[str] = None
    gstin: Optional[str] = None
    currency: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class DimensionUpdate(ORMModel):
    code: Optional[str] = None
    name: Optional[str] = None
    legal_entity_id: Optional[UUID] = None
    gstin: Optional[str] = None
    parent_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class WebhookEndpointCreate(ORMModel):
    name: str = Field(min_length=1, max_length=120)
    url: str = Field(min_length=8, max_length=1000)
    secret: str = Field(min_length=16, max_length=128)
    event_types: list[str] = Field(default_factory=list)
    is_enabled: bool = True
    description: Optional[str] = None


class WebhookEndpointRead(ORMModel):
    id: UUID
    name: str
    url: str
    event_types: list[str]
    is_enabled: bool
    created_at: datetime


class WebhookEndpointUpdate(ORMModel):
    url: Optional[str] = None
    secret: Optional[str] = Field(default=None, min_length=16, max_length=128)
    event_types: Optional[list[str]] = None
    is_enabled: Optional[bool] = None
    description: Optional[str] = None


class NamedDimensionRead(ORMModel):
    id: UUID
    code: str
    name: str
    legal_entity_id: Optional[UUID] = None
    gstin: Optional[str] = None
    parent_id: Optional[UUID] = None
    created_at: datetime


class IntercompanyCreate(ORMModel):
    from_entity_id: UUID
    to_entity_id: UUID
    transaction_date: date
    amount: Decimal = Field(gt=0)
    currency: str = "INR"
    description: Optional[str] = None


class IntercompanyRead(IntercompanyCreate):
    id: UUID
    number: str
    status: str
    journal_entry_id: Optional[UUID] = None
    created_at: datetime


class BudgetCreate(ORMModel):
    name: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date
    branch_id: Optional[UUID] = None
    cost_center_id: Optional[UUID] = None


class BudgetRead(BudgetCreate):
    id: UUID
    status: str
    created_at: datetime


class BudgetLineCreate(ORMModel):
    account_id: UUID
    period: str = Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")
    amount: Decimal


class AssetImpairmentCreate(ORMModel):
    impairment_date: date
    impairment_loss: Decimal = Field(gt=0)
    expense_account_id: UUID
    reason: str = Field(min_length=3, max_length=500)


class AssetWriteOffCreate(ORMModel):
    write_off_date: date
    reason: str = Field(min_length=3, max_length=500)
