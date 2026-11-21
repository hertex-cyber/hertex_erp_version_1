import hashlib
import inspect
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.identity.models import User
from app.modules.procurement.models import (
    PurchaseOrder,
    Vendor,
    VendorInvoice,
)
from app.modules.procurement.ocr_models import OCRConfirmRequest, OCRDraftRead, OCRInvoiceDraft
from app.modules.procurement.schemas import VendorInvoiceCreate

OCR_CREDENTIAL_SECRET_KEY = "integrations.ocr.api_key"
MAX_DOCUMENT_BYTES = 2 * 1024 * 1024

_VENDOR_RE = re.compile(r"^\s*(?:vendor|supplier|from|sold\s+by)\s*[:\-]\s*(.+)$", re.I | re.M)
_INVOICE_RE = re.compile(
    r"\b(?:invoice\s*(?:no\.?|number|#)|inv\s*no\.?)\s*[:\-]?\s*([A-Z0-9][A-Z0-9\-/]{2,})",
    re.I,
)
_DATE_RE = re.compile(
    r"\b(?:invoice\s+date|date)\s*[:\-]?\s*(\d{4}-\d{2}-\d{2}|\d{2}[/-]\d{2}[/-]\d{4})",
    re.I,
)
_GSTIN_RE = re.compile(r"\b\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]\b", re.I)
_TOTAL_RE = re.compile(
    r"\b(?:grand\s+total|total\s+amount|amount\s+payable|total|amount)\s*[:\-]?\s*"
    r"(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.I,
)
_TAX_RE = re.compile(
    r"\b(?:gst|tax|cgst\s*\+\s*sgst|igst)\s*(?:amount)?\s*[:\-]?\s*"
    r"(?:rs\.?|inr|₹)?\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)",
    re.I,
)
_CURRENCY_RE = re.compile(r"(?i)(rs\.?|inr|₹)")

CredentialLoader = Callable[[AsyncSession, Optional[UUID]], Awaitable[Optional[str]]]
ExternalExtractor = Callable[..., Any]


@dataclass(frozen=True)
class OCRDocument:
    text: Optional[str]
    payload: Optional[dict[str, Any]]
    filename: Optional[str]
    mime_type: Optional[str]
    digest: str


@dataclass(frozen=True)
class OCRExtraction:
    vendor_name: str
    invoice_number: str
    invoice_date: date
    amount: Decimal
    tax_amount: Decimal
    gstin: Optional[str]
    confidence: Decimal


class OCRAdapter:
    name = "base"
    configured = False

    async def extract(
        self, document: OCRDocument, *, db: AsyncSession, tenant_id: Optional[UUID]
    ) -> OCRExtraction:
        raise NotImplementedError


