"""Finance compliance, integration, dimension and extended-reporting API."""

import hashlib
from datetime import date
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.finance.compliance_models import (
    BankFeed,
    BankFeedImport,
    Branch,
    Budget,
    BudgetLine,
    CostCenter,
    EInvoice,
    EWaybill,
    FinanceAuditLog,
    FinanceDepartment,
    GstReturn,
    IntercompanyTransaction,
    LegalEntity,
    OutboxEvent,
    SourceEvent,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.modules.finance.compliance_schemas import (
    AssetImpairmentCreate,
    AssetWriteOffCreate,
    BankFeedCreate,
    BankFeedImportResult,
    BankFeedRead,
    BudgetCreate,
    BudgetLineCreate,
    BudgetRead,
    DimensionUpdate,
    DispatchResult,
    EInvoiceCancel,
    EInvoiceGenerate,
    EWaybillCreate,
    GstReturnBuild,
    GstReturnFile,
    GstReturnRead,
    IntercompanyCreate,
    IntercompanyRead,
    LegalEntityCreate,
    LegalEntityRead,
    LegalEntityUpdate,
    NamedDimensionCreate,
    NamedDimensionRead,
    OutboxEventRead,
    WebhookEndpointCreate,
    WebhookEndpointRead,
    WebhookEndpointUpdate,
)
from app.modules.finance.compliance_service import (
    asset_register_report,
    bank_reconciliation_report,
    budget_vs_actual,
    build_gst_return,
    cancel_e_invoice,
    consolidation_report,
    dimension_report,
    eliminate_intercompany_transaction,
    file_gst_return,
    general_ledger,
    generate_e_invoice,
    generate_e_waybill,
    impair_fixed_asset,
    import_bank_feed,
    payroll_cost_report,
    post_intercompany_transaction,
    reconcile_itc,
    write_off_fixed_asset,
)
from app.modules.finance.control_service import (
    claim_source_event,
    dispatch_outbox,
    retry_dead_letter,
    verify_signature,
)
from app.modules.finance.models import FixedAsset
from app.modules.identity.models import User
from app.modules.settings.numbering import document_number

router = APIRouter(prefix="/finance")

read_reports = require_permissions("finance.report.read")
read_control = require_permissions("finance.financeaudit.read")
dispatch_control = require_permissions("finance.outbox.dispatch")
retry_control = require_permissions("finance.outbox.retry")
read_feeds = require_permissions("finance.bankfeed.read")
write_feeds = require_permissions("finance.bankfeed.create")
read_gst = require_permissions("finance.gstreturn.read")
write_gst = require_permissions("finance.gstreturn.create")
file_gst = require_permissions("finance.gstreturn.file")
read_einv = require_permissions("finance.einvoice.read")
write_einv = require_permissions("finance.einvoice.generate")
read_ic = require_permissions("finance.intercompany.read")
write_ic = require_permissions("finance.intercompany.create")
read_budget = require_permissions("finance.budget.read")
write_budget = require_permissions("finance.budget.create")
read_asset = require_permissions("finance.asset.read")
write_asset = require_permissions("finance.asset.update")


def _scope(stmt, model, user: User):
    if not user.is_superuser and user.tenant_id:
        return stmt.where(model.tenant_id == user.tenant_id)
    return stmt


def _paged(items, total: int, page: int, size: int) -> dict:
    import math

    return {"items": items, "total": total, "page": page, "size": size, "pages": max(1, math.ceil(total / size))}



@router.get("/control/audit", response_model=Page[dict], tags=["Finance · Controls"])
async def list_finance_audit(
    request: Request,
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_control),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    stmt = _scope(select(FinanceAuditLog), FinanceAuditLog, user).order_by(FinanceAuditLog.created_at.desc())
    count = _scope(select(func.count()).select_from(FinanceAuditLog), FinanceAuditLog, user)
    total = int((await db.scalar(count)) or 0)
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    items = [
        {
            "id": str(row.id),
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id) if row.entity_id else None,
            "action": row.action,
            "actor_email": row.actor_email,
            "actor_role": row.actor_role,
            "before_state": row.before_state,
            "after_state": row.after_state,
            "reason": row.reason,
            "correlation_id": row.correlation_id,
            "created_at": row.created_at.isoformat(),
        }
        for row in rows
    ]
    return _paged(items, total, page, size)


