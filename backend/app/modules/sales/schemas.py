from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class CustomerBase(ORMModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    credit_limit: Decimal = Decimal("0")
    payment_terms: str = "net_30"
    notes: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(ORMModel):
    code: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    credit_limit: Optional[Decimal] = None
    payment_terms: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CustomerRead(ORMModel):
    id: UUID
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    billing_address: Optional[str] = None
    shipping_address: Optional[str] = None
    credit_limit: Decimal
    payment_terms: str
    is_active: bool
    created_at: datetime


class SalesOrderLineCreate(ORMModel):
    product_id: UUID
    description: Optional[str] = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    discount: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    tax_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    tax_code_id: Optional[UUID] = None


class SalesOrderLineRead(ORMModel):
    id: UUID
    product_id: UUID
    description: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    discount: Decimal
    tax_rate: Decimal
    tax_code_id: Optional[UUID] = None
    cgst_amount: Decimal = Decimal("0")
    sgst_amount: Decimal = Decimal("0")
    igst_amount: Decimal = Decimal("0")
    line_total: Decimal


class SalesOrderCreate(ORMModel):
    customer_id: Optional[UUID] = None
    order_date: date
    channel: str = "manual"
    notes: Optional[str] = None
    warehouse_id: Optional[UUID] = None
    tax_registration_id: Optional[UUID] = None
    place_of_supply_state_code: Optional[str] = Field(default=None, pattern=r"^[0-9]{2}$")
    lines: list[SalesOrderLineCreate] = Field(min_length=1)


class SalesOrderUpdate(ORMModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    warehouse_id: Optional[UUID] = None


class SalesOrderRead(ORMModel):
    id: UUID
    order_number: str
    customer_id: Optional[UUID] = None
    order_date: date
    status: str
    channel: str
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    total: Decimal
    notes: Optional[str] = None
    warehouse_id: Optional[UUID] = None
    tax_registration_id: Optional[UUID] = None
    place_of_supply_state_code: Optional[str] = None
    is_active: bool
    created_at: datetime
    customer: Optional[CustomerRead] = None
    lines: list[SalesOrderLineRead] = []


class DeliveryChallanBase(ORMModel):
    order_id: UUID
    dispatched_date: date
    status: str = "dispatched"
    warehouse_id: Optional[UUID] = None
    notes: Optional[str] = None


class DeliveryChallanCreate(DeliveryChallanBase):
    pass


class DeliveryChallanUpdate(ORMModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class DeliveryChallanRead(ORMModel):
    id: UUID
    challan_number: str
    order_id: UUID
    dispatched_date: date
    status: str
    warehouse_id: Optional[UUID] = None
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