class LocalStubOCRAdapter(OCRAdapter):
    name = "local_stub"
    configured = True

    async def extract(
        self, document: OCRDocument, *, db: AsyncSession, tenant_id: Optional[UUID]
    ) -> OCRExtraction:
        if document.payload is not None:
            return self._from_payload(document.payload)
        return self._from_text(document.text or "")

    def _from_payload(self, payload: dict[str, Any]) -> OCRExtraction:
        values = dict(payload)
        vendor_raw = values.get("vendor")
        if isinstance(vendor_raw, dict):
            for key, value in vendor_raw.items():
                values.setdefault(key, value)
            values["vendor"] = vendor_raw.get("name") or vendor_raw.get("vendor_name")
        vendor_name = _text(_first(values, "vendor", "vendor_name", "supplier", "seller"))
        invoice_number = _text(_first(values, "invoice_number", "invoice_no", "number", "inv_no"))
        invoice_date = _as_date(_first(values, "date", "invoice_date", "issue_date", "issued_on"))
        amount = _decimal(_first(values, "amount", "total", "grand_total", "amount_payable"))
        tax_amount = _decimal(_first(values, "tax_amount", "tax", "gst", "gst_amount")) or Decimal(
            "0"
        )
        gstin = _text(_first(values, "gstin", "gst_number", "tax_id")) or None
        present = sum(
            value is not None
            for value in (vendor_name, invoice_number, invoice_date, amount, tax_amount, gstin)
        )
        if not vendor_name or not invoice_number or invoice_date is None or amount is None:
            raise ValidationError(
                "OCR extraction could not identify vendor, number, date and amount"
            )
        return OCRExtraction(
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            amount=amount,
            tax_amount=tax_amount,
            gstin=gstin.upper() if gstin else None,
            confidence=_confidence(present, structured=True),
        )

    def _from_text(self, text: str) -> OCRExtraction:
        vendor_match = _VENDOR_RE.search(text)
        invoice_match = _INVOICE_RE.search(text)
        date_match = _DATE_RE.search(text)
        total_match = _TOTAL_RE.search(text)
        tax_match = _TAX_RE.search(text)
        gstin_match = _GSTIN_RE.search(text)
        vendor_name = _text(vendor_match.group(1)) if vendor_match else ""
        invoice_number = _text(invoice_match.group(1)) if invoice_match else ""
        invoice_date = _as_date(date_match.group(1)) if date_match else None
        amount = _decimal(total_match.group(1)) if total_match else None
        tax_amount = (_decimal(tax_match.group(1)) if tax_match else None) or Decimal("0")
        gstin = _text(gstin_match.group(0)).upper() if gstin_match else None
        present = sum(
            value is not None
            for value in (vendor_name, invoice_number, invoice_date, amount, tax_amount, gstin)
        )
        if not vendor_name or not invoice_number or invoice_date is None or amount is None:
            raise ValidationError(
                "OCR extraction could not identify vendor, number, date and amount"
            )
        return OCRExtraction(
            vendor_name=vendor_name,
            invoice_number=invoice_number,
            invoice_date=invoice_date,
            amount=amount,
            tax_amount=tax_amount,
            gstin=gstin,
            confidence=_confidence(present, structured=False),
        )


class ExternalCredentialOCRAdapter(OCRAdapter):
    name = "external"
    configured = True

    def __init__(self, credential_loader: CredentialLoader):
        self._credential_loader = credential_loader

    async def extract(
        self, document: OCRDocument, *, db: AsyncSession, tenant_id: Optional[UUID]
    ) -> OCRExtraction:
        credential = await self._credential_loader(db, tenant_id)
        if not credential:
            raise ValidationError("External OCR credential is not configured")
        extractor = _external_extractors.get("default")
        if extractor is None:
            raise ValidationError("External OCR provider adapter is not registered")
        result = extractor(document=document, credential=credential)
        if inspect.isawaitable(result):
            result = await result
        if isinstance(result, dict):
            result = OCRExtraction(**result)
        if not isinstance(result, OCRExtraction):
            raise ValidationError("External OCR provider returned an invalid extraction")
        return result


LOCAL_ADAPTER = LocalStubOCRAdapter()
_external_extractors: dict[str, ExternalExtractor] = {}


def set_external_extractor(extractor: ExternalExtractor | None) -> None:
    if extractor is None:
        _external_extractors.pop("default", None)
    else:
        _external_extractors["default"] = extractor


async def _load_credential(db: AsyncSession, tenant_id: Optional[UUID]) -> Optional[str]:
    from app.modules.settings.secrets import secrets_service

    return await secrets_service.get_plaintext(
        db, tenant_id=tenant_id, key=OCR_CREDENTIAL_SECRET_KEY
    )


async def resolve_adapter(
    db: AsyncSession, tenant_id: Optional[UUID], provider: str = "auto"
) -> OCRAdapter:
    if provider in {"local", "local_stub", "stub"}:
        return LOCAL_ADAPTER
    if provider == "external":
        return ExternalCredentialOCRAdapter(_load_credential)
    if provider == "auto":
        credential = await _load_credential(db, tenant_id)
        if credential:

            async def use_resolved(db: AsyncSession, tenant_id: Optional[UUID]) -> Optional[str]:
                return credential

            return ExternalCredentialOCRAdapter(use_resolved)
        return LOCAL_ADAPTER
    raise ValidationError(f"Unknown OCR provider '{provider}'")