@router.get("/control/source-events", response_model=Page[dict], tags=["Finance · Controls"])
async def list_source_events(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_control),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int((await db.scalar(_scope(select(func.count()).select_from(SourceEvent), SourceEvent, user))) or 0)
    stmt = _scope(select(SourceEvent), SourceEvent, user).order_by(SourceEvent.created_at.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(
        [
            {
                "id": str(row.id),
                "event_type": row.event_type,
                "source_module": row.source_module,
                "idempotency_key": row.idempotency_key,
                "status": row.status,
                "attempts": row.attempts,
                "result_reference": row.result_reference,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ],
        total,
        page,
        size,
    )


@router.get("/control/outbox", response_model=Page[OutboxEventRead], tags=["Finance · Controls"])
async def list_outbox(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_control),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int((await db.scalar(_scope(select(func.count()).select_from(OutboxEvent), OutboxEvent, user))) or 0)
    stmt = _scope(select(OutboxEvent), OutboxEvent, user).order_by(OutboxEvent.created_at.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(list(rows), total, page, size)


@router.post("/control/outbox/dispatch", response_model=DispatchResult, tags=["Finance · Controls"])
async def dispatch_finance_outbox(
    limit: int = 50,
    force: bool = False,
    user: User = Depends(dispatch_control),
    db: AsyncSession = Depends(get_db),
):
    if not user.is_superuser:
        raise ConflictError("Outbox dispatch requires a system administrator")
    result = await dispatch_outbox(db, limit=limit, force=force)
    await record_audit(db, user=user, action="dispatch", module="finance", entity="outbox", changes=result)
    await db.commit()
    return DispatchResult(**result)


@router.post("/control/outbox/{event_id}/retry", tags=["Finance · Controls"])
async def retry_outbox_event(
    event_id: UUID,
    user: User = Depends(retry_control),
    db: AsyncSession = Depends(get_db),
):
    result = await retry_dead_letter(db, event_id=event_id, user=user)
    await db.commit()
    return result


child, _ = build_crud_router(
    model=WebhookEndpoint,
    read_schema=WebhookEndpointRead,
    create_schema=WebhookEndpointCreate,
    update_schema=WebhookEndpointUpdate,
    prefix="/control/webhooks",
    tags=["Finance · Controls"],
    permission_prefix="finance.webhook",
    module="finance",
    entity="webhook_endpoint",
    search_fields=("name",),
    serializer=lambda obj, user: {
        "id": str(obj.id),
        "name": obj.name,
        "url": obj.url,
        "event_types": obj.event_types,
        "is_enabled": obj.is_enabled,
        "created_at": obj.created_at.isoformat(),
    },
)
router.include_router(child)


@router.get("/control/webhook-deliveries", response_model=Page[dict], tags=["Finance · Controls"])
async def list_webhook_deliveries(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_control),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int(
        (await db.scalar(_scope(select(func.count()).select_from(WebhookDelivery), WebhookDelivery, user))) or 0
    )
    stmt = _scope(select(WebhookDelivery), WebhookDelivery, user).order_by(WebhookDelivery.created_at.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(
        [
            {
                "id": str(row.id),
                "endpoint_id": str(row.endpoint_id),
                "outbox_event_id": str(row.outbox_event_id),
                "status": row.status,
                "attempts": row.attempts,
                "response_status": row.response_status,
                "last_error": row.last_error,
            }
            for row in rows
        ],
        total,
        page,
        size,
    )



@router.post("/gst/returns/build", response_model=GstReturnRead, tags=["Finance · GST Statutory"])
async def build_return(
    payload: GstReturnBuild,
    user: User = Depends(write_gst),
    db: AsyncSession = Depends(get_db),
):
    result = await build_gst_return(
        db,
        user,
        registration_id=payload.registration_id,
        return_type=payload.return_type,
        filing_period=payload.filing_period,
    )
    await db.commit()
    return result


@router.get("/gst/returns", response_model=Page[GstReturnRead], tags=["Finance · GST Statutory"])
async def list_returns(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_gst),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int((await db.scalar(_scope(select(func.count()).select_from(GstReturn), GstReturn, user))) or 0)
    stmt = _scope(select(GstReturn), GstReturn, user).order_by(GstReturn.filing_period.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(list(rows), total, page, size)


@router.get("/gst/returns/{return_id}", response_model=GstReturnRead, tags=["Finance · GST Statutory"])
async def get_return(
    return_id: UUID,
    user: User = Depends(read_gst),
    db: AsyncSession = Depends(get_db),
):
    record = await db.scalar(_scope(select(GstReturn).where(GstReturn.id == return_id), GstReturn, user))
    if record is None:
        raise NotFoundError("GST return not found")
    return record


@router.post("/gst/returns/{return_id}/file", response_model=GstReturnRead, tags=["Finance · GST Statutory"])
async def file_return(
    return_id: UUID,
    payload: GstReturnFile,
    user: User = Depends(file_gst),
    db: AsyncSession = Depends(get_db),
):
    result = await file_gst_return(db, user, return_id, acknowledgement_number=payload.acknowledgement_number)
    await db.commit()
    return result


@router.post("/gst/itc/reconcile", response_model=Page[dict], tags=["Finance · GST Statutory"])
async def reconcile_input_tax_credit(
    filing_period: str,
    user: User = Depends(write_gst),
    db: AsyncSession = Depends(get_db),
):
    records = await reconcile_itc(db, user, filing_period=filing_period)
    await db.commit()
    return _paged(
        [
            {
                "id": str(row.id),
                "filing_period": row.filing_period,
                "registration_id": str(row.registration_id) if row.registration_id else None,
                "source_document_id": str(row.source_document_id),
                "tax_code_id": str(row.tax_code_id) if row.tax_code_id else None,
                "taxable_amount": str(row.taxable_amount),
                "invoice_tax": str(row.invoice_tax),
                "posted_itc": str(row.posted_itc),
                "difference": str(row.difference),
                "status": row.status,
            }
            for row in records
        ],
        len(records),
        1,
        max(len(records), 1),
    )


@router.post("/e-invoices/generate", tags=["Finance · E-Invoice"])
async def generate_invoice(payload: EInvoiceGenerate, user: User = Depends(write_einv), db: AsyncSession = Depends(get_db)):
    result = await generate_e_invoice(db, user, payload.invoice_id)
    await db.commit()
    return result


@router.get("/e-invoices", response_model=Page[dict], tags=["Finance · E-Invoice"])
async def list_e_invoices(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_einv),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int((await db.scalar(_scope(select(func.count()).select_from(EInvoice), EInvoice, user))) or 0)
    stmt = _scope(select(EInvoice), EInvoice, user).order_by(EInvoice.created_at.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(
        [
            {
                "id": str(row.id),
                "invoice_id": str(row.invoice_id),
                "irn": row.irn,
                "status": row.status,
                "acknowledgement_number": row.acknowledgement_number,
                "qr_payload": row.qr_payload,
            }
            for row in rows
        ],
        total,
        page,
        size,
    )


@router.post("/e-invoices/{e_invoice_id}/cancel", tags=["Finance · E-Invoice"])
async def cancel_invoice(
    e_invoice_id: UUID,
    payload: EInvoiceCancel,
    user: User = Depends(write_einv),
    db: AsyncSession = Depends(get_db),
):
    result = await cancel_e_invoice(db, user, e_invoice_id, reason=payload.reason)
    await db.commit()
    return result


@router.post("/e-waybills", tags=["Finance · E-Invoice"])
async def create_waybill(
    payload: EWaybillCreate,
    user: User = Depends(write_einv),
    db: AsyncSession = Depends(get_db),
):
    result = await generate_e_waybill(
        db,
        user,
        invoice_id=payload.invoice_id,
        transport_mode=payload.transport_mode,
        valid_days=payload.valid_days,
    )
    await db.commit()
    return result


@router.get("/e-waybills", response_model=Page[dict], tags=["Finance · E-Invoice"])
async def list_waybills(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_einv),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int((await db.scalar(_scope(select(func.count()).select_from(EWaybill), EWaybill, user))) or 0)
    stmt = _scope(select(EWaybill), EWaybill, user).order_by(EWaybill.created_at.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(
        [
            {
                "id": str(row.id),
                "invoice_id": str(row.invoice_id),
                "waybill_number": row.waybill_number,
                "status": row.status,
                "valid_until": row.valid_until.isoformat() if row.valid_until else None,
            }
            for row in rows
        ],
        total,
        page,
        size,
    )



@router.get("/bank-feeds", response_model=Page[BankFeedRead], tags=["Finance · Bank Feeds"])
async def list_feeds(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_feeds),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int((await db.scalar(_scope(select(func.count()).select_from(BankFeed), BankFeed, user))) or 0)
    stmt = _scope(select(BankFeed), BankFeed, user).order_by(BankFeed.created_at.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(list(rows), total, page, size)


@router.post("/bank-feeds", response_model=BankFeedRead, status_code=201, tags=["Finance · Bank Feeds"])
async def create_feed(
    payload: BankFeedCreate,
    user: User = Depends(write_feeds),
    db: AsyncSession = Depends(get_db),
):
    feed = BankFeed(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        **payload.model_dump(),
    )
    db.add(feed)
    await record_audit(
        db, user=user, action="create", module="finance", entity="bank_feed",
        entity_id=feed.id, changes={"name": payload.name, "provider": payload.provider},
    )
    await db.flush()
    await db.commit()
    return feed


@router.post("/bank-feeds/{feed_id}/import", response_model=BankFeedImportResult, tags=["Finance · Bank Feeds"])
async def import_feed(
    feed_id: UUID,
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(write_feeds),
    db: AsyncSession = Depends(get_db),
):
    feed = await db.scalar(_scope(select(BankFeed).where(BankFeed.id == feed_id), BankFeed, user))
    if feed is None:
        raise NotFoundError("Bank feed not found")
    if not feed.is_enabled:
        raise ConflictError("Bank feed is disabled")
    content = (await file.read(10 * 1024 * 1024 + 1)).decode("utf-8-sig")
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    idempotency = request.headers.get("idempotency-key") or f"feed-import:{feed_id}:{digest}"
    event, created = await claim_source_event(
        db,
        user=user,
        event_type="bank_feed.import",
        source_module="finance",
        idempotency_key=idempotency,
        source_document_type="bank_feed",
        source_document_id=feed.id,
        payload={"file_name": file.filename, "provider": feed.provider},
    )
    if not created:
        return BankFeedImportResult(
            import_id=event.result_reference or "duplicate",
            status="duplicate",
            row_count=0,
            imported_count=0,
            duplicate_count=0,
        )
    result = await import_bank_feed(db, user, feed=feed, content=content, file_name=file.filename, source_event=event)
    await db.commit()
    return BankFeedImportResult(**result)


@router.post("/bank-feeds/{feed_id}/webhook", tags=["Finance · Bank Feeds"])
async def receive_bank_feed_webhook(
    feed_id: UUID,
    request: Request,
    user: User = Depends(write_feeds),
    db: AsyncSession = Depends(get_db),
):
    feed = await db.scalar(_scope(select(BankFeed).where(BankFeed.id == feed_id), BankFeed, user))
    if feed is None or feed.provider != "webhook" or not feed.webhook_secret:
        raise NotFoundError("Signed bank webhook feed not found")
    body = await request.body()
    if not verify_signature(feed.webhook_secret, body, request.headers.get("x-hertex-signature")):
        raise ValidationError("Invalid bank feed webhook signature")
    signature_key = request.headers.get("x-hertex-event-id") or hashlib.sha256(body).hexdigest()
    event, created = await claim_source_event(
        db,
        user=user,
        event_type="bank_feed.webhook",
        source_module="finance",
        idempotency_key=f"bank-webhook:{feed_id}:{signature_key}",
        source_document_type="bank_feed",
        source_document_id=feed.id,
        payload={"bytes": len(body)},
    )
    if not created:
        return {"status": "duplicate", "source_event_id": str(event.id)}
    result = await import_bank_feed(
        db, user, feed=feed, content=body.decode("utf-8"), file_name="webhook.csv", source_event=event
    )
    await db.commit()
    return result


@router.get("/bank-feed-imports", response_model=Page[dict], tags=["Finance · Bank Feeds"])
async def list_feed_imports(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_feeds),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int((await db.scalar(_scope(select(func.count()).select_from(BankFeedImport), BankFeedImport, user))) or 0)
    stmt = _scope(select(BankFeedImport), BankFeedImport, user).order_by(BankFeedImport.created_at.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(
        [
            {
                "id": str(row.id),
                "feed_id": str(row.feed_id),
                "status": row.status,
                "row_count": row.row_count,
                "imported_count": row.imported_count,
                "duplicate_count": row.duplicate_count,
                "file_name": row.file_name,
            }
            for row in rows
        ],
        total,
        page,
        size,
    )


for _model, _path, _perm, _entity, _search in (
    (LegalEntity, "/legal-entities", "finance.legalentity", "legal_entity", ("code", "name")),
    (Branch, "/branches", "finance.branch", "branch", ("code", "name")),
    (CostCenter, "/cost-centers", "finance.costcenter", "cost_center", ("code", "name")),
    (FinanceDepartment, "/departments", "finance.department", "department", ("code", "name")),
):
    child, _ = build_crud_router(
        model=_model,
        read_schema=LegalEntityRead if _model is LegalEntity else NamedDimensionRead,
        create_schema=LegalEntityCreate if _model is LegalEntity else NamedDimensionCreate,
        update_schema=LegalEntityUpdate if _model is LegalEntity else DimensionUpdate,
        prefix=_path,
        tags=["Finance · Dimensions"],
        permission_prefix=_perm,
        module="finance",
        entity=_entity,
        search_fields=_search,
        serializer=lambda obj, user: {
            "id": str(obj.id),
            "code": obj.code,
            "name": obj.name,
            "legal_entity_id": str(obj.legal_entity_id) if getattr(obj, "legal_entity_id", None) else None,
            "gstin": getattr(obj, "gstin", None),
            "parent_id": str(obj.parent_id) if getattr(obj, "parent_id", None) else None,
            "created_at": obj.created_at.isoformat(),
        },
    )
    router.include_router(child)


@router.get("/intercompany", response_model=Page[IntercompanyRead], tags=["Finance · Consolidation"])
async def list_intercompany(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_ic),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int(
        (await db.scalar(_scope(select(func.count()).select_from(IntercompanyTransaction), IntercompanyTransaction, user)))
        or 0
    )
    stmt = _scope(select(IntercompanyTransaction), IntercompanyTransaction, user).order_by(
        IntercompanyTransaction.created_at.desc()
    )
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(list(rows), total, page, size)


@router.post("/intercompany", response_model=IntercompanyRead, status_code=201, tags=["Finance · Consolidation"])
async def create_intercompany(
    payload: IntercompanyCreate,
    user: User = Depends(write_ic),
    db: AsyncSession = Depends(get_db),
):
    number = await document_number(
        db,
        key="intercompany",
        tenant_id=user.tenant_id,
        user=user,
        on_date=payload.transaction_date,
        document_type="intercompany_transaction",
    )
    record = IntercompanyTransaction(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        number=number,
        **payload.model_dump(),
    )
    db.add(record)
    await db.flush()
    await db.commit()
    return record


@router.post("/intercompany/{transaction_id}/post", response_model=IntercompanyRead, tags=["Finance · Consolidation"])
async def post_intercompany(
    transaction_id: UUID,
    user: User = Depends(write_ic),
    db: AsyncSession = Depends(get_db),
):
    record = await db.scalar(
        _scope(select(IntercompanyTransaction).where(IntercompanyTransaction.id == transaction_id), IntercompanyTransaction, user)
    )
    if record is None:
        raise NotFoundError("Intercompany transaction not found")
    result = await post_intercompany_transaction(db, user, record)
    await db.commit()
    return result


@router.post("/intercompany/{transaction_id}/eliminate", response_model=IntercompanyRead, tags=["Finance · Consolidation"])
async def eliminate_intercompany(
    transaction_id: UUID,
    user: User = Depends(write_ic),
    db: AsyncSession = Depends(get_db),
):
    record = await db.scalar(
        _scope(select(IntercompanyTransaction).where(IntercompanyTransaction.id == transaction_id), IntercompanyTransaction, user)
    )
    if record is None:
        raise NotFoundError("Intercompany transaction not found")
    result = await eliminate_intercompany_transaction(db, user, record)
    await db.commit()
    return result


@router.get("/budgets", response_model=Page[BudgetRead], tags=["Finance · Budgets"])
async def list_budgets(
    page: int = 1,
    size: int = 50,
    user: User = Depends(read_budget),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func

    total = int((await db.scalar(_scope(select(func.count()).select_from(Budget), Budget, user))) or 0)
    stmt = _scope(select(Budget), Budget, user).order_by(Budget.created_at.desc())
    rows = (await db.scalars(stmt.offset((page - 1) * size).limit(size))).all()
    return _paged(list(rows), total, page, size)


@router.post("/budgets", response_model=BudgetRead, status_code=201, tags=["Finance · Budgets"])
async def create_budget(
    payload: BudgetCreate,
    user: User = Depends(write_budget),
    db: AsyncSession = Depends(get_db),
):
    if payload.end_date < payload.start_date:
        raise ValidationError("Budget end date must not precede its start date")
    record = Budget(tenant_id=user.tenant_id, created_by_id=user.id, **payload.model_dump())
    db.add(record)
    await db.flush()
    await db.commit()
    return record


@router.get("/budgets/{budget_id}/lines", response_model=list[dict], tags=["Finance · Budgets"])
async def list_budget_lines(
    budget_id: UUID,
    user: User = Depends(read_budget),
    db: AsyncSession = Depends(get_db),
):
    budget = await db.scalar(_scope(select(Budget).where(Budget.id == budget_id), Budget, user))
    if budget is None:
        raise NotFoundError("Budget not found")
    rows = (
        await db.scalars(
            select(BudgetLine)
            .where(BudgetLine.budget_id == budget_id)
            .order_by(BudgetLine.period, BudgetLine.created_at)
        )
    ).all()
    return [
        {
            "id": str(row.id),
            "account_id": str(row.account_id),
            "period": row.period,
            "amount": str(row.amount),
        }
        for row in rows
    ]


@router.post("/budgets/{budget_id}/lines", status_code=201, tags=["Finance · Budgets"])
async def create_budget_line(
    budget_id: UUID,
    payload: BudgetLineCreate,
    user: User = Depends(write_budget),
    db: AsyncSession = Depends(get_db),
):
    budget = await db.scalar(_scope(select(Budget).where(Budget.id == budget_id), Budget, user))
    if budget is None:
        raise NotFoundError("Budget not found")
    line = BudgetLine(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        budget_id=budget.id,
        **payload.model_dump(),
    )
    db.add(line)
    try:
        await db.flush()
    except Exception as exc:
        await db.rollback()
        raise ConflictError("Budget line already exists for this account and period") from exc
    await db.commit()
    return {"id": str(line.id), **payload.model_dump(mode="json")}


@router.post("/budgets/{budget_id}/activate", response_model=BudgetRead, tags=["Finance · Budgets"])
async def activate_budget(
    budget_id: UUID,
    user: User = Depends(write_budget),
    db: AsyncSession = Depends(get_db),
):
    record = await db.scalar(_scope(select(Budget).where(Budget.id == budget_id), Budget, user))
    if record is None:
        raise NotFoundError("Budget not found")
    if not (await db.scalar(select(BudgetLine.id).where(BudgetLine.budget_id == budget_id).limit(1))):
        raise ValidationError("A budget needs at least one line before activation")
    record.status = "active"
    await db.flush()
    await db.commit()
    return record


@router.get("/budgets/{budget_id}/vs-actual", response_model=list[dict], tags=["Finance · Budgets"])
async def budget_actual(
    budget_id: UUID,
    user: User = Depends(read_budget),
    db: AsyncSession = Depends(get_db),
):
    return await budget_vs_actual(db, user, budget_id=budget_id)



@router.post("/assets/{asset_id}/impair", response_model=dict, tags=["Finance · Fixed Assets"])
async def impair_asset(
    asset_id: UUID,
    payload: AssetImpairmentCreate,
    user: User = Depends(write_asset),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.scalar(_scope(select(FixedAsset).where(FixedAsset.id == asset_id), FixedAsset, user))
    if asset is None:
        raise NotFoundError("Fixed asset not found")
    await impair_fixed_asset(
        db,
        user,
        asset,
        impairment_date=payload.impairment_date,
        impairment_loss=payload.impairment_loss,
        expense_account_id=payload.expense_account_id,
        reason=payload.reason,
    )
    await db.commit()
    return {"id": str(asset.id), "status": asset.status, "impairment_loss": str(asset.impairment_loss)}


@router.post("/assets/{asset_id}/write-off", response_model=dict, tags=["Finance · Fixed Assets"])
async def write_off_asset(
    asset_id: UUID,
    payload: AssetWriteOffCreate,
    user: User = Depends(write_asset),
    db: AsyncSession = Depends(get_db),
):
    asset = await db.scalar(_scope(select(FixedAsset).where(FixedAsset.id == asset_id), FixedAsset, user))
    if asset is None:
        raise NotFoundError("Fixed asset not found")
    await write_off_fixed_asset(db, user, asset, write_off_date=payload.write_off_date, reason=payload.reason)
    await db.commit()
    return {"id": str(asset.id), "status": asset.status}



@router.get("/reports/general-ledger", response_model=list[dict], tags=["Finance · Reports"])
async def report_general_ledger(
    account_id: Optional[UUID] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await general_ledger(db, user, account_id=account_id, date_from=date_from, date_to=date_to)


@router.get("/reports/dimension", response_model=list[dict], tags=["Finance · Reports"])
async def report_dimension(
    dimension: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await dimension_report(db, user, dimension=dimension, date_from=date_from, date_to=date_to)


@router.get("/reports/consolidation", tags=["Finance · Reports"])
async def report_consolidation(
    user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await consolidation_report(db, user)


@router.get("/reports/payroll-cost", response_model=list[dict], tags=["Finance · Reports"])
async def report_payroll_cost(
    period: Optional[str] = None,
    user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await payroll_cost_report(db, user, period=period)


@router.get("/reports/asset-register", response_model=list[dict], tags=["Finance · Reports"])
async def report_asset_register(
    user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await asset_register_report(db, user)


@router.get("/reports/bank-reconciliation", tags=["Finance · Reports"])
async def report_bank_reconciliation(
    user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    return await bank_reconciliation_report(db, user)


@router.get("/tally/trial-balance/export", tags=["Finance · Tally Export"])
async def export_tally_trial_balance(
    user: User = Depends(read_reports),
    db: AsyncSession = Depends(get_db),
):
    from app.modules.finance.service import trial_balance

    rows = await trial_balance(db, user)
    lines = ["code,debit,credit"]
    for row in rows:
        debit = max(row.balance, 0) if row.balance > 0 else 0
        credit = max(-row.balance, 0) if row.balance < 0 else 0
        lines.append(f"{row.code},{debit},{credit}")
    from fastapi.responses import PlainTextResponse

    return PlainTextResponse("\n".join(lines), media_type="text/csv")
