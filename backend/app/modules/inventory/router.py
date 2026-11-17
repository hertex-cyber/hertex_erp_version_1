from decimal import Decimal

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.inventory.models import Category, Product, StockMove
from app.modules.inventory.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    ProductCreate,
    ProductRead,
    ProductUpdate,
    StockLevel,
    StockMoveCreate,
    StockMoveRead,
    StockMoveUpdate,
)

router = APIRouter(prefix="/inventory")


def _include(*args, **kwargs):
    child, _ = build_crud_router(module="inventory", **kwargs)
    router.include_router(child)


_include(
    model=Category,
    read_schema=CategoryRead,
    create_schema=CategoryCreate,
    update_schema=CategoryUpdate,
    prefix="/categories",
    tags=["Inventory · Categories"],
    permission_prefix="inventory.category",
    entity="Category",
    search_fields=("name", "description"),
)

_include(
    model=Product,
    read_schema=ProductRead,
    create_schema=ProductCreate,
    update_schema=ProductUpdate,
    prefix="/products",
    tags=["Inventory · Products"],
    permission_prefix="inventory.product",
    entity="Product",
    search_fields=("sku", "name", "barcode", "hsn_code"),
    filter_fields=("category_id", "uom"),
    load_options=(selectinload(Product.category),),
)

_include(
    model=StockMove,
    read_schema=StockMoveRead,
    create_schema=StockMoveCreate,
    update_schema=StockMoveUpdate,
    prefix="/stock-moves",
    tags=["Inventory · Ledger"],
    permission_prefix="inventory.stockmove",
    entity="StockMove",
    search_fields=("reference", "reason"),
    filter_fields=("product_id", "warehouse_id", "movement_type"),
    load_options=(selectinload(StockMove.product),),
    soft_delete=False,
)

read_products = require_permissions("inventory.product.read")


async def _stock_levels(db: AsyncSession, user: User, only_low: bool = False) -> list[StockLevel]:
    stmt = (
        select(
            Product.id,
            Product.sku,
            Product.name,
            Product.reorder_level,
            Product.purchase_price,
            func.coalesce(func.sum(StockMove.quantity), 0).label("on_hand"),
        )
        .outerjoin(StockMove, StockMove.product_id == Product.id)
        .where(Product.is_active.is_(True))
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Product.tenant_id == user.tenant_id)
    stmt = stmt.group_by(
        Product.id, Product.sku, Product.name, Product.reorder_level, Product.purchase_price
    ).order_by(Product.name)

    rows = (await db.execute(stmt)).all()
    levels: list[StockLevel] = []
    for row in rows:
        on_hand = Decimal(row.on_hand or 0)
        unit_cost = Decimal(row.purchase_price or 0)
        below = on_hand <= Decimal(row.reorder_level or 0)
        if only_low and not below:
            continue
        levels.append(
            StockLevel(
                product_id=row.id,
                sku=row.sku,
                name=row.name,
                on_hand=on_hand,
                reorder_level=Decimal(row.reorder_level or 0),
                unit_cost=unit_cost,
                stock_value=(on_hand * unit_cost).quantize(Decimal("0.01")),
                below_reorder=below,
            )
        )
    return levels


@router.get("/stock-levels", response_model=list[StockLevel], tags=["Inventory · Reports"])
async def stock_levels(
    user: User = Depends(read_products), db: AsyncSession = Depends(get_db)
):
    return await _stock_levels(db, user)


@router.get("/low-stock", response_model=list[StockLevel], tags=["Inventory · Reports"])
async def low_stock(
    user: User = Depends(read_products), db: AsyncSession = Depends(get_db)
):
    return await _stock_levels(db, user, only_low=True)
