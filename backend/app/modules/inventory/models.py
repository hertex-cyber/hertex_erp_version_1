from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBaseModel
from app.modules.finance.models import JournalEntry


class Category(TenantBaseModel):
    __tablename__ = "inventory_categories"

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inventory_categories.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Product(TenantBaseModel):
    __tablename__ = "inventory_products"

    sku: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    category_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inventory_categories.id", ondelete="SET NULL"), nullable=True
    )
    uom: Mapped[str] = mapped_column(String(20), default="pcs")
    sale_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    purchase_price: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    tax_code_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_tax_codes.id", ondelete="RESTRICT"), nullable=True
    )
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    barcode: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    hsn_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)

    category: Mapped[Optional[Category]] = relationship(lazy="selectin")


class StockMove(TenantBaseModel):
    __tablename__ = "inventory_stock_moves"
    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_inventory_stock_moves_idempotency"),
        UniqueConstraint("journal_entry_id", name="uq_inventory_stock_moves_journal_entry"),
    )

    product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("inventory_products.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    warehouse_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouses.id", ondelete="SET NULL"), nullable=True, index=True
    )
    bin_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("warehouse_bins.id", ondelete="SET NULL"), nullable=True
    )
    movement_type: Mapped[str] = mapped_column(String(40), default="adjustment", index=True)
    status: Mapped[str] = mapped_column(String(30), default="posted", nullable=False, index=True)
    movement_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    reason: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    journal_entry_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"), nullable=True
    )

    product: Mapped[Product] = relationship(lazy="selectin")
    journal_entry: Mapped[Optional[JournalEntry]] = relationship(lazy="selectin")
