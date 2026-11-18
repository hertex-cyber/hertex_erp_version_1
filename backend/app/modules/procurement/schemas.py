from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class VendorBase(ORMModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    address: Optional[str] = None
    payment_terms: str = "net_30"
    rating: Decimal = Decimal("0")
    notes: Optional[str] = None


class VendorCreate(VendorBase):
    pass


class VendorUpdate(ORMModel):
    code: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    address: Optional[str] = None
    payment_terms: Optional[str] = None
    rating: Optional[Decimal] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class VendorRead(ORMModel):
    id: UUID
    code: str
    name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    gstin: Optional[str] = None
    payment_terms: str
    rating: Decimal
    is_active: bool
    created_at: datetime


class RequisitionBase(ORMModel):
    requested_by_id: Optional[UUID] = None
    department: Optional[str] = None
    required_date: Optional[date] = None
    status: str = "pending"
    notes: Optional[str] = None


class RequisitionCreate(RequisitionBase):
    pass


class RequisitionUpdate(ORMModel):
    department: Optional[str] = None
    required_date: Optional[date] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class RequisitionRead(ORMModel):
    id: UUID
    requisition_number: str
    requested_by_id: Optional[UUID] = None
    department: Optional[str] = None
    required_date: Optional[date] = None
    status: str
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime


class POLineCreate(ORMModel):
    product_id: UUID
    description: Optional[str] = None
    quantity: Decimal = Field(gt=0)
    unit_price: Decimal = Decimal("0")


class POLineRead(ORMModel):
    id: UUID
    product_id: UUID
    description: Optional[str] = None
    quantity: Decimal
    unit_price: Decimal
    received_quantity: Decimal
    line_total: Decimal


class PurchaseOrderCreate(ORMModel):
    vendor_id: UUID
    requisition_id: Optional[UUID] = None
    order_date: date
    expected_date: Optional[date] = None
    notes: Optional[str] = None
    lines: list[POLineCreate] = Field(min_length=1)


class PurchaseOrderUpdate(ORMModel):
    expected_date: Optional[date] = None
    notes: Optional[str] = None
    status: Optional[str] = None


class PurchaseOrderRead(ORMModel):
    id: UUID
    po_number: str
    vendor_id: UUID
    requisition_id: Optional[UUID] = None
    order_date: date
    expected_date: Optional[date] = None
    status: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    notes: Optional[str] = None
    approved_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime
    vendor: Optional[VendorRead] = None
    lines: list[POLineRead] = []


class GoodsReceiptLineRead(ORMModel):
    id: UUID
    po_line_id: UUID
    quantity_received: Decimal


class GoodsReceiptCreate(ORMModel):
    purchase_order_id: UUID
    received_date: date
    notes: Optional[str] = None


class GoodsReceiptRead(ORMModel):
    id: UUID
    grn_number: str
    journal_entry_id: Optional[UUID] = None
    purchase_order_id: UUID
    received_date: date
    received_by_id: Optional[UUID] = None
    notes: Optional[str] = None
    created_at: datetime
    lines: list[GoodsReceiptLineRead] = []


class VendorInvoiceBase(ORMModel):
    vendor_id: UUID
    purchase_order_id: Optional[UUID] = None
    invoice_number: str
    issue_date: date
    due_date: Optional[date] = None
    amount: Decimal = Decimal("0")
    tax_amount: Decimal = Decimal("0")
    status: str = "pending"
    notes: Optional[str] = None


class VendorInvoiceCreate(VendorInvoiceBase):
    pass


class VendorInvoiceUpdate(ORMModel):
    due_date: Optional[date] = None
    amount: Optional[Decimal] = None
    tax_amount: Optional[Decimal] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class VendorInvoiceTaxLineCreate(ORMModel):
    tax_code_id: UUID
    registration_id: UUID
    place_of_supply_state_code: str = Field(pattern=r"^[0-9]{2}$")
    taxable_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    description: Optional[str] = Field(default=None, max_length=255)


class VendorInvoiceTaxLinesUpdate(ORMModel):
    lines: list[VendorInvoiceTaxLineCreate] = Field(min_length=1, max_length=200)


class VendorInvoiceTaxLineRead(ORMModel):
    id: UUID
    tax_code_id: UUID
    registration_id: UUID
    tax_type_snapshot: str
    can_claim_itc_snapshot: bool
    description: Optional[str] = None
    place_of_supply_state_code: str
    taxable_amount: Decimal
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal


class VendorInvoiceRead(ORMModel):
    id: UUID
    vendor_id: UUID
    purchase_order_id: Optional[UUID] = None
    invoice_number: str
    issue_date: date
    due_date: Optional[date] = None
    amount: Decimal
    tax_amount: Decimal
    paid_amount: Decimal = Decimal("0")
    status: str
    notes: Optional[str] = None
    is_active: bool
    created_at: datetime
    tax_lines: list[VendorInvoiceTaxLineRead] = []
