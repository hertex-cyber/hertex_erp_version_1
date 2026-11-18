from decimal import Decimal

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.db.session import get_db
from app.modules.finance.service import submit_finance_approval
from app.modules.identity.models import User
from app.modules.inventory.models import Category, Product, StockMove
from app.modules.inventory.schemas import (
    CategoryCreate,
    CategoryRead,
    CategoryUpdate,
    InventoryAdjustmentCreate,
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
    create_enabled=False,
    update_enabled=False,
    delete_enabled=False,
)

read_products = require_permissions("inventory.product.read")
create_stock_moves = require_permissions("inventory.stockmove.create")


@router.post(
    "/stock-adjustments",
    response_model=StockMoveRead,
    status_code=201,
    tags=["Inventory · Ledger"],
)
async def create_stock_adjustment(
    payload: InventoryAdjustmentCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=16, max_length=120),
    user: User = Depends(create_stock_moves),
    db: AsyncSession = Depends(get_db),
):
    if user.tenant_id is None:
        raise ValidationError("A tenant is required to post inventory adjustments")

    existing = await db.scalar(
        select(StockMove)
        .options(selectinload(StockMove.product))
        .where(
            StockMove.tenant_id == user.tenant_id,
            StockMove.idempotency_key == idempotency_key,
        )
        .with_for_update()
    )
    if existing is not None:
        same_request = (
            existing.movement_type == "adjustment"
            and existing.product_id == payload.product_id
            and (
                payload.warehouse_id is None
                or existing.warehouse_id == payload.warehouse_id
            )
            and existing.bin_id == payload.bin_id
            and existing.quantity == payload.quantity
            and existing.unit_cost == payload.unit_cost
            and existing.reason == payload.reason
            and existing.reference == payload.reference
            and existing.movement_date == payload.adjustment_date
            and existing.status in {"pending_approval", "posted"}
        )
        if not same_request:
            raise ConflictError("Idempotency key was already used for a different adjustment")
        return existing

    product = await db.scalar(
        select(Product).where(
            Product.id == payload.product_id,
            Product.tenant_id == user.tenant_id,
            Product.is_active.is_(True),
        )
    )
    if product is None:
        raise NotFoundError("Active product not found")

    warehouse_id = payload.warehouse_id
    if warehouse_id is not None:
        from app.modules.warehouse.models import Warehouse

        warehouse = await db.scalar(
            select(Warehouse).where(
                Warehouse.id == warehouse_id,
                Warehouse.tenant_id == user.tenant_id,
                Warehouse.is_active.is_(True),
            )
        )
        if warehouse is None:
            raise NotFoundError("Active warehouse not found")

    if payload.bin_id is not None:
        from app.modules.warehouse.models import Bin

        bin_stmt = select(Bin).where(
            Bin.id == payload.bin_id,
            Bin.tenant_id == user.tenant_id,
            Bin.is_active.is_(True),
        )
        if warehouse_id is not None:
            bin_stmt = bin_stmt.where(Bin.warehouse_id == warehouse_id)
        bin_record = await db.scalar(bin_stmt)
        if bin_record is None:
            raise ValidationError("Bin must be active and belong to the selected warehouse")
        if warehouse_id is None:
            warehouse_id = bin_record.warehouse_id

    move = StockMove(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        product_id=product.id,
        warehouse_id=warehouse_id,
        bin_id=payload.bin_id,
        movement_type="adjustment",
        status="pending_approval",
        movement_date=payload.adjustment_date,
        quantity=payload.quantity,
        unit_cost=payload.unit_cost,
        reason=payload.reason,
        reference=payload.reference,
        idempotency_key=idempotency_key,
    )
    db.add(move)
    await db.flush()
    approval = await submit_finance_approval(
        db,
        user,
        entity_type="inventory_adjustment",
        entity_id=move.id,
        amount=(abs(move.quantity) * move.unit_cost).quantize(Decimal("0.01")),
        summary=f"Stock adjustment: {product.name} ({move.quantity})",
        tenant_id=move.tenant_id,
    )
    await record_audit(
        db,
        user=user,
        action="submit_for_approval",
        module="inventory",
        entity="StockAdjustment",
        entity_id=move.id,
        changes={
            "product_id": product.id,
            "quantity": payload.quantity,
            "unit_cost": payload.unit_cost,
            "adjustment_date": payload.adjustment_date,
            "approval_id": approval.id,
            "idempotency_key": idempotency_key,
        },
        request=request,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        existing = await db.scalar(
            select(StockMove)
            .options(selectinload(StockMove.product), selectinload(StockMove.journal_entry))
            .where(
                StockMove.tenant_id == user.tenant_id,
                StockMove.idempotency_key == idempotency_key,
            )
        )
        if existing is not None:
            same_request = (
                existing.product_id == payload.product_id
                and (
                    payload.warehouse_id is None
                    or existing.warehouse_id == payload.warehouse_id
                )
                and existing.bin_id == payload.bin_id
                and existing.quantity == payload.quantity
                and existing.unit_cost == payload.unit_cost
                and existing.reason == payload.reason
                and existing.reference == payload.reference
                and existing.movement_date == payload.adjustment_date
                and existing.status in {"pending_approval", "posted"}
            )
            if same_request:
                return existing
            raise ConflictError("Idempotency key was already used for a different adjustment") from exc
        raise ConflictError("Inventory adjustment conflicts with an existing ledger record") from exc
    return await db.scalar(
        select(StockMove)
        .options(selectinload(StockMove.product), selectinload(StockMove.journal_entry))
        .where(StockMove.id == move.id)
    )


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
        .outerjoin(
            StockMove,
            (StockMove.product_id == Product.id) & (StockMove.status == "posted"),
        )
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
