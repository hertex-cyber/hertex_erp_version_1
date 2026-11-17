from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class CategoryBase(ORMModel):
    name: str = Field(min_length=1, max_length=150)
    parent_id: Optional[UUID] = None
    description: Optional[str] = None


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(ORMModel):
    name: Optional[str] = None
    parent_id: Optional[UUID] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class CategoryRead(ORMModel):
    id: UUID
    name: str
    parent_id: Optional[UUID] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime


class ProductBase(ORMModel):
    sku: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    description: Optional[str] = None
    category_id: Optional[UUID] = None
    uom: str = "pcs"
    sale_price: Decimal = Decimal("0")
    purchase_price: Decimal = Decimal("0")
    tax_rate: Decimal = Decimal("0")
    reorder_level: Decimal = Decimal("0")
    barcode: Optional[str] = None
    hsn_code: Optional[str] = None


class ProductCreate(ProductBase):
    pass


class ProductUpdate(ORMModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    category_id: Optional[UUID] = None
    uom: Optional[str] = None
    sale_price: Optional[Decimal] = None
    purchase_price: Optional[Decimal] = None
    tax_rate: Optional[Decimal] = None
    reorder_level: Optional[Decimal] = None
    barcode: Optional[str] = None
    hsn_code: Optional[str] = None
    is_active: Optional[bool] = None


class ProductRead(ORMModel):
    id: UUID
    sku: str
    name: str
    description: Optional[str] = None
    category_id: Optional[UUID] = None
    uom: str
    sale_price: Decimal
    purchase_price: Decimal
    tax_rate: Decimal
    reorder_level: Decimal
    barcode: Optional[str] = None
    hsn_code: Optional[str] = None
    is_active: bool
    created_at: datetime
    category: Optional[CategoryRead] = None


class StockMoveBase(ORMModel):
    product_id: UUID
    warehouse_id: Optional[UUID] = None
    bin_id: Optional[UUID] = None
    movement_type: str = "adjustment"
    quantity: Decimal
    unit_cost: Decimal = Decimal("0")
    reason: Optional[str] = None
    reference: Optional[str] = None


class StockMoveCreate(StockMoveBase):
    pass


class StockMoveUpdate(ORMModel):
    reason: Optional[str] = None
    reference: Optional[str] = None
    is_active: Optional[bool] = None


class StockMoveRead(ORMModel):
    id: UUID
    product_id: UUID
    warehouse_id: Optional[UUID] = None
    bin_id: Optional[UUID] = None
    movement_type: str
    quantity: Decimal
    unit_cost: Decimal
    reason: Optional[str] = None
    reference: Optional[str] = None
    is_active: bool
    created_at: datetime
    product: Optional[ProductRead] = None


class StockLevel(ORMModel):
    product_id: UUID
    sku: str
    name: str
    on_hand: Decimal
    reorder_level: Decimal
    unit_cost: Decimal
    stock_value: Decimal
    below_reorder: bool
