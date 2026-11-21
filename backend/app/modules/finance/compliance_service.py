"""Statutory filings, bank feeds, dimensions, consolidation and extended ledger reports."""

import csv
import hashlib
import io
import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.finance.compliance_models import (
    Budget,
    BudgetLine,
    EInvoice,
    EWaybill,
    GstItcMatch,
    GstReturn,
    IntercompanyTransaction,
)
from app.modules.finance.control_service import (
    complete_source_event,
    enqueue_outbox,
    record_finance_audit,
)
from app.modules.finance.models import (
    Account,
    BankAccount,
    BankTransaction,
    FixedAsset,
    Invoice,
    InvoiceTaxLine,
    JournalEntry,
    JournalLine,
    TaxRegistration,
)
from app.modules.finance.service import (
    ACCOUNTS_PAYABLE,
    ACCOUNTS_RECEIVABLE,
    INVENTORY_ADJUSTMENT_EXPENSE,
    _require_account,
    trial_balance,
)
from app.modules.hr.models import PayrollRun, Payslip
from app.modules.identity.models import User
from app.modules.procurement.models import VendorInvoice, VendorInvoiceTaxLine
from app.modules.settings.numbering import (
    assert_no_collision,
    document_number,
    find_allocation,
    select_gstin_series,
    validate_gst_renderable,
)
from app.modules.settings.numbering import (
    commit as commit_number,
)

ZERO = Decimal("0")


def _scope(stmt: Select, model: Any, user: User) -> Select:
    if not user.is_superuser and user.tenant_id:
        return stmt.where(model.tenant_id == user.tenant_id)
    return stmt


def _amount(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def _period(month: str) -> str:
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month or ""):
        raise ValidationError("filing_period must use YYYY-MM format")
    return month



def _gst_totals(rows: list[Any]) -> dict[str, str]:
    return {
        "taxable_amount": str(sum((_amount(row.taxable_amount) for row in rows), ZERO)),
        "cgst": str(sum((_amount(row.cgst_amount) for row in rows), ZERO)),
        "sgst": str(sum((_amount(row.sgst_amount) for row in rows), ZERO)),
        "igst": str(sum((_amount(row.igst_amount) for row in rows), ZERO)),
        "tax_total": str(
            sum(
                (_amount(row.cgst_amount) + _amount(row.sgst_amount) + _amount(row.igst_amount) for row in rows),
                ZERO,
            )
        ),
    }


