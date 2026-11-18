import math
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.numbering import next_number
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.finance.models import Invoice, InvoiceTaxLine, TaxRegistration
from app.modules.finance.service import (
    calculate_tax_snapshot,
    post_invoice_journal,
    tenant_has_gst_setup,
)
from app.modules.identity.models import User
from app.modules.inventory.models import Product
from app.modules.sales.models import Customer, DeliveryChallan, SalesOrder, SalesOrderLine
from app.modules.sales.schemas import (
    CustomerCreate,
    CustomerRead,
    CustomerUpdate,
    DeliveryChallanCreate,
    DeliveryChallanRead,
    DeliveryChallanUpdate,
    SalesOrderCreate,
    SalesOrderLineCreate,
    SalesOrderRead,
    SalesOrderUpdate,
)

router = APIRouter(prefix="/sales")


def _include(**kwargs):
    child, _ = build_crud_router(module="sales", **kwargs)
    router.include_router(child)


_include(
    model=Customer,
    read_schema=CustomerRead,
    create_schema=CustomerCreate,
    update_schema=CustomerUpdate,
    prefix="/customers",
    tags=["Sales · Customers"],
    permission_prefix="sales.customer",
    entity="Customer",
    search_fields=("name", "code", "email", "phone", "gstin"),
)

_include(
    model=DeliveryChallan,
    read_schema=DeliveryChallanRead,
    create_schema=DeliveryChallanCreate,
    update_schema=DeliveryChallanUpdate,
    prefix="/delivery-challans",
    tags=["Sales · Delivery"],
    permission_prefix="sales.deliverychallan",
    entity="DeliveryChallan",
    search_fields=("challan_number", "notes"),
    filter_fields=("order_id", "status"),
    number_field="challan_number",
    number_prefix="DC",
)

read_orders = require_permissions("sales.salesorder.read")
create_orders = require_permissions("sales.salesorder.create")
update_orders = require_permissions("sales.salesorder.update")
fulfill_orders = require_permissions("sales.order.fulfill")