def _first(values: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = values.get(key)
        if value not in (None, ""):
            return value
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _decimal(value: Any) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    if isinstance(value, Decimal):
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    cleaned = _CURRENCY_RE.sub("", _text(value)).replace(",", "").replace(" ", "")
    try:
        return Decimal(cleaned).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError) as exc:
        raise ValidationError(f"Invalid OCR amount '{value}'") from exc


def _as_date(value: Any) -> Optional[date]:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = _text(value)
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d %b %Y", "%d %B %Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    raise ValidationError(f"Invalid OCR date '{value}'")


def _confidence(present: int, *, structured: bool) -> Decimal:
    base = Decimal("0.68") if structured else Decimal("0.55")
    value = base + Decimal("0.05") * present
    return min(value, Decimal("0.99")).quantize(Decimal("0.0001"))


def build_document(
    *,
    text: Optional[str],
    payload: Optional[dict[str, Any]],
    filename: Optional[str],
    mime_type: Optional[str],
) -> OCRDocument:
    if payload is not None:
        canonical = json.dumps(payload, sort_keys=True, default=str)
    else:
        canonical = text or ""
    return OCRDocument(
        text=text,
        payload=payload,
        filename=filename,
        mime_type=mime_type,
        digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
    )


def _tenant_stmt(stmt, model, user: User):
    if not user.is_superuser and user.tenant_id:
        return stmt.where(model.tenant_id == user.tenant_id)
    return stmt


