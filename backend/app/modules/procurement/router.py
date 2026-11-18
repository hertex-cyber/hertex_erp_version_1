import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.events import publish
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.numbering import next_number
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.finance.service import (
    calculate_tax_snapshot,
    post_goods_receipt_accrual,
    post_vendor_invoice_journal,
    tax_line_totals,
)
from app.modules.identity.models import User
from app.modules.procurement.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    POLine,
    PurchaseOrder,
    PurchaseRequisition,
    Vendor,
    VendorInvoice,
    VendorInvoiceTaxLine,
)
from app.modules.procurement.schemas import (
    GoodsReceiptCreate,
    GoodsReceiptRead,
    PurchaseOrderCreate,
    PurchaseOrderRead,
    RequisitionCreate,
    RequisitionRead,
    RequisitionUpdate,
    VendorCreate,
    VendorInvoiceCreate,
    VendorInvoiceRead,
    VendorInvoiceTaxLineRead,
    VendorInvoiceTaxLinesUpdate,
    VendorInvoiceUpdate,
    VendorRead,
    VendorUpdate,
)

router = APIRouter(prefix="/procurement")


def _include(**kwargs):
    child, _ = build_crud_router(module="procurement", **kwargs)
    router.include_router(child)


_include(
    model=Vendor,
    read_schema=VendorRead,
    create_schema=VendorCreate,
    update_schema=VendorUpdate,
    prefix="/vendors",
    tags=["Procurement · Vendors"],
    permission_prefix="procurement.vendor",
    entity="Vendor",
    search_fields=("name", "code", "email", "gstin"),
)

_include(
    model=PurchaseRequisition,
    read_schema=RequisitionRead,
    create_schema=RequisitionCreate,
    update_schema=RequisitionUpdate,
    prefix="/requisitions",
    tags=["Procurement · Requisitions"],
    permission_prefix="procurement.requisition",
    entity="PurchaseRequisition",
    search_fields=("requisition_number", "department", "notes"),
    filter_fields=("status", "department"),
    number_field="requisition_number",
    number_prefix="PR",
)

_include(
    model=VendorInvoice,
    read_schema=VendorInvoiceRead,
    create_schema=VendorInvoiceCreate,
    update_schema=VendorInvoiceUpdate,
    prefix="/vendor-invoices",
    tags=["Procurement · Vendor Invoices"],
    permission_prefix="procurement.vendorinvoice",
    entity="VendorInvoice",
    search_fields=("invoice_number", "notes"),
    filter_fields=("status", "vendor_id", "purchase_order_id"),
)

read_pos = require_permissions("procurement.purchaseorder.read")
create_pos = require_permissions("procurement.purchaseorder.create")
update_pos = require_permissions("procurement.purchaseorder.update")