async def _load_order(db: AsyncSession, user: User, order_id) -> SalesOrder:
    stmt = (
        select(SalesOrder)
        .options(selectinload(SalesOrder.customer), selectinload(SalesOrder.lines))
        .where(SalesOrder.id == order_id)
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(SalesOrder.tenant_id == user.tenant_id)
    order = await db.scalar(stmt)
    if order is None:
        raise NotFoundError("Sales order not found")
    return order


def _price_line(line: SalesOrderLineCreate) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    base = (Decimal(line.quantity) * Decimal(line.unit_price)).quantize(Decimal("0.01"))
    discount = Decimal(line.discount or 0).quantize(Decimal("0.01"))
    taxable = base - discount
    tax = (taxable * Decimal(line.tax_rate or 0) / Decimal("100")).quantize(Decimal("0.01"))
    return base, discount, tax, taxable + tax


@router.get("/orders", response_model=Page[SalesOrderRead], tags=["Sales · Orders"])
async def list_orders(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    status: Optional[str] = None,
    channel: Optional[str] = None,
    customer_id: Optional[str] = None,
    user: User = Depends(read_orders),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(SalesOrder).options(
        selectinload(SalesOrder.customer), selectinload(SalesOrder.lines)
    )
    count_stmt = select(func.count()).select_from(SalesOrder)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(SalesOrder.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(SalesOrder.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(SalesOrder.status == status)
        count_stmt = count_stmt.where(SalesOrder.status == status)
    if channel:
        stmt = stmt.where(SalesOrder.channel == channel)
        count_stmt = count_stmt.where(SalesOrder.channel == channel)
    if customer_id:
        stmt = stmt.where(SalesOrder.customer_id == customer_id)
        count_stmt = count_stmt.where(SalesOrder.customer_id == customer_id)
    if q:
        pattern = f"%{q}%"
        clause = or_(SalesOrder.order_number.ilike(pattern), SalesOrder.notes.ilike(pattern))
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(SalesOrder.order_date.desc(), SalesOrder.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


@router.post("/orders", response_model=SalesOrderRead, status_code=201, tags=["Sales · Orders"])
async def create_order(
    payload: SalesOrderCreate,
    request: Request,
    user: User = Depends(create_orders),
    db: AsyncSession = Depends(get_db),
):
    subtotal = Decimal("0")
    discount_total = Decimal("0")
    tax_total = Decimal("0")
    computed_lines = []
    gst_enabled = await tenant_has_gst_setup(db, user.tenant_id)
    tax_registration_id = payload.tax_registration_id
    place_of_supply = payload.place_of_supply_state_code
    registration = None
    if gst_enabled:
        if user.tenant_id is None:
            raise ValidationError("A tenant must be selected for GST sales")
        registration_stmt = select(TaxRegistration).where(
            TaxRegistration.tenant_id == user.tenant_id,
            TaxRegistration.is_active.is_(True),
        )
        if tax_registration_id:
            registration_stmt = registration_stmt.where(
                TaxRegistration.id == tax_registration_id
            )
        else:
            registration_stmt = registration_stmt.where(TaxRegistration.is_default.is_(True))
        registration = await db.scalar(registration_stmt)
        if registration is None and tax_registration_id is None:
            active_registrations = list(
                (
                    await db.scalars(
                        select(TaxRegistration).where(
                            TaxRegistration.tenant_id == user.tenant_id,
                            TaxRegistration.is_active.is_(True),
                        )
                    )
                ).all()
            )
            if len(active_registrations) == 1:
                registration = active_registrations[0]
        if registration is None:
            raise ValidationError("Select an active GST registration for this sales order")
        tax_registration_id = registration.id
        if place_of_supply is None and payload.customer_id is not None:
            customer = await db.scalar(
                select(Customer).where(
                    Customer.id == payload.customer_id,
                    Customer.tenant_id == user.tenant_id,
                )
            )
            if customer is None:
                raise NotFoundError("Customer not found")
            if customer.gstin:
                if len(customer.gstin) < 2 or not customer.gstin[:2].isdigit():
                    raise ValidationError("Customer GSTIN has an invalid state-code prefix")
                place_of_supply = customer.gstin[:2]
        place_of_supply = place_of_supply or registration.state_code

    for line in payload.lines:
        base = (Decimal(line.quantity) * Decimal(line.unit_price)).quantize(Decimal("0.01"))
        discount = Decimal(line.discount or 0).quantize(Decimal("0.01"))
        taxable = base - discount
        if taxable < 0:
            raise ValidationError("Line discount cannot exceed the line amount")
        tax_snapshot = None
        if gst_enabled:
            tax_code_id = line.tax_code_id
            if tax_code_id is None:
                product_stmt = select(Product).where(
                    Product.id == line.product_id,
                    Product.tenant_id == user.tenant_id,
                    Product.is_active.is_(True),
                )
                product = await db.scalar(product_stmt)
                tax_code_id = product.tax_code_id if product else None
            if tax_code_id is None:
                raise ValidationError("Select a GST tax code for every sales order line")
            tax_snapshot = await calculate_tax_snapshot(
                db,
                user.tenant_id,
                tax_code_id=tax_code_id,
                registration_id=tax_registration_id,
                place_of_supply_state_code=place_of_supply,
                taxable_amount=taxable.quantize(Decimal("0.01")),
                description=line.description,
            )
            tax = (
                tax_snapshot["cgst_amount"]
                + tax_snapshot["sgst_amount"]
                + tax_snapshot["igst_amount"]
            )
        else:
            if line.tax_code_id is not None:
                raise ValidationError("Configure a GST registration before using GST tax codes")
            _, _, tax, _ = _price_line(line)
        line_total = taxable + tax
        subtotal += base
        discount_total += discount
        tax_total += tax
        computed_lines.append((line, line_total, tax_snapshot))

    order = SalesOrder(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        order_number=await next_number(db, SalesOrder, "order_number", "SO", user.tenant_id),
        customer_id=payload.customer_id,
        order_date=payload.order_date,
        channel=payload.channel,
        status="confirmed",
        notes=payload.notes,
        warehouse_id=payload.warehouse_id,
        tax_registration_id=tax_registration_id,
        place_of_supply_state_code=place_of_supply,
        subtotal=subtotal,
        discount=discount_total,
        tax=tax_total,
        total=subtotal - discount_total + tax_total,
    )
    db.add(order)
    await db.flush()
    for line, line_total, tax_snapshot in computed_lines:
        db.add(
            SalesOrderLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                order_id=order.id,
                product_id=line.product_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                discount=line.discount,
                tax_rate=(
                    tax_snapshot["cgst_rate"]
                    + tax_snapshot["sgst_rate"]
                    + tax_snapshot["igst_rate"]
                    if tax_snapshot
                    else line.tax_rate
                ),
                tax_code_id=tax_snapshot["tax_code_id"] if tax_snapshot else line.tax_code_id,
                cgst_amount=tax_snapshot["cgst_amount"] if tax_snapshot else Decimal("0"),
                sgst_amount=tax_snapshot["sgst_amount"] if tax_snapshot else Decimal("0"),
                igst_amount=tax_snapshot["igst_amount"] if tax_snapshot else Decimal("0"),
                cgst_rate_snapshot=tax_snapshot["cgst_rate"] if tax_snapshot else Decimal("0"),
                sgst_rate_snapshot=tax_snapshot["sgst_rate"] if tax_snapshot else Decimal("0"),
                igst_rate_snapshot=tax_snapshot["igst_rate"] if tax_snapshot else Decimal("0"),
                tax_type_snapshot=tax_snapshot["tax_type_snapshot"] if tax_snapshot else None,
                can_claim_itc_snapshot=tax_snapshot["can_claim_itc_snapshot"] if tax_snapshot else None,
                output_cgst_account_id=tax_snapshot["output_cgst_account_id"] if tax_snapshot else None,
                output_sgst_account_id=tax_snapshot["output_sgst_account_id"] if tax_snapshot else None,
                output_igst_account_id=tax_snapshot["output_igst_account_id"] if tax_snapshot else None,
                line_total=line_total,
            )
        )
    await record_audit(
        db,
        user=user,
        action="create",
        module="sales",
        entity="SalesOrder",
        entity_id=order.id,
        changes={"order_number": order.order_number, "total": float(order.total)},
        request=request,
    )
    await db.commit()
    order = await _load_order(db, user, order.id)
    await publish("order.created", {"order_id": str(order.id), "total": float(order.total)})
    return order


@router.get("/orders/{order_id}", response_model=SalesOrderRead, tags=["Sales · Orders"])
async def get_order(
    order_id: UUID,
    user: User = Depends(read_orders),
    db: AsyncSession = Depends(get_db),
):
    return await _load_order(db, user, order_id)


@router.patch("/orders/{order_id}", response_model=SalesOrderRead, tags=["Sales · Orders"])
async def update_order(
    order_id: UUID,
    payload: SalesOrderUpdate,
    user: User = Depends(update_orders),
    db: AsyncSession = Depends(get_db),
):
    order = await _load_order(db, user, order_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(order, field, value)
    await db.commit()
    return await _load_order(db, user, order.id)


@router.post("/orders/{order_id}/fulfill", response_model=SalesOrderRead, tags=["Sales · Orders"])
async def fulfill_order(
    order_id: UUID,
    request: Request,
    user: User = Depends(fulfill_orders),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.inventory.models import Product, StockMove
    from app.modules.warehouse.models import Warehouse

    order = await _load_order(db, user, order_id)
    if order.status in {"fulfilled", "cancelled"}:
        raise ConflictError(f"Order is already {order.status}")

    warehouse_id = order.warehouse_id
    if warehouse_id is None:
        stmt = select(Warehouse).where(Warehouse.is_active.is_(True))
        if not user.is_superuser and user.tenant_id:
            stmt = stmt.where(Warehouse.tenant_id == user.tenant_id)
        warehouse = await db.scalar(stmt)
        warehouse_id = warehouse.id if warehouse else None

    for line in order.lines:
        product = await db.get(Product, line.product_id)
        db.add(
            StockMove(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                product_id=line.product_id,
                warehouse_id=warehouse_id,
                movement_type="sale",
                quantity=-line.quantity,
                unit_cost=product.purchase_price if product else Decimal("0"),
                reason=f"Sales order {order.order_number}",
                reference=order.order_number,
            )
        )

    order.status = "fulfilled"
    db.add(
        DeliveryChallan(
            tenant_id=user.tenant_id,
            created_by_id=user.id,
            challan_number=await next_number(db, DeliveryChallan, "challan_number", "DC", user.tenant_id),
            order_id=order.id,
            dispatched_date=date.today(),
            warehouse_id=warehouse_id,
        )
    )

    invoice = Invoice(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        invoice_number=await next_number(db, Invoice, "invoice_number", "INV", user.tenant_id),
        customer_id=order.customer_id,
        issue_date=date.today(),
        due_date=date.today() + timedelta(days=30),
        status="sent",
        subtotal=order.subtotal,
        tax=order.tax,
        total=order.total,
        source_order_id=order.id,
    )
    db.add(invoice)
    await db.flush()
    for order_line in order.lines:
        if order_line.tax_code_id is None:
            continue
        db.add(
            InvoiceTaxLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                invoice_id=invoice.id,
                tax_code_id=order_line.tax_code_id,
                tax_type_snapshot=order_line.tax_type_snapshot or "taxable",
                can_claim_itc_snapshot=order_line.can_claim_itc_snapshot or False,
                registration_id=order.tax_registration_id,
                description=order_line.description,
                place_of_supply_state_code=order.place_of_supply_state_code,
                taxable_amount=(
                    order_line.quantity * order_line.unit_price - order_line.discount
                ).quantize(Decimal("0.01")),
                cgst_rate=order_line.cgst_rate_snapshot,
                sgst_rate=order_line.sgst_rate_snapshot,
                igst_rate=order_line.igst_rate_snapshot,
                cgst_amount=order_line.cgst_amount,
                sgst_amount=order_line.sgst_amount,
                igst_amount=order_line.igst_amount,
                output_cgst_account_id=order_line.output_cgst_account_id,
                output_sgst_account_id=order_line.output_sgst_account_id,
                output_igst_account_id=order_line.output_igst_account_id,
            )
        )
    await post_invoice_journal(db, user, invoice)

    await record_audit(
        db,
        user=user,
        action="fulfill",
        module="sales",
        entity="SalesOrder",
        entity_id=order.id,
        changes={"invoice": invoice.invoice_number},
        request=request,
    )
    await db.commit()
    order = await _load_order(db, user, order.id)
    await publish(
        "order.fulfilled",
        {"order_id": str(order.id), "invoice_id": str(invoice.id), "total": float(order.total)},
    )
    return order