async def create_draft(
    db: AsyncSession, *, user: User, document: OCRDocument, provider: str, request: Request
) -> OCRInvoiceDraft:
    adapter = await resolve_adapter(db, user.tenant_id, provider)
    extraction = await adapter.extract(document, db=db, tenant_id=user.tenant_id)

    existing_stmt = _tenant_stmt(
        select(OCRInvoiceDraft).where(
            OCRInvoiceDraft.source_digest == document.digest,
            OCRInvoiceDraft.is_active.is_(True),
        ),
        OCRInvoiceDraft,
        user,
    )
    existing = await db.scalar(existing_stmt)
    if existing is not None:
        return existing

    vendor_stmt = _tenant_stmt(select(Vendor), Vendor, user)
    clauses: list[ColumnElement[bool]] = [Vendor.name.ilike(extraction.vendor_name)]
    if extraction.gstin:
        clauses.append(Vendor.gstin == extraction.gstin)
    vendor = await db.scalar(vendor_stmt.where(or_(*clauses)))

    draft = OCRInvoiceDraft(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        source_type="json" if document.payload is not None else "text",
        source_digest=document.digest,
        filename=document.filename,
        mime_type=document.mime_type,
        provider=adapter.name,
        credential_key=OCR_CREDENTIAL_SECRET_KEY if adapter.name == "external" else None,
        vendor_name=extraction.vendor_name,
        vendor_id=vendor.id if vendor else None,
        invoice_number=extraction.invoice_number,
        invoice_date=extraction.invoice_date,
        amount=extraction.amount,
        tax_amount=extraction.tax_amount,
        gstin=extraction.gstin,
        confidence=extraction.confidence,
        status="pending",
        source_metadata={
            "filename": document.filename,
            "mime_type": document.mime_type,
            "adapter": adapter.name,
        },
    )
    db.add(draft)
    await record_audit(
        db,
        user=user,
        action="ocr.ingest",
        module="procurement",
        entity="OCRInvoiceDraft",
        entity_id=draft.id,
        changes={
            "provider": adapter.name,
            "invoice_number": draft.invoice_number,
            "source_digest": draft.source_digest,
            "confidence": str(draft.confidence),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(draft)
    return draft


async def load_draft(
    db: AsyncSession, user: User, draft_id: UUID, *, for_update: bool = False
) -> OCRInvoiceDraft:
    stmt = _tenant_stmt(
        select(OCRInvoiceDraft).where(
            OCRInvoiceDraft.id == draft_id, OCRInvoiceDraft.is_active.is_(True)
        ),
        OCRInvoiceDraft,
        user,
    )
    if for_update:
        stmt = stmt.with_for_update()
    draft = await db.scalar(stmt)
    if draft is None:
        raise NotFoundError("OCR draft not found")
    return draft


async def confirm_draft(
    db: AsyncSession,
    *,
    user: User,
    draft: OCRInvoiceDraft,
    payload: OCRConfirmRequest,
    request: Request,
) -> VendorInvoice:
    if draft.status == "confirmed" and draft.confirmed_invoice_id:
        existing = await db.scalar(
            _tenant_stmt(
                select(VendorInvoice).where(VendorInvoice.id == draft.confirmed_invoice_id),
                VendorInvoice,
                user,
            )
        )
        if existing is None:
            raise NotFoundError("Confirmed vendor invoice not found")
        return existing
    if draft.status != "pending":
        raise ConflictError("Only pending OCR drafts can be confirmed")

    vendor_id = payload.vendor_id or draft.vendor_id
    if vendor_id is None:
        raise ValidationError("Select a vendor before confirming this OCR draft")
    vendor = await db.scalar(
        _tenant_stmt(select(Vendor).where(Vendor.id == vendor_id), Vendor, user)
    )
    if vendor is None:
        raise NotFoundError("Vendor not found")

    purchase_order_id = payload.purchase_order_id
    if purchase_order_id is not None:
        po = await db.scalar(
            _tenant_stmt(
                select(PurchaseOrder).where(PurchaseOrder.id == purchase_order_id),
                PurchaseOrder,
                user,
            )
        )
        if po is None:
            raise NotFoundError("Purchase order not found")

    invoice_payload = VendorInvoiceCreate(
        vendor_id=vendor_id,
        purchase_order_id=purchase_order_id,
        invoice_number=payload.invoice_number or draft.invoice_number,
        issue_date=payload.issue_date or draft.invoice_date,
        due_date=payload.due_date,
        amount=payload.amount if payload.amount is not None else draft.amount,
        tax_amount=payload.tax_amount if payload.tax_amount is not None else draft.tax_amount,
        status="draft",
        notes=payload.notes,
    )
    invoice = VendorInvoice(
        tenant_id=draft.tenant_id or user.tenant_id,
        created_by_id=user.id,
        **invoice_payload.model_dump(),
    )
    db.add(invoice)
    await db.flush()

    draft.status = "confirmed"
    draft.vendor_id = vendor_id
    draft.reviewed_by_id = user.id
    draft.reviewed_at = datetime.now(timezone.utc)
    draft.confirmed_invoice_id = invoice.id
    await record_audit(
        db,
        user=user,
        action="ocr.confirm",
        module="procurement",
        entity="VendorInvoice",
        entity_id=invoice.id,
        changes={
            "draft_id": str(draft.id),
            "invoice_number": invoice.invoice_number,
            "status": invoice.status,
            "provider": draft.provider,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def reject_draft(
    db: AsyncSession, *, user: User, draft: OCRInvoiceDraft, reason: str, request: Request
) -> OCRInvoiceDraft:
    if draft.status != "pending":
        raise ConflictError("Only pending OCR drafts can be rejected")
    draft.status = "rejected"
    draft.rejection_reason = reason
    draft.reviewed_by_id = user.id
    draft.reviewed_at = datetime.now(timezone.utc)
    await record_audit(
        db,
        user=user,
        action="ocr.reject",
        module="procurement",
        entity="OCRInvoiceDraft",
        entity_id=draft.id,
        changes={"reason": reason, "invoice_number": draft.invoice_number},
        request=request,
    )
    await db.commit()
    await db.refresh(draft)
    return draft


async def delete_draft(
    db: AsyncSession, *, user: User, draft: OCRInvoiceDraft, request: Request
) -> None:
    if draft.status == "confirmed":
        raise ConflictError("Confirmed OCR drafts cannot be deleted")
    draft.is_active = False
    await record_audit(
        db,
        user=user,
        action="ocr.delete",
        module="procurement",
        entity="OCRInvoiceDraft",
        entity_id=draft.id,
        changes={"invoice_number": draft.invoice_number},
        request=request,
    )
    await db.commit()


def to_read(draft: OCRInvoiceDraft) -> OCRDraftRead:
    return OCRDraftRead.model_validate(draft)