async def _load_po(
    db: AsyncSession, user: User, po_id, *, for_update: bool = False
) -> PurchaseOrder:
    stmt = (
        select(PurchaseOrder)
        .options(selectinload(PurchaseOrder.vendor), selectinload(PurchaseOrder.lines))
        .where(PurchaseOrder.id == po_id)
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(PurchaseOrder.tenant_id == user.tenant_id)
    if for_update:
        stmt = stmt.with_for_update()
    po = await db.scalar(stmt)
    if po is None:
        raise NotFoundError("Purchase order not found")
    return po


@router.get("/purchase-orders", response_model=Page[PurchaseOrderRead], tags=["Procurement · Purchase Orders"])
async def list_purchase_orders(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    vendor_id: Optional[str] = None,
    user: User = Depends(read_pos),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(PurchaseOrder).options(
        selectinload(PurchaseOrder.vendor), selectinload(PurchaseOrder.lines)
    )
    count_stmt = select(func.count()).select_from(PurchaseOrder)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(PurchaseOrder.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(PurchaseOrder.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(PurchaseOrder.status == status)
        count_stmt = count_stmt.where(PurchaseOrder.status == status)
    if vendor_id:
        stmt = stmt.where(PurchaseOrder.vendor_id == vendor_id)
        count_stmt = count_stmt.where(PurchaseOrder.vendor_id == vendor_id)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(PurchaseOrder.order_date.desc()).offset((page - 1) * size).limit(size)
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


@router.post("/purchase-orders", response_model=PurchaseOrderRead, status_code=201, tags=["Procurement · Purchase Orders"])
async def create_purchase_order(
    payload: PurchaseOrderCreate,
    request: Request,
    user: User = Depends(create_pos),
    db: AsyncSession = Depends(get_db),
):
    subtotal = sum((line.quantity * line.unit_price for line in payload.lines), Decimal("0"))
    po = PurchaseOrder(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        po_number=await next_number(db, PurchaseOrder, "po_number", "PO", user.tenant_id),
        vendor_id=payload.vendor_id,
        requisition_id=payload.requisition_id,
        order_date=payload.order_date,
        expected_date=payload.expected_date,
        status="pending_approval",
        subtotal=subtotal,
        tax=Decimal("0"),
        total=subtotal,
        notes=payload.notes,
    )
    db.add(po)
    await db.flush()
    for line in payload.lines:
        db.add(
            POLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                order_id=po.id,
                product_id=line.product_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                line_total=line.quantity * line.unit_price,
            )
        )
    await record_audit(
        db,
        user=user,
        action="create",
        module="procurement",
        entity="PurchaseOrder",
        entity_id=po.id,
        changes={"po_number": po.po_number, "total": float(po.total)},
        request=request,
    )
    await db.commit()
    return await _load_po(db, user, po.id)


@router.post("/purchase-orders/{po_id}/approve", response_model=PurchaseOrderRead, tags=["Procurement · Purchase Orders"])
async def approve_purchase_order(
    po_id: UUID,
    request: Request,
    user: User = Depends(require_permissions("procurement.po.approve")),
    db: AsyncSession = Depends(get_db),
):
    po = await _load_po(db, user, po_id)
    if po.status == "approved":
        return po
    limits = [role.approval_limit for role in user.roles if role.approval_limit is not None]
    if not user.is_superuser and limits:
        max_limit = max(Decimal(str(limit)) for limit in limits)
        if po.total > max_limit:
            raise ForbiddenError(f"Approval limit is {max_limit}; order total is {po.total}")
    po.status = "approved"
    po.approved_by_id = user.id
    po.approved_at = datetime.now(timezone.utc)
    await record_audit(
        db,
        user=user,
        action="approve",
        module="procurement",
        entity="PurchaseOrder",
        entity_id=po.id,
        request=request,
    )
    await db.commit()
    po = await _load_po(db, user, po.id)
    await publish("po.approved", {"po_id": str(po.id)})
    return po


@router.post("/purchase-orders/{po_id}/receive", response_model=GoodsReceiptRead, tags=["Procurement · Goods Receipt"])
async def receive_purchase_order(
    po_id: UUID,
    payload: GoodsReceiptCreate,
    request: Request,
    user: User = Depends(require_permissions("procurement.grn.create")),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.inventory.models import StockMove
    from app.modules.warehouse.models import Warehouse

    po = await _load_po(db, user, po_id, for_update=True)
    if po.status not in {"approved", "received", "partially_received"}:
        raise ConflictError("Purchase order must be approved before receiving")
    if all(line.received_quantity >= line.quantity for line in po.lines):
        raise ConflictError("All purchase order quantities have already been received")

    grn = GoodsReceipt(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        grn_number=await next_number(db, GoodsReceipt, "grn_number", "GRN", user.tenant_id),
        purchase_order_id=po.id,
        received_date=payload.received_date,
        received_by_id=user.id,
        notes=payload.notes,
    )
    db.add(grn)
    await db.flush()

    stmt = select(Warehouse).where(Warehouse.is_active.is_(True))
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Warehouse.tenant_id == user.tenant_id)
    warehouse = await db.scalar(stmt)

    fully_received = True
    for line in po.lines:
        remaining = line.quantity - line.received_quantity
        if remaining <= 0:
            continue
        db.add(
            GoodsReceiptLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                grn_id=grn.id,
                po_line_id=line.id,
                quantity_received=remaining,
            )
        )
        line.received_quantity = line.quantity
        db.add(
            StockMove(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                product_id=line.product_id,
                warehouse_id=warehouse.id if warehouse else None,
                movement_type="receipt",
                quantity=remaining,
                unit_cost=line.unit_price,
                reason=f"GRN {grn.grn_number}",
                reference=po.po_number,
            )
        )
    for line in po.lines:
        if line.received_quantity < line.quantity:
            fully_received = False
    po.status = "received" if fully_received else "partially_received"
    await post_goods_receipt_accrual(db, user, grn)

    await record_audit(
        db,
        user=user,
        action="receive",
        module="procurement",
        entity="GoodsReceipt",
        entity_id=grn.id,
        changes={"po_number": po.po_number},
        request=request,
    )
    await db.commit()
    await db.refresh(grn)
    await publish("grn.received", {"grn_id": str(grn.id), "po_id": str(po.id)})
    return grn


@router.post("/vendor-invoices/{invoice_id}/approve", response_model=VendorInvoiceRead, tags=["Procurement · Vendor Invoices"])
async def approve_vendor_invoice(
    invoice_id: UUID,
    request: Request,
    user: User = Depends(require_permissions("procurement.vendorinvoice.update")),
    db: AsyncSession = Depends(get_db),
):
    invoice_stmt = select(VendorInvoice).where(VendorInvoice.id == invoice_id).with_for_update()
    invoice = await db.scalar(invoice_stmt)
    if invoice is None:
        raise NotFoundError("Vendor invoice not found")
    if not user.is_superuser and invoice.tenant_id != user.tenant_id:
        raise NotFoundError("Vendor invoice not found")
    if invoice.status == "approved":
        return invoice
    if invoice.purchase_order_id is None:
        raise ConflictError("Vendor invoice must reference a purchase order for three-way matching")

    po = await _load_po(db, user, invoice.purchase_order_id, for_update=True)
    total_received = Decimal("0")
    total_ordered = Decimal("0")
    for line in po.lines:
        total_received += line.received_quantity
        total_ordered += line.quantity
    if total_received < total_ordered * Decimal("0.99"):
        raise ConflictError("Three-way match failed: goods not fully received against the purchase order")

    invoice_total = invoice.amount
    tolerance = po.total * Decimal("0.05")
    if abs(invoice_total - po.total) > tolerance:
        raise ConflictError(
            f"Three-way match failed: invoice taxable base {invoice_total} does not match PO total {po.total}"
        )

    invoice.status = "approved"
    await post_vendor_invoice_journal(db, user, invoice)

    await record_audit(
        db,
        user=user,
        action="approve",
        module="procurement",
        entity="VendorInvoice",
        entity_id=invoice.id,
        changes={"invoice_number": invoice.invoice_number},
        request=request,
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice


@router.put(
    "/vendor-invoices/{invoice_id}/tax-lines",
    response_model=list[VendorInvoiceTaxLineRead],
    tags=["Procurement · Vendor Invoices"],
)
async def replace_vendor_invoice_tax_lines(
    invoice_id: UUID,
    payload: VendorInvoiceTaxLinesUpdate,
    request: Request,
    user: User = Depends(require_permissions("procurement.vendorinvoice.update")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(VendorInvoice).where(VendorInvoice.id == invoice_id).with_for_update()
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(VendorInvoice.tenant_id == user.tenant_id)
    invoice = await db.scalar(stmt)
    if invoice is None:
        raise NotFoundError("Vendor invoice not found")
    if invoice.status != "pending":
        raise ConflictError("GST lines can only be changed on a pending vendor invoice")

    tax_lines = []
    for line in payload.lines:
        values = await calculate_tax_snapshot(
            db,
            invoice.tenant_id,
            tax_code_id=line.tax_code_id,
            registration_id=line.registration_id,
            place_of_supply_state_code=line.place_of_supply_state_code,
            taxable_amount=line.taxable_amount,
            description=line.description,
        )
        tax_lines.append(
            VendorInvoiceTaxLine(
                tenant_id=invoice.tenant_id,
                created_by_id=user.id,
                invoice_id=invoice.id,
                **{
                    key: value
                    for key, value in values.items()
                    if not key.startswith("output_")
                },
            )
        )
    base, tax = tax_line_totals(tax_lines)
    if base != invoice.amount:
        raise ValidationError(
            f"GST taxable lines total {base} must equal the vendor invoice amount {invoice.amount}"
        )
    invoice.tax_amount = tax
    await db.execute(
        delete(VendorInvoiceTaxLine).where(VendorInvoiceTaxLine.invoice_id == invoice.id)
    )
    db.add_all(tax_lines)
    await record_audit(
        db,
        user=user,
        action="replace_tax_lines",
        module="procurement",
        entity="VendorInvoice",
        entity_id=invoice.id,
        changes={
            "tax_line_count": len(tax_lines),
            "taxable_amount": str(base),
            "tax_amount": str(tax),
        },
        request=request,
    )
    await db.commit()
    return tax_lines
