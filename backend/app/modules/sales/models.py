from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Boolean, Date, ForeignKey, Numeric, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBaseModel


class Customer(TenantBaseModel):
    __tablename__ = "customers"

    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    billing_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    shipping_address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    credit_limit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    payment_terms: Mapped[str] = mapped_column(String(60), default="net_30")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class SalesOrder(TenantBaseModel):
    __tablename__ = "sales_orders"

    order_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    customer_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    order_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    channel: Mapped[str] = mapped_column(String(30), default="manual", index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    warehouse_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    tax_registration_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_tax_registrations.id", ondelete="RESTRICT"),
        nullable=True,
    )
    place_of_supply_state_code: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)

    customer: Mapped[Optional[Customer]] = relationship(lazy="selectin")
    lines: Mapped[list["SalesOrderLine"]] = relationship(
        back_populates="order", lazy="selectin", cascade="all, delete-orphan"
    )


class SalesOrderLine(TenantBaseModel):
    __tablename__ = "sales_order_lines"

    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="RESTRICT"), nullable=False
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    discount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    tax_code_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_tax_codes.id", ondelete="RESTRICT"), nullable=True
    )
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    cgst_rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    sgst_rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    igst_rate_snapshot: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    tax_type_snapshot: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    can_claim_itc_snapshot: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    output_cgst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    output_sgst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    output_igst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    line_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)

    order: Mapped[SalesOrder] = relationship(back_populates="lines")


class DeliveryChallan(TenantBaseModel):
    __tablename__ = "sales_delivery_challans"

    challan_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    order_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    dispatched_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="dispatched")
    warehouse_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