async def build_gst_return(
    db: AsyncSession,
    user: User,
    *,
    registration_id: UUID,
    return_type: str,
    filing_period: str,
) -> GstReturn:
    filing_period = _period(filing_period)
    if return_type not in {"GSTR1", "GSTR3B"}:
        raise ValidationError("return_type must be GSTR1 or GSTR3B")
    registration = await db.scalar(
        _scope(select(TaxRegistration).where(TaxRegistration.id == registration_id), TaxRegistration, user)
    )
    if registration is None:
        raise NotFoundError("Tax registration not found")
    prefix, suffix = filing_period.split("-")
    start = date(int(prefix), int(suffix), 1)
    end = date(int(prefix) + (int(suffix) // 12), (int(suffix) % 12) + 1, 1) - timedelta(days=1)

    sales = list(
        (
            await db.scalars(
                _scope(
                    select(InvoiceTaxLine)
                    .join(Invoice, Invoice.id == InvoiceTaxLine.invoice_id)
                    .where(
                        Invoice.status.in_(("sent", "partially_paid", "paid", "overdue")),
                        Invoice.issue_date >= start,
                        Invoice.issue_date <= end,
                        InvoiceTaxLine.registration_id == registration_id,
                    ),
                    InvoiceTaxLine,
                    user,
                )
            )
        ).all()
    )
    purchases = list(
        (
            await db.scalars(
                _scope(
                    select(VendorInvoiceTaxLine)
                    .join(VendorInvoice, VendorInvoice.id == VendorInvoiceTaxLine.invoice_id)
                    .where(
                        VendorInvoice.status.in_(("approved", "partially_paid", "paid")),
                        VendorInvoice.issue_date >= start,
                        VendorInvoice.issue_date <= end,
                        VendorInvoiceTaxLine.registration_id == registration_id,
                    ),
                    VendorInvoiceTaxLine,
                    user,
                )
            )
        ).all()
    )
    summary = {
        "period_start": str(start),
        "period_end": str(end),
        "gstin": registration.gstin,
        "outward_supply": _gst_totals(sales),
        "inward_supply": _gst_totals(purchases),
        "invoice_count": len({line.invoice_id for line in sales}),
        "vendor_invoice_count": len({line.invoice_id for line in purchases}),
        "net_tax_liability": str(
            _amount(_gst_totals(sales)["tax_total"]) - _amount(_gst_totals(purchases)["tax_total"])
        ),
        "source": "posted_subledger_lines",
    }
    existing = await db.scalar(
        _scope(
            select(GstReturn).where(
                GstReturn.registration_id == registration_id,
                GstReturn.return_type == return_type,
                GstReturn.filing_period == filing_period,
            ),
            GstReturn,
            user,
        )
    )
    if existing is not None:
        if existing.status != "draft":
            raise ConflictError("A filed return is immutable; create a fresh draft for amendments")
        existing.summary = summary
        await record_finance_audit(
            db,
            user=user,
            entity_type="gst_return",
            entity_id=existing.id,
            action="rebuild_draft",
            after=summary,
        )
        await db.flush()
        return existing
    gst_return = GstReturn(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        registration_id=registration_id,
        return_type=return_type,
        filing_period=filing_period,
        status="draft",
        summary=summary,
    )
    db.add(gst_return)
    await record_finance_audit(
        db,
        user=user,
        entity_type="gst_return",
        entity_id=gst_return.id,
        action="build_draft",
        after={"return_type": return_type, "filing_period": filing_period},
    )
    await db.flush()
    return gst_return


async def file_gst_return(
    db: AsyncSession, user: User, gst_return_id: UUID, *, acknowledgement_number: str
) -> GstReturn:
    record = await db.scalar(_scope(select(GstReturn).where(GstReturn.id == gst_return_id), GstReturn, user))
    if record is None:
        raise NotFoundError("GST return not found")
    if record.status == "filed":
        raise ConflictError("GST return is already filed")
    if len(acknowledgement_number.strip()) < 4:
        raise ValidationError("Acknowledge number must be at least 4 characters")
    before = {"status": record.status}
    record.status = "filed"
    record.filed_at = datetime.now(timezone.utc)
    record.filed_by_id = user.id
    record.acknowledgement_number = acknowledgement_number.strip()
    await record_finance_audit(
        db,
        user=user,
        entity_type="gst_return",
        entity_id=record.id,
        action="file",
        before=before,
        after={"status": "filed", "acknowledgement_number": record.acknowledgement_number},
    )
    await enqueue_outbox(
        db,
        tenant_id=user.tenant_id,
        event_type="gst.return.filed",
        aggregate_type="gst_return",
        aggregate_id=record.id,
        payload={"filing_period": record.filing_period, "return_type": record.return_type},
    )
    await db.flush()
    return record


async def generate_e_invoice(db: AsyncSession, user: User, invoice_id: UUID) -> EInvoice:
    invoice = await db.scalar(
        _scope(
            select(Invoice).options(selectinload(Invoice.tax_lines)).where(Invoice.id == invoice_id),
            Invoice,
            user,
        )
    )
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if invoice.status == "draft":
        raise ValidationError("Only a posted invoice can generate an e-invoice")
    existing = await db.scalar(
        _scope(select(EInvoice).where(EInvoice.invoice_id == invoice_id), EInvoice, user)
    )
    if existing is not None and existing.status in {"generated", "cancelled"}:
        return existing
    irn = hashlib.sha256(f"{user.tenant_id}:{invoice.id}:{invoice.invoice_number}".encode()).hexdigest()[:64]
    registration = await db.scalar(
        select(TaxRegistration).where(TaxRegistration.tenant_id == user.tenant_id)
    )
    if registration and registration.gstin:
        series = await select_gstin_series(
            db, tenant_id=user.tenant_id, key="invoice", gstin=registration.gstin
        )
        if series is not None:
            validate_gst_renderable(
                invoice.invoice_number,
                doc_type="gst_invoice",
                irp_safe=series.irp_safe or True,
                max_length=series.max_length or 16,
            )
            allocation = await find_allocation(
                db, tenant_id=user.tenant_id, rendered=invoice.invoice_number
            )
            await assert_no_collision(
                db,
                tenant_id=user.tenant_id,
                rendered=invoice.invoice_number,
                fiscal_year=allocation.fiscal_year if allocation else None,
                sequence_id=allocation.sequence_id if allocation else series.id,
                exclude_allocation_id=allocation.id if allocation else None,
            )
    payload = {
        "invoice_number": invoice.invoice_number,
        "issue_date": str(invoice.issue_date),
        "total": str(invoice.total),
        "gstin": registration.gstin if registration else None,
        "tax_lines": [
            {
                "tax_code_id": str(line.tax_code_id) if line.tax_code_id else None,
                "taxable_amount": str(line.taxable_amount),
                "cgst": str(line.cgst_amount),
                "sgst": str(line.sgst_amount),
                "igst": str(line.igst_amount),
            }
            for line in invoice.tax_lines
        ],
    }
    if existing is not None:
        existing.irn = irn
        existing.status = "generated"
        existing.payload = payload
        existing.qr_payload = f"IRN:{irn}|INV:{invoice.invoice_number}|AMT:{invoice.total}"
        existing.acknowledgement_number = f"ACK{irn[:12]}"
        existing.acknowledgement_date = datetime.now(timezone.utc)
        existing.error = None
        record = existing
    else:
        record = EInvoice(
            tenant_id=user.tenant_id,
            created_by_id=user.id,
            invoice_id=invoice.id,
            irn=irn,
            status="generated",
            payload=payload,
            qr_payload=f"IRN:{irn}|INV:{invoice.invoice_number}|AMT:{invoice.total}",
            acknowledgement_number=f"ACK{irn[:12]}",
            acknowledgement_date=datetime.now(timezone.utc),
        )
        db.add(record)
    await enqueue_outbox(
        db,
        tenant_id=user.tenant_id,
        event_type="einvoice.generated",
        aggregate_type="einvoice",
        aggregate_id=invoice.id,
        payload={"irn": irn, "invoice_number": invoice.invoice_number},
    )
    await db.flush()
    return record


async def cancel_e_invoice(
    db: AsyncSession, user: User, e_invoice_id: UUID, *, reason: str
) -> EInvoice:
    record = await db.scalar(_scope(select(EInvoice).where(EInvoice.id == e_invoice_id), EInvoice, user))
    if record is None:
        raise NotFoundError("E-invoice not found")
    if record.status != "generated":
        raise ConflictError("Only a generated e-invoice can be cancelled")
    if len(reason.strip()) < 3:
        raise ValidationError("Cancellation reason is required")
    record.status = "cancelled"
    record.cancelled_at = datetime.now(timezone.utc)
    record.cancellation_reason = reason.strip()
    await record_finance_audit(
        db,
        user=user,
        entity_type="einvoice",
        entity_id=record.id,
        action="cancel",
        after={"status": "cancelled", "reason": reason.strip()},
    )
    await db.flush()
    return record


async def generate_e_waybill(
    db: AsyncSession,
    user: User,
    *,
    invoice_id: UUID,
    transport_mode: str = "road",
    valid_days: int = 10,
) -> EWaybill:
    if transport_mode not in {"road", "air", "rail", "ship"}:
        raise ValidationError("Unsupported transport mode")
    invoice = await db.scalar(_scope(select(Invoice).where(Invoice.id == invoice_id), Invoice, user))
    if invoice is None:
        raise NotFoundError("Invoice not found")
    existing = await db.scalar(
        _scope(select(EWaybill).where(EWaybill.invoice_id == invoice_id), EWaybill, user)
    )
    if existing is not None:
        return existing
    number = await document_number(
        db, key="e_waybill", tenant_id=user.tenant_id, user=user,
        on_date=invoice.issue_date, document_type="e_waybill",
    )
    waybill = EWaybill(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        invoice_id=invoice_id,
        waybill_number=number,
        transport_mode=transport_mode,
        valid_until=datetime.now(timezone.utc) + timedelta(days=valid_days),
        payload={"invoice_number": invoice.invoice_number, "transport_mode": transport_mode},
    )
    db.add(waybill)
    await db.flush()
    await commit_number(
        db, number, document_type="EWaybill", document_id=waybill.id, user=user
    )
    return waybill


async def reconcile_itc(db: AsyncSession, user: User, *, filing_period: str) -> list[GstItcMatch]:
    filing_period = _period(filing_period)
    prefix, suffix = filing_period.split("-")
    start = date(int(prefix), int(suffix), 1)
    end = date(int(prefix) + (int(suffix) // 12), (int(suffix) % 12) + 1, 1) - timedelta(days=1)
    rows = list(
        (
            await db.scalars(
                _scope(
                    select(VendorInvoiceTaxLine)
                    .join(VendorInvoice, VendorInvoice.id == VendorInvoiceTaxLine.invoice_id)
                    .where(
                        VendorInvoice.status.in_(("approved", "partially_paid", "paid")),
                        VendorInvoice.issue_date >= start,
                        VendorInvoice.issue_date <= end,
                    ),
                    VendorInvoiceTaxLine,
                    user,
                )
            )
        ).all()
    )
    results: list[GstItcMatch] = []
    for line in rows:
        posted = _amount(line.cgst_amount) + _amount(line.sgst_amount) + _amount(line.igst_amount)
        invoice_tax = _amount(line.taxable_amount) * (
            _amount(line.cgst_rate) + _amount(line.sgst_rate) + _amount(line.igst_rate)
        ) / Decimal("100")
        difference = posted - invoice_tax
        existing = await db.scalar(
            _scope(
                select(GstItcMatch).where(
                    GstItcMatch.filing_period == filing_period,
                    GstItcMatch.source_document_id == line.invoice_id,
                    GstItcMatch.tax_code_id == line.tax_code_id,
                ),
                GstItcMatch,
                user,
            )
        )
        values = {
            "taxable_amount": _amount(line.taxable_amount),
            "invoice_tax": invoice_tax.quantize(Decimal("0.01")),
            "posted_itc": posted,
            "difference": difference.quantize(Decimal("0.01")),
            "status": "matched" if abs(difference) < Decimal("0.01") else "mismatch",
            "source_document_type": "vendor_invoice",
            "registration_id": getattr(line, "registration_id", None),
        }
        if existing is None:
            record = GstItcMatch(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                filing_period=filing_period,
                source_document_id=line.invoice_id,
                tax_code_id=line.tax_code_id,
                **values,
            )
            db.add(record)
        else:
            for key, value in values.items():
                setattr(existing, key, value)
            record = existing
        results.append(record)
    await db.flush()
    return results



def parse_bank_statement(content: str, provider: str = "csv") -> list[dict[str, Any]]:
    if provider in ("csv", "bank_feed"):
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise ValidationError("Bank statement CSV needs a header row")
        columns = {name.strip().lower(): name for name in reader.fieldnames if name}
        required = {"date", "amount"}
        if not required.issubset(columns):
            raise ValidationError("Bank statement CSV requires date and amount columns")
        transactions = []
        for row in reader:
            raw_date = (row.get(columns["date"]) or "").strip()
            raw_amount = (row.get(columns["amount"]) or "0").replace(",", "").strip()
            try:
                txn_date = date.fromisoformat(raw_date)
                amount = Decimal(raw_amount)
            except (ValueError, ArithmeticError) as exc:
                raise ValidationError(f"Invalid bank statement row: {raw_date} {raw_amount}") from exc
            transactions.append(
                {
                    "txn_date": txn_date,
                    "amount": amount,
                    "description": (row.get(columns.get("description", "")) or "")[:255] or None,
                    "reference": (row.get(columns.get("reference", "")) or "")[:120] or None,
                }
            )
        return transactions
    if provider == "ofx":
        transactions = []
        for block in re.findall(r"<STMTTRN>(.*?)</STMTTRN>", content, flags=re.IGNORECASE | re.DOTALL):
            fields = dict(re.findall(r"<([A-Z]+)>([^<\r\n]+)", block))
            try:
                txn_date = datetime.strptime(fields["DTPOSTED"][:8], "%Y%m%d").date()
                amount = Decimal(fields["TRNAMT"])
            except (KeyError, ValueError, ArithmeticError) as exc:
                raise ValidationError("Invalid OFX STMTTRN entry") from exc
            transactions.append(
                {
                    "txn_date": txn_date,
                    "amount": amount,
                    "description": fields.get("MEMO", "")[:255] or None,
                    "reference": fields.get("FITID", "")[:120] or None,
                }
            )
        if not transactions:
            raise ValidationError("OFX statement contains no STMTTRN entries")
        return transactions
    raise ValidationError("Unsupported bank feed provider")


def transaction_hash(bank_account_id: UUID, row: dict[str, Any]) -> str:
    payload = "|".join(
        [
            str(bank_account_id),
            str(row["txn_date"]),
            str(row["amount"]),
            row.get("reference") or "",
            row.get("description") or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def import_bank_feed(
    db: AsyncSession,
    user: User,
    *,
    feed: Any,
    content: str,
    file_name: str | None = None,
    source_event: Any | None = None,
) -> dict[str, Any]:
    from app.modules.finance.compliance_models import BankFeedImport

    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    existing = await db.scalar(
        _scope(
            select(BankFeedImport).where(BankFeedImport.feed_id == feed.id, BankFeedImport.file_hash == digest),
            BankFeedImport,
            user,
        )
    )
    if existing is not None:
        return {
            "import_id": str(existing.id),
            "status": "duplicate",
            "row_count": existing.row_count,
            "imported_count": 0,
            "duplicate_count": existing.row_count,
        }
    rows = parse_bank_statement(content, feed.provider if feed.provider != "webhook" else "csv")
    imported = 0
    for row in rows:
        digest_row = transaction_hash(feed.bank_account_id, row)
        present = await db.scalar(
            select(BankTransaction.id).where(
                BankTransaction.bank_account_id == feed.bank_account_id,
                BankTransaction.transaction_hash == digest_row,
            )
        )
        if present is not None:
            continue
        db.add(
            BankTransaction(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                bank_account_id=feed.bank_account_id,
                txn_date=row["txn_date"],
                amount=row["amount"],
                description=row["description"],
                reference=row["reference"],
                transaction_hash=digest_row,
                reconciled=False,
            )
        )
        imported += 1
    record = BankFeedImport(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        feed_id=feed.id,
        file_hash=digest,
        file_name=file_name,
        status="completed",
        row_count=len(rows),
        imported_count=imported,
        duplicate_count=len(rows) - imported,
    )
    db.add(record)
    feed.last_imported_at = datetime.now(timezone.utc)
    if source_event is not None:
        complete_source_event(source_event, result_reference=str(record.id))
    await record_finance_audit(
        db,
        user=user,
        entity_type="bank_feed_import",
        entity_id=record.id,
        action="import",
        after={"feed_id": str(feed.id), "rows": len(rows), "imported": imported},
    )
    await db.flush()
    return {
        "import_id": str(record.id),
        "status": "completed",
        "row_count": len(rows),
        "imported_count": imported,
        "duplicate_count": len(rows) - imported,
    }


async def impair_fixed_asset(
    db: AsyncSession,
    user: User,
    asset: FixedAsset,
    *,
    impairment_date: date,
    impairment_loss: Decimal,
    expense_account_id: UUID,
    reason: str,
) -> FixedAsset:
    if asset.status not in ("active", "impaired"):
        raise ConflictError("Only an active or impaired asset can be impaired")
    carrying = asset.cost - asset.accumulated_depreciation - asset.impairment_loss
    if impairment_loss <= 0 or impairment_loss > carrying:
        raise ValidationError("Impairment loss must be positive and within the carrying amount")
    expense = await db.scalar(
        _scope(select(Account).where(Account.id == expense_account_id), Account, user)
    )
    if expense is None or not expense.is_active:
        raise ValidationError("Impairment expense account must be an active account in this tenant")
    number = await document_number(
        db, key="asset_impairment", tenant_id=user.tenant_id, user=user,
        on_date=impairment_date, document_type="asset_impairment",
    )
    journal = JournalEntry(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=impairment_date,
        reference=f"IMP:{asset.asset_tag}",
        memo=f"Impairment of {asset.name}: {reason}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
        source_module="finance",
        source_document_type="fixed_asset_impairment",
        source_document_id=asset.id,
    )
    db.add(journal)
    await db.flush()
    await commit_number(
        db, number, document_type="JournalEntry", document_id=journal.id, user=user
    )
    db.add_all(
        [
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=journal.id,
                account_id=expense.id,
                debit=impairment_loss,
                credit=ZERO,
                description=f"Impairment loss: {asset.asset_tag}",
            ),
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=journal.id,
                account_id=asset.accumulated_depreciation_account_id,
                debit=ZERO,
                credit=impairment_loss,
                description=f"Impairment allowance: {asset.asset_tag}",
            ),
        ]
    )
    asset.impairment_loss += impairment_loss
    asset.status = "impaired"
    await record_finance_audit(
        db,
        user=user,
        entity_type="fixed_asset",
        entity_id=asset.id,
        action="impair",
        after={"loss": str(impairment_loss), "reason": reason, "journal": journal.entry_number},
    )
    await db.flush()
    return asset


async def write_off_fixed_asset(
    db: AsyncSession, user: User, asset: FixedAsset, *, write_off_date: date, reason: str
) -> FixedAsset:
    if asset.status == "written_off" or asset.status == "disposed":
        raise ConflictError("Asset is already derecognised")
    accumulated = asset.accumulated_depreciation + asset.impairment_loss
    residual = asset.cost - accumulated
    number = await document_number(
        db, key="asset_write_off", tenant_id=user.tenant_id, user=user,
        on_date=write_off_date, document_type="asset_write_off",
    )
    journal = JournalEntry(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=write_off_date,
        reference=f"WO:{asset.asset_tag}",
        memo=f"Write-off of {asset.name}: {reason}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
        source_module="finance",
        source_document_type="fixed_asset_write_off",
        source_document_id=asset.id,
    )
    db.add(journal)
    await db.flush()
    await commit_number(
        db, number, document_type="JournalEntry", document_id=journal.id, user=user
    )
    lines = [
        JournalLine(
            tenant_id=user.tenant_id,
            journal_entry_id=journal.id,
            account_id=asset.accumulated_depreciation_account_id,
            debit=accumulated,
            credit=ZERO,
            description=f"Remove accumulated depreciation: {asset.asset_tag}",
        )
    ]
    if residual > 0:
        lines.append(
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=journal.id,
                account_id=asset.depreciation_expense_account_id,
                debit=residual,
                credit=ZERO,
                description=f"Write-off loss: {asset.asset_tag}",
            )
        )
    lines.append(
        JournalLine(
            tenant_id=user.tenant_id,
            journal_entry_id=journal.id,
            account_id=asset.asset_account_id,
            debit=ZERO,
            credit=asset.cost,
            description=f"Remove asset cost: {asset.asset_tag}",
        )
    )
    db.add_all(lines)
    asset.status = "written_off"
    asset.disposed_at = write_off_date
    await record_finance_audit(
        db,
        user=user,
        entity_type="fixed_asset",
        entity_id=asset.id,
        action="write_off",
        after={"reason": reason, "journal": journal.entry_number},
    )
    await db.flush()
    return asset



async def post_intercompany_transaction(
    db: AsyncSession, user: User, transaction: IntercompanyTransaction
) -> IntercompanyTransaction:
    if transaction.status == "posted":
        return transaction
    if transaction.from_entity_id == transaction.to_entity_id:
        raise ValidationError("Intercompany transactions require two different entities")
    ar = await _require_account(db, user.tenant_id, ACCOUNTS_RECEIVABLE, "accounts receivable")
    expense = await _require_account(db, user.tenant_id, INVENTORY_ADJUSTMENT_EXPENSE, "expense")
    number = await document_number(
        db, key="intercompany", tenant_id=user.tenant_id, user=user,
        on_date=transaction.transaction_date, document_type="intercompany_transaction",
    )
    journal = JournalEntry(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=transaction.transaction_date,
        reference=f"IC:{transaction.number}",
        memo=transaction.description or "Intercompany transaction",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
        source_module="finance",
        source_document_type="intercompany_transaction",
        source_document_id=transaction.id,
        legal_entity_id=transaction.from_entity_id,
    )
    db.add(journal)
    await db.flush()
    await commit_number(
        db, number, document_type="JournalEntry", document_id=journal.id, user=user
    )
    db.add_all(
        [
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=journal.id,
                account_id=expense.id,
                debit=transaction.amount,
                credit=ZERO,
                description="Intercompany charge",
            ),
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=journal.id,
                account_id=ar.id,
                debit=ZERO,
                credit=transaction.amount,
                description="Intercompany receivable",
            ),
        ]
    )
    transaction.status = "posted"
    transaction.journal_entry_id = journal.id
    await enqueue_outbox(
        db,
        tenant_id=user.tenant_id,
        event_type="intercompany.posted",
        aggregate_type="intercompany_transaction",
        aggregate_id=transaction.id,
        payload={"amount": str(transaction.amount), "from": str(transaction.from_entity_id)},
    )
    await db.flush()
    return transaction


async def eliminate_intercompany_transaction(
    db: AsyncSession, user: User, transaction: IntercompanyTransaction
) -> IntercompanyTransaction:
    if transaction.status != "posted":
        raise ConflictError("Only posted intercompany transactions can be eliminated")
    if transaction.elimination_journal_entry_id is not None:
        return transaction
    ar = await _require_account(db, user.tenant_id, ACCOUNTS_RECEIVABLE, "accounts receivable")
    ap = await _require_account(db, user.tenant_id, ACCOUNTS_PAYABLE, "accounts payable")
    number = await document_number(
        db, key="intercompany_elimination", tenant_id=user.tenant_id, user=user,
        on_date=transaction.transaction_date, document_type="intercompany_elimination",
    )
    journal = JournalEntry(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=transaction.transaction_date,
        reference=f"ELIM:{transaction.number}",
        memo=f"Elimination of intercompany transaction {transaction.number}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
        source_module="finance",
        source_document_type="intercompany_elimination",
        source_document_id=transaction.id,
    )
    db.add(journal)
    await db.flush()
    await commit_number(
        db, number, document_type="JournalEntry", document_id=journal.id, user=user
    )
    db.add_all(
        [
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=journal.id,
                account_id=ap.id,
                debit=transaction.amount,
                credit=ZERO,
                description="Eliminate intercompany payable",
            ),
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=journal.id,
                account_id=ar.id,
                debit=ZERO,
                credit=transaction.amount,
                description="Eliminate intercompany receivable",
            ),
        ]
    )
    transaction.status = "eliminated"
    transaction.elimination_journal_entry_id = journal.id
    await db.flush()
    return transaction



