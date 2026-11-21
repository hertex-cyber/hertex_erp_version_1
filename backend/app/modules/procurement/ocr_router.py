import json
import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permissions
from app.core.exceptions import ValidationError
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.procurement.ocr_models import (
    OCRConfirmRequest,
    OCRDraftRead,
    OCRInvoiceDraft,
    OCRRejectRequest,
    OCRSubmitRequest,
)
from app.modules.procurement.ocr_service import (
    MAX_DOCUMENT_BYTES,
    build_document,
    confirm_draft,
    create_draft,
    delete_draft,
    load_draft,
    reject_draft,
    to_read,
)
from app.modules.procurement.schemas import VendorInvoiceRead

router = APIRouter(prefix="/ocr", tags=["Procurement · OCR Ingestion"])

create_permission = require_permissions("procurement.vendorinvoice.create")
read_permission = require_permissions("procurement.vendorinvoice.read")
review_permission = require_permissions("procurement.vendorinvoice.update")
delete_permission = require_permissions("procurement.vendorinvoice.delete")


@router.post("/documents", response_model=OCRDraftRead, status_code=201)
async def submit_invoice_document(
    payload: OCRSubmitRequest,
    request: Request,
    user: User = Depends(create_permission),
    db: AsyncSession = Depends(get_db),
):
    text = payload.text
    document_payload = payload.document
    if document_payload is None and text and text.lstrip().startswith("{"):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            document_payload = parsed
            text = None
    document = build_document(
        text=text,
        payload=document_payload,
        filename=payload.filename,
        mime_type=payload.mime_type,
    )
    draft = await create_draft(
        db, user=user, document=document, provider=payload.provider, request=request
    )
    return to_read(draft)


@router.post("/documents/upload", response_model=OCRDraftRead, status_code=201)
async def upload_invoice_document(
    request: Request,
    file: UploadFile = File(...),
    provider: str = Form("auto"),
    user: User = Depends(create_permission),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    if not content:
        raise ValidationError("Uploaded file is empty")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValidationError("Uploaded file exceeds the OCR size limit")
    text = content.decode("utf-8", errors="replace")
    document_payload = None
    filename = file.filename or ""
    mime_type = file.content_type
    if mime_type == "application/json" or filename.lower().endswith(".json"):
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            document_payload = parsed
            text = None
    document = build_document(
        text=text,
        payload=document_payload,
        filename=filename,
        mime_type=mime_type,
    )
    draft = await create_draft(db, user=user, document=document, provider=provider, request=request)
    return to_read(draft)


@router.get("/drafts", response_model=Page[OCRDraftRead])
async def list_ocr_drafts(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    q: Optional[str] = None,
    user: User = Depends(read_permission),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(OCRInvoiceDraft).where(OCRInvoiceDraft.is_active.is_(True))
    count_stmt = (
        select(func.count()).select_from(OCRInvoiceDraft).where(OCRInvoiceDraft.is_active.is_(True))
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(OCRInvoiceDraft.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(OCRInvoiceDraft.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(OCRInvoiceDraft.status == status)
        count_stmt = count_stmt.where(OCRInvoiceDraft.status == status)
    if q:
        clauses = (
            OCRInvoiceDraft.vendor_name.ilike(f"%{q}%"),
            OCRInvoiceDraft.invoice_number.ilike(f"%{q}%"),
            OCRInvoiceDraft.gstin.ilike(f"%{q}%"),
        )
        stmt = stmt.where(or_(*clauses))
        count_stmt = count_stmt.where(or_(*clauses))
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(OCRInvoiceDraft.created_at.desc())
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
    )
    return {
        "items": [to_read(item) for item in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


@router.get("/drafts/{draft_id}", response_model=OCRDraftRead)
async def get_ocr_draft(
    draft_id: UUID,
    user: User = Depends(read_permission),
    db: AsyncSession = Depends(get_db),
):
    draft = await load_draft(db, user, draft_id)
    return to_read(draft)


@router.post("/drafts/{draft_id}/confirm", response_model=VendorInvoiceRead)
async def confirm_ocr_draft(
    draft_id: UUID,
    payload: OCRConfirmRequest,
    request: Request,
    user: User = Depends(review_permission),
    db: AsyncSession = Depends(get_db),
):
    draft = await load_draft(db, user, draft_id, for_update=True)
    return await confirm_draft(db, user=user, draft=draft, payload=payload, request=request)


@router.post("/drafts/{draft_id}/reject", response_model=OCRDraftRead)
async def reject_ocr_draft(
    draft_id: UUID,
    payload: OCRRejectRequest,
    request: Request,
    user: User = Depends(review_permission),
    db: AsyncSession = Depends(get_db),
):
    draft = await load_draft(db, user, draft_id, for_update=True)
    return to_read(
        await reject_draft(db, user=user, draft=draft, reason=payload.reason, request=request)
    )


@router.delete("/drafts/{draft_id}")
async def delete_ocr_draft(
    draft_id: UUID,
    request: Request,
    user: User = Depends(delete_permission),
    db: AsyncSession = Depends(get_db),
):
    draft = await load_draft(db, user, draft_id, for_update=True)
    await delete_draft(db, user=user, draft=draft, request=request)
    return {"message": "OCR draft deleted"}
