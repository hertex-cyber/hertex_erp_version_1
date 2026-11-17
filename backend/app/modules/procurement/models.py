from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBaseModel


class Vendor(TenantBaseModel):
    __tablename__ = "procurement_vendors"

    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payment_terms: Mapped[str] = mapped_column(String(60), default="net_30")
    rating: Mapped[int] = mapped_column(Numeric(3, 1), default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PurchaseRequisition(TenantBaseModel):
    __tablename__ = "procurement_requisitions"

    requisition_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    requested_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    department: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    required_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class PurchaseOrder(TenantBaseModel):
    __tablename__ = "procurement_purchase_orders"

    po_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("procurement_vendors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    requisition_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("procurement_requisitions.id", ondelete="SET NULL"), nullable=True
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    vendor: Mapped[Vendor] = relationship(lazy="selectin")
    lines: Mapped[list["POLine"]] = relationship(
        back_populates="order", lazy="selectin", cascade="all, delete-orphan"
    )


class POLine(TenantBaseModel):
    __tablename__ = "procurement_po_lines"

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("procurement_purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    received_quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class GoodsReceipt(TenantBaseModel):
    __tablename__ = "procurement_goods_receipts"

    grn_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    purchase_order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("procurement_purchase_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    received_date: Mapped[date] = mapped_column(Date, nullable=False)
    received_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    lines: Mapped[list["GoodsReceiptLine"]] = relationship(
        back_populates="receipt", lazy="selectin", cascade="all, delete-orphan"
    )


class GoodsReceiptLine(TenantBaseModel):
    __tablename__ = "procurement_grn_lines"

    grn_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("procurement_goods_receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    po_line_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("procurement_po_lines.id", ondelete="CASCADE"), nullable=False
    )
    quantity_received: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)

    receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")


class VendorInvoice(TenantBaseModel):
    __tablename__ = "procurement_vendor_invoices"

    invoice_number: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    vendor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("procurement_vendors.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    purchase_order_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("procurement_purchase_orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