async def general_ledger(
    db: AsyncSession, user: User, *, account_id: UUID | None = None, date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    stmt = (
        select(JournalEntry, JournalLine, Account)
        .join(JournalLine, JournalLine.journal_entry_id == JournalEntry.id)
        .join(Account, Account.id == JournalLine.account_id)
        .where(JournalEntry.status == "posted")
        .order_by(JournalEntry.entry_date, JournalEntry.entry_number, JournalLine.id)
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(JournalEntry.tenant_id == user.tenant_id)
    if account_id is not None:
        stmt = stmt.where(JournalLine.account_id == account_id)
    if date_from is not None:
        stmt = stmt.where(JournalEntry.entry_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(JournalEntry.entry_date <= date_to)
    rows = (await db.execute(stmt)).all()
    return [
        {
            "entry_date": str(entry.entry_date),
            "entry_number": entry.entry_number,
            "account_code": account.code,
            "account_name": account.name,
            "description": line.description,
            "debit": str(line.debit),
            "credit": str(line.credit),
            "reference": entry.reference,
            "journal_entry_id": str(entry.id),
            "branch_id": str(line.branch_id) if line.branch_id else None,
            "cost_center_id": str(line.cost_center_id) if line.cost_center_id else None,
        }
        for entry, line, account in rows
    ]


async def dimension_report(
    db: AsyncSession, user: User, *, dimension: str, date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    if dimension not in {"branch", "cost_center", "department", "project"}:
        raise ValidationError("Unsupported dimension")
    column = {
        "branch": JournalLine.branch_id,
        "cost_center": JournalLine.cost_center_id,
        "department": JournalLine.department_id,
        "project": JournalLine.project_id,
    }[dimension]
    stmt = (
        select(column.label("dimension_id"), func.sum(JournalLine.debit), func.sum(JournalLine.credit))
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(JournalEntry.status == "posted", column.is_not(None))
        .group_by(column)
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(JournalEntry.tenant_id == user.tenant_id)
    if date_from is not None:
        stmt = stmt.where(JournalEntry.entry_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(JournalEntry.entry_date <= date_to)
    rows = (await db.execute(stmt)).all()
    return [
        {
            "dimension": dimension,
            "dimension_id": str(row.dimension_id),
            "debit": str(_amount(row[1])),
            "credit": str(_amount(row[2])),
            "net": str(_amount(row[1]) - _amount(row[2])),
        }
        for row in rows
    ]


async def budget_vs_actual(db: AsyncSession, user: User, *, budget_id: UUID) -> list[dict[str, Any]]:
    budget = await db.scalar(_scope(select(Budget).where(Budget.id == budget_id), Budget, user))
    if budget is None:
        raise NotFoundError("Budget not found")
    lines = list((await db.scalars(select(BudgetLine).where(BudgetLine.budget_id == budget_id))).all())
    results = []
    for line in lines:
        year, month = line.period.split("-")
        start = date(int(year), int(month), 1)
        end = date(int(year) + (int(month) // 12), (int(month) % 12) + 1, 1) - timedelta(days=1)
        stmt = select(func.sum(JournalLine.debit), func.sum(JournalLine.credit)).join(
            JournalEntry, JournalEntry.id == JournalLine.journal_entry_id
        ).where(
            JournalEntry.status == "posted",
            JournalLine.account_id == line.account_id,
            JournalEntry.entry_date >= start,
            JournalEntry.entry_date <= end,
        )
        if not user.is_superuser and user.tenant_id:
            stmt = stmt.where(JournalEntry.tenant_id == user.tenant_id)
        actual = await db.execute(stmt)
        row = actual.one()
        debit, credit = _amount(row[0]), _amount(row[1])
        actual_amount = debit - credit if debit > credit else credit - debit
        results.append(
            {
                "account_id": str(line.account_id),
                "period": line.period,
                "budget": str(line.amount),
                "actual": str(actual_amount.quantize(Decimal("0.01"))),
                "variance": str((line.amount - actual_amount).quantize(Decimal("0.01"))),
            }
        )
    return results


async def consolidation_report(db: AsyncSession, user: User) -> dict[str, Any]:
    balances = await trial_balance(db, user)
    entity_rows = select(JournalEntry.legal_entity_id).where(
        JournalEntry.legal_entity_id.is_not(None)
    )
    if not user.is_superuser and user.tenant_id:
        entity_rows = entity_rows.where(JournalEntry.tenant_id == user.tenant_id)
    entity_stmt = select(func.count()).select_from(entity_rows.distinct().subquery())
    entity_count = int((await db.scalar(entity_stmt)) or 0)
    intercompany = await db.scalar(
        _scope(
            select(func.sum(IntercompanyTransaction.amount)).where(
                IntercompanyTransaction.status == "posted"
            ),
            IntercompanyTransaction,
            user,
        )
    )
    return {
        "trial_balance": [row.model_dump(mode="json") for row in balances],
        "legal_entities": entity_count,
        "uneliminated_intercompany": str(_amount(intercompany)),
        "source": "posted_ledger",
    }


async def payroll_cost_report(db: AsyncSession, user: User, *, period: str | None = None) -> list[dict[str, Any]]:
    _period(period) if period else None
    stmt = select(PayrollRun, func.sum(Payslip.gross), func.sum(Payslip.pf), func.sum(Payslip.esi), func.sum(Payslip.tds), func.sum(Payslip.net)).outerjoin(
        Payslip, Payslip.payroll_run_id == PayrollRun.id
    ).where(PayrollRun.status.in_(("processed", "posted"))).group_by(PayrollRun.id)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(PayrollRun.tenant_id == user.tenant_id)
    if period:
        stmt = stmt.where(PayrollRun.period == period)
    rows = (await db.execute(stmt)).all()
    return [
        {
            "period": run.period,
            "gross": str(_amount(gross)),
            "pf": str(_amount(pf)),
            "esi": str(_amount(esi)),
            "tds": str(_amount(tds)),
            "net": str(_amount(net)),
            "posted": run.journal_entry_id is not None,
        }
        for run, gross, pf, esi, tds, net in rows
    ]


async def asset_register_report(db: AsyncSession, user: User) -> list[dict[str, Any]]:
    stmt = select(FixedAsset).order_by(FixedAsset.asset_tag)
    stmt = _scope(stmt, FixedAsset, user)
    assets = list((await db.scalars(stmt)).all())
    return [
        {
            "asset_tag": asset.asset_tag,
            "name": asset.name,
            "cost": str(asset.cost),
            "accumulated_depreciation": str(asset.accumulated_depreciation),
            "net_book_value": str(asset.cost - asset.accumulated_depreciation - asset.impairment_loss),
            "status": asset.status,
            "in_service_date": str(asset.in_service_date),
        }
        for asset in assets
    ]


async def bank_reconciliation_report(db: AsyncSession, user: User) -> dict[str, Any]:
    stmt = select(BankAccount)
    stmt = _scope(stmt, BankAccount, user)
    accounts = list((await db.scalars(stmt)).all())
    result = []
    for account in accounts:
        bank_total = await db.scalar(
            select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
                BankTransaction.bank_account_id == account.id, BankTransaction.is_active.is_(True)
            )
        )
        matched = await db.scalar(
            select(func.coalesce(func.sum(BankTransaction.amount), 0)).where(
                BankTransaction.bank_account_id == account.id,
                BankTransaction.reconciled.is_(True),
                BankTransaction.is_active.is_(True),
            )
        )
        result.append(
            {
                "bank_account_id": str(account.id),
                "name": account.name,
                "opening_balance": str(account.opening_balance),
                "bank_movement": str(_amount(bank_total)),
                "matched_movement": str(_amount(matched)),
                "unmatched_movement": str(_amount(bank_total) - _amount(matched)),
            }
        )
    return {"accounts": result}
