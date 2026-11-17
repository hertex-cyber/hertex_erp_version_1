import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError
from app.core.numbering import next_number
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.pos.models import PosSale, PosSaleLine, PosSession
from app.modules.pos.schemas import (
    PosSaleCreate,
    PosSaleRead,
    PosSessionCreate,
    PosSessionRead,
    PosSessionUpdate,
)

router = APIRouter(prefix="/pos")


def _include(**kwargs):
    child, _ = build_crud_router(module="pos", **kwargs)
    router.include_router(child)


_include(
    model=PosSession,
    read_schema=PosSessionRead,
    create_schema=PosSessionCreate,
    update_schema=PosSessionUpdate,
    prefix="/sessions",
    tags=["POS · Sessions"],
    permission_prefix="pos.session",
    entity="PosSession",
    search_fields=("terminal_name",),
    filter_fields=("status",),
    soft_delete=False,
)

read_sales = require_permissions("pos.sale.read")
checkout = require_permissions("pos.sale.checkout")


async def _load_sale(db: AsyncSession, user: User, sale_id) -> PosSale:
    stmt = select(PosSale).options(selectinload(PosSale.lines)).where(PosSale.id == sale_id)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(PosSale.tenant_id == user.tenant_id)
    sale = await db.scalar(stmt)
    if sale is None:
        raise NotFoundError("POS sale not found")
    return sale


@router.get("/sales", response_model=Page[PosSaleRead], tags=["POS · Sales"])
async def list_sales(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    session_id: Optional[str] = None,
    user: User = Depends(read_sales),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PosSale).options(selectinload(PosSale.lines))
    count_stmt = select(func.count()).select_from(PosSale)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(PosSale.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(PosSale.tenant_id == user.tenant_id)
    if session_id:
        stmt = stmt.where(PosSale.session_id == session_id)
        count_stmt = count_stmt.where(PosSale.session_id == session_id)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (await db.scalars(stmt.order_by(PosSale.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


@router.post("/checkout", response_model=PosSaleRead, status_code=201, tags=["POS · Sales"])
async def pos_checkout(
    payload: PosSaleCreate,
    request: Request,
    user: User = Depends(checkout),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.finance.models import Invoice
    from app.modules.finance.service import post_invoice_journal
    from app.modules.inventory.models import Product, StockMove
    from app.modules.sales.models import SalesOrder, SalesOrderLine
    from app.modules.warehouse.models import Warehouse

    if payload.session_id:
        session = await db.scalar(select(PosSession).where(PosSession.id == payload.session_id))
        if session is None:
            raise NotFoundError("POS session not found")
        if session.status != "open":
            raise ConflictError("POS session is not open")

    subtotal = Decimal("0")
    tax_total = Decimal("0")
    resolved = []
    for line in payload.lines:
        product = await db.get(Product, line.product_id)
        if product is None:
            raise NotFoundError(f"Product {line.product_id} not found")
        unit_price = line.unit_price if line.unit_price is not None else product.sale_price
        base = unit_price * line.quantity
        tax = (base * (product.tax_rate or 0) / Decimal("100")).quantize(Decimal("0.01"))
        subtotal += base
        tax_total += tax
        resolved.append((line, product, unit_price, tax, base + tax))

    total = subtotal + tax_total
    sale_number = await next_number(db, PosSale, "sale_number", "PS", user.tenant_id)

    order = SalesOrder(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        order_number=await next_number(db, SalesOrder, "order_number", "SO", user.tenant_id),
        customer_id=payload.customer_id,
        order_date=date.today(),
        status="fulfilled",
        channel="pos",
        subtotal=subtotal,
        discount=Decimal("0"),
        tax=tax_total,
        total=total,
        notes=payload.notes,
    )
    db.add(order)
    await db.flush()

    sale = PosSale(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        session_id=payload.session_id,
        sales_order_id=order.id,
        sale_number=sale_number,
        customer_id=payload.customer_id,
        subtotal=subtotal,
        tax=tax_total,
        total=total,
        payment_method=payload.payment_method,
        status="completed",
        notes=payload.notes,
    )
    db.add(sale)
    await db.flush()

    stmt = select(Warehouse).where(Warehouse.is_active.is_(True))
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Warehouse.tenant_id == user.tenant_id)
    warehouse = await db.scalar(stmt)

    for line, product, unit_price, _tax, line_total in resolved:
        db.add(
            PosSaleLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                sale_id=sale.id,
                product_id=line.product_id,
                quantity=line.quantity,
                unit_price=unit_price,
                tax_rate=product.tax_rate or 0,
                line_total=line_total,
            )
        )
        db.add(
            SalesOrderLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                order_id=order.id,
                product_id=line.product_id,
                quantity=line.quantity,
                unit_price=unit_price,
                tax_rate=product.tax_rate or 0,
                line_total=line_total,
            )
        )
        db.add(
            StockMove(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                product_id=line.product_id,
                warehouse_id=warehouse.id if warehouse else None,
                movement_type="sale",
                quantity=-line.quantity,
                unit_cost=product.purchase_price,
                reason=f"POS sale {sale_number}",
                reference=sale_number,
            )
        )

    invoice = Invoice(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        invoice_number=await next_number(db, Invoice, "invoice_number", "INV", user.tenant_id),
        customer_id=payload.customer_id,
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        status="paid",
        subtotal=subtotal,
        tax=tax_total,
        total=total,
        amount_paid=total,
        source_order_id=order.id,
    )
    db.add(invoice)
    await db.flush()
    await post_invoice_journal(db, user, invoice)

    await record_audit(
        db,
        user=user,
        action="checkout",
        module="pos",
        entity="PosSale",
        entity_id=sale.id,
        changes={"sale_number": sale_number, "total": float(total)},
        request=request,
    )
    await db.commit()
    sale = await _load_sale(db, user, sale.id)
    await publish("pos.sale.completed", {"sale_id": str(sale.id), "total": float(total)})
    return sale


@router.post("/sessions/{session_id}/close", response_model=PosSessionRead, tags=["POS · Sessions"])
async def close_session(
    session_id: UUID,
    closing_cash: Decimal = Decimal("0"),
    user: User = Depends(require_permissions("pos.session.update")),
    db: AsyncSession = Depends(get_db),
):
    session = await db.scalar(select(PosSession).where(PosSession.id == session_id))
    if session is None:
        raise NotFoundError("POS session not found")
    session.status = "closed"
    session.closed_at = datetime.now(timezone.utc)
    session.closing_cash = closing_cash
    await db.commit()
    await db.refresh(session)
    return session
