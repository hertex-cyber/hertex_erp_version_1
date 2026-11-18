from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class PosSessionCreate(ORMModel):
    terminal_name: str = Field(min_length=1, max_length=120)
    opening_cash: Decimal = Decimal("0")


class PosSessionUpdate(ORMModel):
    status: Optional[str] = None
    closing_cash: Optional[Decimal] = None


class PosSessionRead(ORMModel):
    id: UUID
    terminal_name: str
    opened_by_id: Optional[UUID] = None
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    opening_cash: Decimal
    closing_cash: Optional[Decimal] = None
    status: str
    created_at: datetime


class PosSaleLineCreate(ORMModel):
    product_id: UUID
    quantity: Decimal = Field(gt=0)
    unit_price: Optional[Decimal] = None


class PosSaleLineRead(ORMModel):
    id: UUID
    product_id: UUID
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal
    line_total: Decimal


class PosSaleCreate(ORMModel):
    session_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    tax_registration_id: Optional[UUID] = None
    place_of_supply_state_code: Optional[str] = Field(default=None, pattern=r"^[0-9]{2}$")
    payment_method: str = "cash"
    notes: Optional[str] = None
    lines: list[PosSaleLineCreate] = Field(min_length=1)


class PosSaleRead(ORMModel):
    id: UUID
    session_id: Optional[UUID] = None
    sales_order_id: Optional[UUID] = None
    sale_number: str
    customer_id: Optional[UUID] = None
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    payment_method: str
    status: str
    notes: Optional[str] = None
    created_at: datetime
    lines: list[PosSaleLineRead] = []
