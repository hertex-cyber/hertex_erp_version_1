from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.events import publish
from app.core.exceptions import ConflictError, ValidationError
from app.core.numbering import next_number
from app.modules.finance.models import (
    Account,
    BankAccount,
    BankTransaction,
    FinanceApproval,
    FinancialPeriod,
    GRNAccrual,
    Invoice,
    InvoiceTaxLine,
    JournalEntry,
    JournalLine,
    Payment,
    TaxCode,
    TaxRegistration,
    VendorPayment,
)
from app.modules.finance.schemas import (
    JournalEntryCreate,
    JournalReversalCreate,
    PaymentCreate,
    ReceivableRow,
    TrialBalanceRow,
)
from app.modules.identity.models import User
from app.modules.inventory.models import StockMove
from app.modules.procurement.models import (
    GoodsReceipt,
    GoodsReceiptLine,
    POLine,
    VendorInvoice,
    VendorInvoiceTaxLine,
)

# Canonical chart-of-accounts codes shared with the seed data.
CASH = "1010"
ACCOUNTS_RECEIVABLE = "1100"
INVENTORY = "1200"
ACCOUNTS_PAYABLE = "2000"
GOODS_RECEIVED_NOT_INVOICED = "2100"
SALES_REVENUE = "4000"
INVENTORY_ADJUSTMENT_EXPENSE = "5000"
SALARIES_EXPENSE = "5200"
PAYROLL_LIABILITIES = {
    "pf": ("2210", "provident fund payable"),
    "esi": ("2220", "employee state insurance payable"),
    "tds": ("2230", "payroll TDS payable"),
    "net": ("2240", "net salaries payable"),
}
GST_STATE_CODES = frozenset(
    {
        *(f"{code:02d}" for code in range(1, 39)),
        "96",
        "97",
        "99",
    }
)


async def _account_by_code(
    db: AsyncSession, tenant_id, code: str
) -> Optional[Account]:
    stmt = select(Account).where(Account.code == code, Account.is_active.is_(True))
    if tenant_id:
        stmt = stmt.where(Account.tenant_id == tenant_id)
    return await db.scalar(stmt)


async def _require_account(
    db: AsyncSession, tenant_id, code: str, label: str
) -> Account:
    account = await _account_by_code(db, tenant_id, code)
    if account is None:
        raise ValidationError(
            f"Chart of accounts is missing the {label} account ({code}); import or create it first"
        )
    return account


def _validate_lines(lines: list) -> tuple[Decimal, Decimal]:
    total_debit = sum((line.debit or Decimal("0") for line in lines), Decimal("0"))
    total_credit = sum((line.credit or Decimal("0") for line in lines), Decimal("0"))
    if total_debit != total_credit:
        raise ValidationError(
            f"Journal entry is unbalanced: debit {total_debit} != credit {total_credit}"
        )
    if total_debit <= 0:
        raise ValidationError("Journal entry must have a non-zero amount")
    for line in lines:
        debit = line.debit or Decimal("0")
        credit = line.credit or Decimal("0")
        if (debit > 0) == (credit > 0):
            raise ValidationError("Each journal line must have either a debit or a credit")
        if debit < 0 or credit < 0:
            raise ValidationError("Debit and credit values cannot be negative")
        if debit >= Decimal("1000000000000") or credit >= Decimal("1000000000000"):
            raise ValidationError("Journal amounts exceed the supported precision")
        if debit != debit.quantize(Decimal("0.01")) or credit != credit.quantize(Decimal("0.01")):
            raise ValidationError("Journal amounts cannot have more than two decimal places")
    return total_debit, total_credit


async def tenant_has_gst_setup(db: AsyncSession, tenant_id: UUID) -> bool:
    return bool(
        await db.scalar(
            select(TaxRegistration.id)
            .where(
                TaxRegistration.tenant_id == tenant_id,
                TaxRegistration.is_active.is_(True),
            )
            .limit(1)
        )
    )


async def calculate_tax_snapshot(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    tax_code_id: UUID,
    registration_id: UUID,
    place_of_supply_state_code: str,
    taxable_amount: Decimal,
    description: Optional[str] = None,
) -> dict:
    if taxable_amount < 0 or taxable_amount != taxable_amount.quantize(Decimal("0.01")):
        raise ValidationError("Taxable amount cannot be negative or have more than two decimals")
    registration = await db.scalar(
        select(TaxRegistration).where(
            TaxRegistration.id == registration_id,
            TaxRegistration.tenant_id == tenant_id,
            TaxRegistration.is_active.is_(True),
        )
    )
    if registration is None:
        raise ValidationError("GST registration must be active and belong to this tenant")
    if registration.state_code not in GST_STATE_CODES:
        raise ValidationError("GST registration has an invalid state code")
    if place_of_supply_state_code not in GST_STATE_CODES:
        raise ValidationError("Place of supply must be a valid two-digit Indian GST state code")
    code = await db.scalar(
        select(TaxCode).where(
            TaxCode.id == tax_code_id,
            TaxCode.tenant_id == tenant_id,
            TaxCode.is_active.is_(True),
        )
    )
    if code is None:
        raise ValidationError("GST tax code must be active and belong to this tenant")
    if code.cgst_rate + code.sgst_rate != code.igst_rate:
        raise ValidationError("GST tax code has inconsistent component rates")
    if code.tax_type != "taxable" and any(
        (code.cgst_rate, code.sgst_rate, code.igst_rate)
    ):
        raise ValidationError("Non-taxable GST codes cannot have tax rates")

    same_state = registration.state_code == place_of_supply_state_code
    cgst_rate = code.cgst_rate if same_state and code.tax_type == "taxable" else Decimal("0")
    sgst_rate = code.sgst_rate if same_state and code.tax_type == "taxable" else Decimal("0")
    igst_rate = code.igst_rate if not same_state and code.tax_type == "taxable" else Decimal("0")
    cgst_amount = (taxable_amount * cgst_rate / Decimal("100")).quantize(Decimal("0.01"))
    sgst_amount = (taxable_amount * sgst_rate / Decimal("100")).quantize(Decimal("0.01"))
    igst_amount = (taxable_amount * igst_rate / Decimal("100")).quantize(Decimal("0.01"))
    output_accounts = {
        "cgst": code.output_cgst_account_id,
        "sgst": code.output_sgst_account_id,
        "igst": code.output_igst_account_id,
    }
    input_accounts = {
        "cgst": code.input_cgst_account_id,
        "sgst": code.input_sgst_account_id,
        "igst": code.input_igst_account_id,
    }
    amounts = {"cgst": cgst_amount, "sgst": sgst_amount, "igst": igst_amount}
    for component, amount in amounts.items():
        if amount == 0:
            continue
        if output_accounts[component] is None:
            raise ValidationError(f"Tax code has no output liability mapping for {component.upper()}")
        output_account = await db.scalar(
            select(Account).where(
                Account.id == output_accounts[component],
                Account.tenant_id == tenant_id,
                Account.account_type == "liability",
                Account.is_active.is_(True),
            )
        )
        if output_account is None:
            raise ValidationError(f"Output {component.upper()} account must be an active liability")
        if code.can_claim_itc:
            if input_accounts[component] is None:
                raise ValidationError(f"Tax code has no input asset mapping for {component.upper()}")
            input_account = await db.scalar(
                select(Account).where(
                    Account.id == input_accounts[component],
                    Account.tenant_id == tenant_id,
                    Account.account_type == "asset",
                    Account.is_active.is_(True),
                )
            )
            if input_account is None:
                raise ValidationError(f"Input {component.upper()} account must be an active asset")

    return {
        "tax_code_id": code.id,
        "registration_id": registration.id,
        "tax_type_snapshot": code.tax_type,
        "can_claim_itc_snapshot": code.can_claim_itc,
        "description": description,
        "place_of_supply_state_code": place_of_supply_state_code,
        "taxable_amount": taxable_amount,
        "cgst_rate": cgst_rate,
        "sgst_rate": sgst_rate,
        "igst_rate": igst_rate,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "igst_amount": igst_amount,
        "output_cgst_account_id": output_accounts["cgst"],
        "output_sgst_account_id": output_accounts["sgst"],
        "output_igst_account_id": output_accounts["igst"],
        "input_cgst_account_id": input_accounts["cgst"] if code.can_claim_itc else None,
        "input_sgst_account_id": input_accounts["sgst"] if code.can_claim_itc else None,
        "input_igst_account_id": input_accounts["igst"] if code.can_claim_itc else None,
    }


def tax_line_totals(lines) -> tuple[Decimal, Decimal]:
    taxable = sum((line.taxable_amount for line in lines), Decimal("0"))
    tax = sum(
        (line.cgst_amount + line.sgst_amount + line.igst_amount for line in lines),
        Decimal("0"),
    )
    return taxable, tax


async def _tax_journal_lines(
    db: AsyncSession,
    tenant_id: UUID,
    journal_entry_id: UUID,
    tax_lines,
    *,
    output: bool,
) -> list[JournalLine]:
    totals: dict[UUID, Decimal] = {}
    for tax_line in tax_lines:
        for component in ("cgst", "sgst", "igst"):
            amount = getattr(tax_line, f"{component}_amount")
            account_id = getattr(
                tax_line,
                f"{'output' if output else 'input'}_{component}_account_id",
            )
            if amount:
                if account_id is None:
                    side = "output liability" if output else "input credit"
                    raise ValidationError(f"GST tax line has no {side} account mapping")
                totals[account_id] = totals.get(account_id, Decimal("0")) + amount
    expected_type = "liability" if output else "asset"
    if totals:
        valid_accounts = set(
            (
                await db.scalars(
                    select(Account.id).where(
                        Account.id.in_(totals),
                        Account.tenant_id == tenant_id,
                        Account.account_type == expected_type,
                        Account.is_active.is_(True),
                    )
                )
            ).all()
        )
        if valid_accounts != set(totals):
            raise ValidationError(
                f"GST tax accounts must remain active same-tenant {expected_type} accounts before posting"
            )
    return [
        JournalLine(
            tenant_id=tenant_id,
            journal_entry_id=journal_entry_id,
            account_id=account_id,
            description="Output GST liability" if output else "Recoverable input GST",
            debit=Decimal("0") if output else amount,
            credit=amount if output else Decimal("0"),
        )
        for account_id, amount in totals.items()
    ]


async def ensure_period_open(db: AsyncSession, tenant_id, entry_date: date) -> None:
    tenant_periods = select(FinancialPeriod.id).where(FinancialPeriod.tenant_id == tenant_id)
    has_periods = await db.scalar(tenant_periods.limit(1))
    if has_periods is None:
        return

    matching_periods = list(
        (
            await db.scalars(
                select(FinancialPeriod)
                .where(
                    FinancialPeriod.tenant_id == tenant_id,
                    FinancialPeriod.start_date <= entry_date,
                    FinancialPeriod.end_date >= entry_date,
                )
                .with_for_update()
            )
        ).all()
    )
    if not matching_periods:
        raise ValidationError(
            f"No financial period is configured for {entry_date.isoformat()}"
        )
    if len(matching_periods) > 1:
        raise ConflictError("Overlapping financial periods prevent posting")
    period = matching_periods[0]
    if period.status != "open":
        raise ValidationError(f"Financial period '{period.name}' is closed")


async def create_financial_period(
    db: AsyncSession, user: User, *, name: str, start_date: date, end_date: date
) -> FinancialPeriod:
    if start_date > end_date:
        raise ValidationError("Period start date must be on or before its end date")

    overlap = select(FinancialPeriod.id).where(
        FinancialPeriod.tenant_id == user.tenant_id,
        FinancialPeriod.start_date <= end_date,
        FinancialPeriod.end_date >= start_date,
    )
    if await db.scalar(overlap.limit(1)):
        raise ConflictError("Financial periods cannot overlap")

    period = FinancialPeriod(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        name=name.strip(),
        start_date=start_date,
        end_date=end_date,
        status="open",
    )
    db.add(period)
    await db.flush()
    return period


async def set_financial_period_status(
    db: AsyncSession, user: User, period: FinancialPeriod, *, status: str
) -> FinancialPeriod:
    if period.status == status:
        return period

    if status == "closed":
        if period.close_signed_at is None or period.close_signed_by_id is None:
            raise ConflictError("Period close requires a recorded sign-off")
        draft_count = await db.scalar(
            select(func.count())
            .select_from(JournalEntry)
            .where(
                JournalEntry.tenant_id == period.tenant_id,
                JournalEntry.entry_date >= period.start_date,
                JournalEntry.entry_date <= period.end_date,
                JournalEntry.status == "draft",
                JournalEntry.is_active.is_(True),
            )
        )
        if draft_count:
            raise ConflictError(
                f"Cannot close this period while {draft_count} draft journal "
                f"{'entry' if draft_count == 1 else 'entries'} remain"
            )
        period.closed_by_id = user.id
        period.closed_at = datetime.now(timezone.utc)
    else:
        period.closed_by_id = None
        period.closed_at = None
        period.close_signed_by_id = None
        period.close_signed_at = None
        period.close_signoff_reason = None

    period.status = status
    await db.flush()
    return period


async def create_journal_entry(
    db: AsyncSession, user: User, payload: JournalEntryCreate
) -> JournalEntry:
    _validate_lines(payload.lines)
    await ensure_period_open(db, user.tenant_id, payload.entry_date)
    account_ids = {line.account_id for line in payload.lines}
    account_stmt = select(Account.id).where(
        Account.id.in_(account_ids),
        Account.tenant_id == user.tenant_id,
        Account.is_active.is_(True),
    )
    valid_account_ids = set((await db.scalars(account_stmt)).all())
    if valid_account_ids != account_ids:
        raise ValidationError("Every journal line must use an active account in this tenant")

    number = await next_number(db, JournalEntry, "entry_number", "JE", user.tenant_id)
    entry = JournalEntry(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=payload.entry_date,
        reference=payload.reference,
        memo=payload.memo,
        status="draft",
    )
    db.add(entry)
    await db.flush()
    for line in payload.lines:
        db.add(
            JournalLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                journal_entry_id=entry.id,
                account_id=line.account_id,
                description=line.description,
                debit=line.debit or Decimal("0"),
                credit=line.credit or Decimal("0"),
            )
        )
    await db.flush()
    return await get_journal_entry(db, user, entry.id)


async def get_journal_entry(db: AsyncSession, user: User, entry_id) -> JournalEntry:
    stmt = (
        select(JournalEntry)
        .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
        .where(JournalEntry.id == entry_id)
        .with_for_update()
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(JournalEntry.tenant_id == user.tenant_id)
    entry = await db.scalar(stmt)
    if entry is None:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Journal entry not found")
    return entry


async def post_journal_entry(db: AsyncSession, user: User, entry: JournalEntry) -> JournalEntry:
    if entry.status == "posted":
        return entry
    await ensure_period_open(db, entry.tenant_id, entry.entry_date)
    _validate_lines(entry.lines)
    account_ids = {line.account_id for line in entry.lines}
    account_stmt = select(Account.id).where(
        Account.id.in_(account_ids),
        Account.tenant_id == entry.tenant_id,
        Account.is_active.is_(True),
    )
    valid_account_ids = set((await db.scalars(account_stmt)).all())
    if valid_account_ids != account_ids:
        raise ValidationError("Every journal line must use an active account in this tenant")
    entry.status = "posted"
    entry.posted_by_id = user.id
    entry.posted_at = datetime.now(timezone.utc)
    await db.flush()
    return entry


async def reverse_journal_entry(
    db: AsyncSession,
    user: User,
    entry: JournalEntry,
    payload: JournalReversalCreate,
) -> tuple[JournalEntry, bool]:
    entry_id = entry.id
    entry_tenant_id = entry.tenant_id
    user_tenant_id = user.tenant_id
    is_superuser = user.is_superuser
    if entry_tenant_id != user_tenant_id and not is_superuser:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Journal entry not found")
    if entry.reversal_of_id is not None:
        raise ConflictError("A reversal journal cannot itself be reversed")
    if entry.status != "posted":
        raise ValidationError("Only posted journal entries can be reversed")
    if not payload.reason.strip():
        raise ValidationError("A reversal reason is required")
    await ensure_period_open(db, entry.tenant_id, payload.reversal_date)

    existing_reversal = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.reversal_of_id == entry.id,
            JournalEntry.tenant_id == entry.tenant_id,
        )
    )
    if existing_reversal is not None:
        return existing_reversal, False

    _validate_lines(entry.lines)
    number = await next_number(db, JournalEntry, "entry_number", "JE", entry_tenant_id)
    reversal = JournalEntry(
        tenant_id=entry.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=payload.reversal_date,
        reference=f"REV:{entry.entry_number}",
        memo=f"Reversal of {entry.entry_number}: {payload.reason.strip()}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
        reversal_of_id=entry.id,
    )
    db.add(reversal)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        reversal_stmt = (
            select(JournalEntry)
            .options(selectinload(JournalEntry.lines).selectinload(JournalLine.account))
            .where(
                JournalEntry.reversal_of_id == entry_id,
                JournalEntry.tenant_id == entry_tenant_id,
            )
        )
        if not is_superuser and user_tenant_id is not None:
            reversal_stmt = reversal_stmt.where(JournalEntry.tenant_id == user_tenant_id)
        existing_reversal = await db.scalar(reversal_stmt)
        if existing_reversal is None:
            raise ConflictError("Journal reversal conflicts with another ledger update") from exc
        return existing_reversal, False
    db.add_all(
        [
            JournalLine(
                tenant_id=entry.tenant_id,
                created_by_id=user.id,
                journal_entry_id=reversal.id,
                account_id=line.account_id,
                description=f"Reversal: {line.description}" if line.description else "Reversal",
                debit=line.credit,
                credit=line.debit,
            )
            for line in entry.lines
        ]
    )
    await db.flush()
    return await get_journal_entry(db, user, reversal.id), True


async def _existing_posting(db: AsyncSession, tenant_id, reference: str) -> bool:
    stmt = select(JournalEntry.id).where(
        JournalEntry.reference == reference, JournalEntry.status == "posted"
    )
    if tenant_id:
        stmt = stmt.where(JournalEntry.tenant_id == tenant_id)
    return (await db.scalar(stmt)) is not None


async def create_invoice_from_proposal(
    db: AsyncSession,
    user: User,
    *,
    customer_id: Optional[UUID],
    issue_date: date,
    due_date: Optional[date],
    subtotal: Decimal,
    tax: Decimal,
    total: Decimal,
    currency: str,
    notes: Optional[str],
    reference: str,
) -> Invoice:
    invoice_number = await next_number(db, Invoice, "invoice_number", "INV", user.tenant_id)
    invoice = Invoice(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        invoice_number=invoice_number,
        customer_id=customer_id,
        issue_date=issue_date,
        due_date=due_date,
        status="sent",
        subtotal=subtotal,
        tax=tax,
        total=total,
        currency=currency,
        notes=f"{notes or ''}\n{reference}".strip(),
    )
    db.add(invoice)
    await db.flush()
    await post_invoice_journal(db, user, invoice)
    return invoice


async def post_invoice_journal(db: AsyncSession, user: User, invoice: Invoice) -> Optional[JournalEntry]:
    """Post AR debit / revenue credit for a customer invoice (idempotent)."""
    if invoice.total <= 0:
        return None
    reference = f"INV:{invoice.invoice_number}"
    if await _existing_posting(db, user.tenant_id, reference):
        return None
    await ensure_period_open(db, user.tenant_id, invoice.issue_date)
    tax_lines = list(
        (
            await db.scalars(
                select(InvoiceTaxLine).where(InvoiceTaxLine.invoice_id == invoice.id)
            )
        ).all()
    )
    if not tax_lines and await tenant_has_gst_setup(db, invoice.tenant_id):
        raise ValidationError("Classify every invoice line with a GST tax code before posting")
    taxable_amount = invoice.total - invoice.tax
    if tax_lines:
        line_taxable, line_tax = tax_line_totals(tax_lines)
        if line_taxable != taxable_amount or line_tax != invoice.tax:
            raise ValidationError("Invoice totals do not match its saved GST line snapshots")
        taxable_amount = line_taxable
    ar = await _require_account(db, user.tenant_id, ACCOUNTS_RECEIVABLE, "accounts receivable")
    revenue = await _require_account(db, user.tenant_id, SALES_REVENUE, "sales revenue")

    number = await next_number(db, JournalEntry, "entry_number", "JE", user.tenant_id)
    entry = JournalEntry(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=invoice.issue_date or date.today(),
        reference=reference,
        memo=f"Sales invoice {invoice.invoice_number}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    journal_lines = [
        JournalLine(
            tenant_id=user.tenant_id,
            journal_entry_id=entry.id,
            account_id=ar.id,
            description="Accounts receivable",
            debit=invoice.total,
            credit=Decimal("0"),
        ),
        JournalLine(
            tenant_id=user.tenant_id,
            journal_entry_id=entry.id,
            account_id=revenue.id,
            description="Sales revenue",
            debit=Decimal("0"),
            credit=taxable_amount if tax_lines else invoice.total,
        ),
    ]
    journal_lines.extend(
        await _tax_journal_lines(
            db,
            invoice.tenant_id,
            entry.id,
            tax_lines,
            output=True,
        )
    )
    db.add_all(journal_lines)
    await db.flush()
    return entry


async def post_vendor_invoice_journal(
    db: AsyncSession, user: User, invoice: VendorInvoice
) -> Optional[JournalEntry]:
    """Post inventory debit / accounts-payable credit for an approved vendor invoice."""
    if invoice.tenant_id != user.tenant_id and not user.is_superuser:
        from app.core.exceptions import NotFoundError

        raise NotFoundError("Vendor invoice not found")
    if invoice.status != "approved":
        raise ValidationError("Only an approved vendor invoice can be posted")
    total = (invoice.amount or Decimal("0")) + (invoice.tax_amount or Decimal("0"))
    if total <= 0:
        raise ValidationError("Vendor invoice total must be greater than zero")
    tenant_id = invoice.tenant_id
    reference = f"VINV:{invoice.invoice_number}"
    if await _existing_posting(db, tenant_id, reference):
        return None
    await ensure_period_open(db, tenant_id, invoice.issue_date)
    tax_lines = list(
        (
            await db.scalars(
                select(VendorInvoiceTaxLine).where(
                    VendorInvoiceTaxLine.invoice_id == invoice.id
                )
            )
        ).all()
    )
    if not tax_lines and await tenant_has_gst_setup(db, tenant_id):
        raise ValidationError("Classify every vendor invoice line with a GST tax code before approval")
    if tax_lines:
        line_taxable, line_tax = tax_line_totals(tax_lines)
        if line_taxable != invoice.amount or line_tax != invoice.tax_amount:
            raise ValidationError("Vendor invoice totals do not match its saved GST line snapshots")
    goods_receipts = list(
        (
            await db.scalars(
                select(GoodsReceipt)
                .where(
                    GoodsReceipt.purchase_order_id == invoice.purchase_order_id,
                    GoodsReceipt.tenant_id == tenant_id,
                )
                .with_for_update()
            )
        ).all()
    )
    if not goods_receipts:
        raise ValidationError(
            "Vendor invoice cannot post until its goods receipts have been accrued"
        )
    receipts = list(
        (
            await db.scalars(
                select(GRNAccrual)
                .where(
                    GRNAccrual.goods_receipt_id.in_(
                        [receipt.id for receipt in goods_receipts]
                    )
                )
                .with_for_update()
            )
        ).all()
    )
    if len(receipts) != len(goods_receipts):
        raise ValidationError(
            "A goods receipt predates GRNI posting and requires reconciliation before invoice approval"
        )
    if any(receipt.cleared_by_invoice_id is not None for receipt in receipts):
        raise ConflictError("Goods receipt accruals are already cleared by another invoice")
    accrued_amount = sum(
        (receipt.accrued_amount for receipt in receipts), Decimal("0")
    )
    if accrued_amount <= 0:
        raise ValidationError("Goods receipt accrual total must be greater than zero")

    inventory = await _require_account(db, tenant_id, INVENTORY, "inventory")
    payable = await _require_account(db, tenant_id, ACCOUNTS_PAYABLE, "accounts payable")
    grni = await _require_account(
        db, tenant_id, GOODS_RECEIVED_NOT_INVOICED, "goods received not invoiced"
    )

    number = await next_number(db, JournalEntry, "entry_number", "JE", tenant_id)
    entry = JournalEntry(
        tenant_id=tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=invoice.issue_date,
        reference=reference,
        memo=f"Vendor invoice {invoice.invoice_number}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    recoverable_tax_lines = await _tax_journal_lines(
        db,
        tenant_id,
        entry.id,
        tax_lines,
        output=False,
    )
    recoverable_tax = sum((line.debit for line in recoverable_tax_lines), Decimal("0"))
    inventory_cost = invoice.amount + (invoice.tax_amount - recoverable_tax)
    lines = [
        JournalLine(
            tenant_id=tenant_id,
            journal_entry_id=entry.id,
            account_id=grni.id,
            description="Clear goods received not invoiced",
            debit=accrued_amount,
            credit=Decimal("0"),
        ),
        JournalLine(
            tenant_id=tenant_id,
            journal_entry_id=entry.id,
            account_id=payable.id,
            description="Accounts payable",
            debit=Decimal("0"),
            credit=total,
        ),
        *recoverable_tax_lines,
    ]
    variance = inventory_cost - accrued_amount
    if variance > 0:
        lines.append(
            JournalLine(
                tenant_id=tenant_id,
                journal_entry_id=entry.id,
                account_id=inventory.id,
                description="Invoice amount and tax above GRNI accrual",
                debit=variance,
                credit=Decimal("0"),
            )
        )
    elif variance < 0:
        lines.append(
            JournalLine(
                tenant_id=tenant_id,
                journal_entry_id=entry.id,
                account_id=inventory.id,
                description="Invoice amount below GRNI accrual",
                debit=Decimal("0"),
                credit=-variance,
            )
        )
    db.add_all(lines)
    for receipt in receipts:
        receipt.cleared_by_invoice_id = invoice.id
    await db.flush()
    return entry


async def post_goods_receipt_accrual(
    db: AsyncSession,
    user: User,
    receipt: GoodsReceipt,
) -> Optional[JournalEntry]:
    """Accrue received PO value to inventory and the GRNI control account."""
    tenant_id = receipt.tenant_id
    if receipt.journal_entry_id is not None:
        return await db.get(JournalEntry, receipt.journal_entry_id)
    existing_accrual = await db.scalar(
        select(GRNAccrual).where(GRNAccrual.goods_receipt_id == receipt.id)
    )
    if existing_accrual is not None:
        return await db.get(JournalEntry, existing_accrual.journal_entry_id)

    receipt_lines = list(
        (
            await db.execute(
                select(GoodsReceiptLine, POLine.unit_price)
                .join(POLine, POLine.id == GoodsReceiptLine.po_line_id)
                .where(GoodsReceiptLine.grn_id == receipt.id)
            )
        ).all()
    )
    accrued_amount = sum(
        (
            line.quantity_received * unit_price
            for line, unit_price in receipt_lines
        ),
        Decimal("0"),
    ).quantize(Decimal("0.01"))
    if accrued_amount <= 0:
        raise ValidationError("Goods receipt must have a positive received value")
    await ensure_period_open(db, tenant_id, receipt.received_date)
    inventory = await _require_account(db, tenant_id, INVENTORY, "inventory")
    grni = await _require_account(
        db, tenant_id, GOODS_RECEIVED_NOT_INVOICED, "goods received not invoiced"
    )
    number = await next_number(db, JournalEntry, "entry_number", "JE", tenant_id)
    entry = JournalEntry(
        tenant_id=tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=receipt.received_date,
        reference=f"GRN:{receipt.grn_number}",
        memo=f"Goods receipt accrual {receipt.grn_number}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    db.add_all(
        [
            JournalLine(
                tenant_id=tenant_id,
                journal_entry_id=entry.id,
                account_id=inventory.id,
                description="Inventory received",
                debit=accrued_amount,
                credit=Decimal("0"),
            ),
            JournalLine(
                tenant_id=tenant_id,
                journal_entry_id=entry.id,
                account_id=grni.id,
                description="Goods received not invoiced",
                debit=Decimal("0"),
                credit=accrued_amount,
            ),
        ]
    )
    db.add(
        GRNAccrual(
            tenant_id=tenant_id,
            created_by_id=user.id,
            goods_receipt_id=receipt.id,
            journal_entry_id=entry.id,
            accrued_amount=accrued_amount,
        )
    )
    receipt.journal_entry_id = entry.id
    await db.flush()
    return entry


async def post_inventory_adjustment_journal(
    db: AsyncSession,
    user: User,
    stock_move: StockMove,
    *,
    entry_date: date,
) -> JournalEntry:
    """Post the GL impact of a signed inventory count adjustment."""
    if stock_move.tenant_id != user.tenant_id and not user.is_superuser:
        raise ValidationError("Inventory adjustment belongs to a different tenant")
    if stock_move.movement_type != "adjustment":
        raise ValidationError("Only inventory adjustments can use this posting workflow")
    if stock_move.journal_entry_id is not None:
        entry = await db.get(JournalEntry, stock_move.journal_entry_id)
        if entry is None:
            raise ValidationError("Inventory adjustment has a missing journal link")
        return entry

    reference = f"INVADJ:{stock_move.id}"
    existing = await db.scalar(
        select(JournalEntry).where(
            JournalEntry.tenant_id == stock_move.tenant_id,
            JournalEntry.reference == reference,
            JournalEntry.status == "posted",
        )
    )
    if existing is not None:
        stock_move.journal_entry_id = existing.id
        stock_move.status = "posted"
        await db.flush()
        return existing

    amount = (abs(stock_move.quantity) * stock_move.unit_cost).quantize(Decimal("0.01"))
    if amount <= 0:
        raise ValidationError("Inventory adjustment value must be greater than zero")
    if amount >= Decimal("1000000000000"):
        raise ValidationError("Inventory adjustment value exceeds supported ledger precision")
    await ensure_period_open(db, stock_move.tenant_id, entry_date)
    inventory = await _require_account(db, stock_move.tenant_id, INVENTORY, "inventory")
    adjustment_expense = await _require_account(
        db,
        stock_move.tenant_id,
        INVENTORY_ADJUSTMENT_EXPENSE,
        "inventory adjustment expense",
    )
    if inventory.account_type != "asset":
        raise ValidationError("Inventory ledger account must be an asset account")
    if adjustment_expense.account_type != "expense":
        raise ValidationError("Inventory adjustment account must be an expense account")

    quantity_increase = stock_move.quantity > 0
    number = await next_number(db, JournalEntry, "entry_number", "JE", stock_move.tenant_id)
    entry = JournalEntry(
        tenant_id=stock_move.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=entry_date,
        reference=reference,
        memo=f"Inventory adjustment: {stock_move.reason}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    db.add_all(
        [
            JournalLine(
                tenant_id=stock_move.tenant_id,
                created_by_id=user.id,
                journal_entry_id=entry.id,
                account_id=inventory.id,
                description="Inventory adjustment",
                debit=amount if quantity_increase else Decimal("0"),
                credit=Decimal("0") if quantity_increase else amount,
            ),
            JournalLine(
                tenant_id=stock_move.tenant_id,
                created_by_id=user.id,
                journal_entry_id=entry.id,
                account_id=adjustment_expense.id,
                description="Inventory adjustment offset",
                debit=Decimal("0") if quantity_increase else amount,
                credit=amount if quantity_increase else Decimal("0"),
            ),
        ]
    )
    stock_move.journal_entry_id = entry.id
    stock_move.status = "posted"
    await db.flush()
    return entry


async def submit_finance_approval(
    db: AsyncSession,
    user: User,
    *,
    entity_type: str,
    entity_id: UUID,
    amount: Decimal,
    summary: str,
    tenant_id: Optional[UUID] = None,
) -> FinanceApproval:
    if entity_type not in {"journal_entry", "vendor_payment", "inventory_adjustment"}:
        raise ValidationError("Unsupported accounting approval type")
    if amount <= 0 or amount >= Decimal("1000000000000"):
        raise ValidationError("Approval amount must be positive and within ledger precision")
    approval = FinanceApproval(
        tenant_id=tenant_id or user.tenant_id,
        created_by_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        amount=amount.quantize(Decimal("0.01")),
        summary=summary[:255],
        requested_by_id=user.id,
        status="pending",
    )
    db.add(approval)
    await db.flush()
    return approval


async def post_vendor_payment_journal(
    db: AsyncSession,
    user: User,
    payment: VendorPayment,
) -> JournalEntry:
    if payment.tenant_id != user.tenant_id and not user.is_superuser:
        raise ValidationError("Vendor payment belongs to a different tenant")
    if payment.status == "posted" and payment.journal_entry_id is not None:
        entry = await db.get(JournalEntry, payment.journal_entry_id)
        if entry is None:
            raise ValidationError("Vendor payment has a missing journal link")
        return entry
    if payment.status != "pending_approval":
        raise ValidationError("Only a pending vendor payment can be approved")

    invoice = await db.scalar(
        select(VendorInvoice)
        .where(
            VendorInvoice.id == payment.vendor_invoice_id,
            VendorInvoice.tenant_id == payment.tenant_id,
        )
        .with_for_update()
    )
    if invoice is None or invoice.status not in {"approved", "partially_paid"}:
        raise ValidationError("Vendor invoice is no longer available for settlement")
    invoice_total = invoice.amount + invoice.tax_amount
    pending_total = await db.scalar(
        select(func.coalesce(func.sum(VendorPayment.amount), 0)).where(
            VendorPayment.vendor_invoice_id == invoice.id,
            VendorPayment.status == "pending_approval",
            VendorPayment.id != payment.id,
        )
    )
    if payment.amount > invoice_total - invoice.paid_amount - Decimal(pending_total or 0):
        raise ConflictError("Approved payments and pending requests exceed the invoice balance")
    await ensure_period_open(db, payment.tenant_id, payment.paid_on)
    if payment.method == "cash":
        settlement_account = await _require_account(db, payment.tenant_id, CASH, "cash")
    else:
        bank_account = await db.scalar(
            select(BankAccount).where(
                BankAccount.id == payment.bank_account_id,
                BankAccount.tenant_id == payment.tenant_id,
                BankAccount.is_active.is_(True),
            )
        )
        if bank_account is None or bank_account.ledger_account_id is None:
            raise ValidationError("Vendor payment bank account is no longer valid")
        settlement_account = await db.scalar(
            select(Account).where(
                Account.id == bank_account.ledger_account_id,
                Account.tenant_id == payment.tenant_id,
                Account.account_type == "asset",
                Account.is_active.is_(True),
            )
        )
        if settlement_account is None:
            raise ValidationError("Vendor payment bank mapping must be an active asset account")
    payable = await _require_account(db, payment.tenant_id, ACCOUNTS_PAYABLE, "accounts payable")
    invoice.paid_amount += payment.amount
    invoice.status = "paid" if invoice.paid_amount == invoice_total else "partially_paid"

    number = await next_number(db, JournalEntry, "entry_number", "JE", payment.tenant_id)
    entry = JournalEntry(
        tenant_id=payment.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=payment.paid_on,
        reference=f"VPAY:{payment.id}",
        memo=f"Payment for vendor invoice {invoice.invoice_number}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    db.add_all(
        [
            JournalLine(
                tenant_id=payment.tenant_id,
                created_by_id=user.id,
                journal_entry_id=entry.id,
                account_id=payable.id,
                description=f"Accounts payable settled: {invoice.invoice_number}",
                debit=payment.amount,
                credit=Decimal("0"),
            ),
            JournalLine(
                tenant_id=payment.tenant_id,
                created_by_id=user.id,
                journal_entry_id=entry.id,
                account_id=settlement_account.id,
                description=f"{payment.method.title()} vendor payment",
                debit=Decimal("0"),
                credit=payment.amount,
            ),
        ]
    )
    payment.status = "posted"
    payment.journal_entry_id = entry.id
    await db.flush()
    return entry


async def post_payroll_journal(
    db: AsyncSession,
    user: User,
    payroll_run,
    *,
    entry_date: date,
    gross: Decimal,
    pf: Decimal,
    esi: Decimal,
    tds: Decimal,
    net: Decimal,
) -> JournalEntry:
    """Accrue payroll expense and employee deductions to their payable accounts."""
    if payroll_run.tenant_id != user.tenant_id and not user.is_superuser:
        raise ValidationError("Payroll run belongs to a different tenant")
    if payroll_run.journal_entry_id is not None:
        entry = await db.get(JournalEntry, payroll_run.journal_entry_id)
        if entry is None:
            raise ValidationError("Payroll run has a missing journal link")
        return entry
    amounts = {"pf": pf, "esi": esi, "tds": tds, "net": net}
    all_amounts = [gross, *amounts.values()]
    if any(
        not amount.is_finite()
        or amount < 0
        or amount >= Decimal("1000000000000")
        or amount != amount.quantize(Decimal("0.01"))
        for amount in all_amounts
    ):
        raise ValidationError("Payroll amounts exceed supported ledger precision")
    if gross <= 0:
        raise ValidationError("Payroll totals must contain positive gross and non-negative payables")
    if sum(amounts.values(), Decimal("0")) != gross:
        raise ValidationError("Payroll gross must equal net pay plus all deductions")
    await ensure_period_open(db, payroll_run.tenant_id, entry_date)

    salary_account = await _require_account(
        db, payroll_run.tenant_id, SALARIES_EXPENSE, "salaries expense"
    )
    if salary_account.account_type != "expense":
        raise ValidationError("Salaries account (5200) must be an expense account")
    accounts = {}
    for key, (code, label) in PAYROLL_LIABILITIES.items():
        if amounts[key] == 0:
            continue
        account = await _require_account(db, payroll_run.tenant_id, code, label)
        if account.account_type != "liability":
            raise ValidationError(f"Payroll account ({code}) must be a liability account")
        accounts[key] = account

    number = await next_number(db, JournalEntry, "entry_number", "JE", payroll_run.tenant_id)
    entry = JournalEntry(
        tenant_id=payroll_run.tenant_id,
        created_by_id=user.id,
        entry_number=number,
        entry_date=entry_date,
        reference=f"PAYROLL:{payroll_run.period}:{payroll_run.id}",
        memo=f"Payroll accrual for {payroll_run.period}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    lines = [
        JournalLine(
            tenant_id=payroll_run.tenant_id,
            created_by_id=user.id,
            journal_entry_id=entry.id,
            account_id=salary_account.id,
            description=f"Gross salaries for {payroll_run.period}",
            debit=gross,
            credit=Decimal("0"),
        )
    ]
    for key, amount in amounts.items():
        if amount == 0:
            continue
        lines.append(
            JournalLine(
                tenant_id=payroll_run.tenant_id,
                created_by_id=user.id,
                journal_entry_id=entry.id,
                account_id=accounts[key].id,
                description=f"{key.upper()} payable" if key != "net" else "Net salaries payable",
                debit=Decimal("0"),
                credit=amount,
            )
        )
    db.add_all(lines)
    payroll_run.journal_entry_id = entry.id
    await db.flush()
    return entry


async def create_payment(
    db: AsyncSession,
    user: User,
    invoice: Invoice,
    payload: PaymentCreate,
    *,
    idempotency_key: str,
) -> tuple[Payment, bool]:
    idempotency_key = idempotency_key.strip()
    if len(idempotency_key) < 8 or len(idempotency_key) > 128:
        raise ValidationError("Idempotency-Key must be between 8 and 128 characters")

    existing = await db.scalar(
        select(Payment).where(
            Payment.tenant_id == user.tenant_id,
            Payment.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if not payment_matches_request(existing, invoice.id, payload):
            raise ConflictError("Idempotency-Key was already used for a different payment")
        return existing, False

    if invoice.status not in {"sent", "partially_paid", "overdue"}:
        raise ValidationError("Payments can only be recorded against a posted, unpaid invoice")
    outstanding = invoice.total - invoice.amount_paid
    if payload.amount > outstanding:
        raise ValidationError(f"Payment exceeds outstanding balance of {outstanding}")
    if payload.amount != payload.amount.quantize(Decimal("0.01")):
        raise ValidationError("Payment amount cannot have more than two decimal places")
    if payload.amount >= Decimal("1000000000000"):
        raise ValidationError("Payment amount exceeds the supported precision")
    await ensure_period_open(db, user.tenant_id, payload.paid_on)

    if payload.method == "cash":
        if payload.bank_account_id is not None:
            raise ValidationError("Cash payments cannot be assigned to a bank account")
        settlement_account = await _require_account(
            db, user.tenant_id, CASH, "cash"
        )
    else:
        if payload.bank_account_id is None:
            raise ValidationError("Select the bank account that received this payment")
        bank_account = await db.scalar(
            select(BankAccount).where(
                BankAccount.id == payload.bank_account_id,
                BankAccount.tenant_id == user.tenant_id,
                BankAccount.is_active.is_(True),
            )
        )
        if bank_account is None:
            raise ValidationError("Bank account must be active and belong to this tenant")
        if bank_account.currency != invoice.currency:
            raise ValidationError("Bank account currency must match the invoice currency")
        if bank_account.ledger_account_id is None:
            raise ValidationError("Map the bank account to an active GL account before posting")
        settlement_account = await db.scalar(
            select(Account).where(
                Account.id == bank_account.ledger_account_id,
                Account.tenant_id == user.tenant_id,
                Account.account_type == "asset",
                Account.is_active.is_(True),
            )
        )
        if settlement_account is None:
            raise ValidationError("Bank account GL mapping must be an active asset account")

    payment = Payment(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        invoice_id=invoice.id,
        idempotency_key=idempotency_key,
        bank_account_id=payload.bank_account_id,
        amount=payload.amount,
        method=payload.method,
        paid_on=payload.paid_on,
        reference=payload.reference,
        notes=payload.notes,
    )
    db.add(payment)
    await db.flush()
    invoice.amount_paid = invoice.amount_paid + payload.amount
    invoice.status = "paid" if invoice.amount_paid == invoice.total else "partially_paid"

    ar = await _require_account(db, user.tenant_id, ACCOUNTS_RECEIVABLE, "accounts receivable")
    number = await next_number(db, JournalEntry, "entry_number", "JE", user.tenant_id)
    entry = JournalEntry(
        tenant_id=user.tenant_id,
        entry_number=number,
        entry_date=payload.paid_on,
        reference=f"PAY:{payment.id}",
        memo=f"Payment for invoice {invoice.invoice_number}",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    db.add_all(
        [
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=entry.id,
                account_id=settlement_account.id,
                description=f"{payload.method.title()} payment received",
                debit=payload.amount,
                credit=Decimal("0"),
            ),
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=entry.id,
                account_id=ar.id,
                description="Accounts receivable settled",
                debit=Decimal("0"),
                credit=payload.amount,
            ),
        ]
    )
    await db.flush()
    payment.journal_entry_id = entry.id
    await db.flush()
    await publish(
        "invoice.paid",
        {
            "invoice_id": str(invoice.id),
            "payment_id": str(payment.id),
            "tenant_id": str(user.tenant_id) if user.tenant_id else None,
            "amount": str(payload.amount),
            "paid_at": payload.paid_on.isoformat() if hasattr(payload.paid_on, "isoformat") else str(payload.paid_on),
            "invoice_status": invoice.status,
        },
    )
    return payment, True


async def create_vendor_payment(
    db: AsyncSession,
    user: User,
    invoice: VendorInvoice,
    payload,
    *,
    idempotency_key: str,
) -> tuple[VendorPayment, bool]:
    idempotency_key = idempotency_key.strip()
    if len(idempotency_key) < 8 or len(idempotency_key) > 128:
        raise ValidationError("Idempotency-Key must be between 8 and 128 characters")

    existing = await db.scalar(
        select(VendorPayment).where(
            VendorPayment.tenant_id == invoice.tenant_id,
            VendorPayment.idempotency_key == idempotency_key,
        )
    )
    if existing is not None:
        if not vendor_payment_matches_request(existing, invoice.id, payload):
            raise ConflictError("Idempotency-Key was already used for a different payment")
        return existing, False

    if invoice.status not in {"approved", "partially_paid"}:
        raise ValidationError("Only approved, unpaid vendor invoices can be settled")
    reference = f"VINV:{invoice.invoice_number}"
    if not await _existing_posting(db, invoice.tenant_id, reference):
        raise ValidationError("Vendor invoice must be posted to accounts payable before settlement")
    invoice_total = invoice.amount + invoice.tax_amount
    pending_total = await db.scalar(
        select(func.coalesce(func.sum(VendorPayment.amount), 0)).where(
            VendorPayment.vendor_invoice_id == invoice.id,
            VendorPayment.status == "pending_approval",
        )
    )
    outstanding = invoice_total - invoice.paid_amount - Decimal(pending_total or 0)
    if payload.amount > outstanding:
        raise ValidationError(f"Payment exceeds outstanding balance of {outstanding}")
    if payload.amount != payload.amount.quantize(Decimal("0.01")):
        raise ValidationError("Payment amount cannot have more than two decimal places")
    if payload.amount >= Decimal("1000000000000"):
        raise ValidationError("Payment amount exceeds the supported precision")

    tenant_id = invoice.tenant_id
    if payload.paid_on < invoice.issue_date:
        raise ValidationError("Payment date cannot be before the vendor invoice date")
    await ensure_period_open(db, tenant_id, payload.paid_on)
    if payload.method == "cash":
        if payload.bank_account_id is not None:
            raise ValidationError("Cash payments cannot be assigned to a bank account")
        settlement_account = await _require_account(db, tenant_id, CASH, "cash")
    else:
        if payload.bank_account_id is None:
            raise ValidationError("Select the bank account used for this payment")
        bank_account = await db.scalar(
            select(BankAccount).where(
                BankAccount.id == payload.bank_account_id,
                BankAccount.tenant_id == tenant_id,
                BankAccount.is_active.is_(True),
            )
        )
        if bank_account is None:
            raise ValidationError("Bank account must be active and belong to this tenant")
        if bank_account.ledger_account_id is None:
            raise ValidationError("Map the bank account to an active GL account before posting")
        settlement_account = await db.scalar(
            select(Account).where(
                Account.id == bank_account.ledger_account_id,
                Account.tenant_id == tenant_id,
                Account.account_type == "asset",
                Account.is_active.is_(True),
            )
        )
        if settlement_account is None:
            raise ValidationError("Bank account GL mapping must be an active asset account")

    payment = VendorPayment(
        tenant_id=tenant_id,
        created_by_id=user.id,
        vendor_invoice_id=invoice.id,
        idempotency_key=idempotency_key,
        bank_account_id=payload.bank_account_id,
        amount=payload.amount,
        method=payload.method,
        paid_on=payload.paid_on,
        reference=payload.reference,
        notes=payload.notes,
        status="pending_approval",
    )
    db.add(payment)
    await db.flush()
    return payment, True


def vendor_payment_matches_request(payment, invoice_id: UUID, payload) -> bool:
    return (
        payment.vendor_invoice_id == invoice_id
        and payment.amount == payload.amount
        and payment.method == payload.method
        and payment.paid_on == payload.paid_on
        and payment.bank_account_id == payload.bank_account_id
        and payment.reference == payload.reference
        and payment.notes == payload.notes
    )


def payment_matches_request(payment: Payment, invoice_id: UUID, payload: PaymentCreate) -> bool:
    return (
        payment.invoice_id == invoice_id
        and payment.amount == payload.amount
        and payment.method == payload.method
        and payment.paid_on == payload.paid_on
        and payment.bank_account_id == payload.bank_account_id
        and payment.reference == payload.reference
        and payment.notes == payload.notes
    )


async def trial_balance(db: AsyncSession, user: User) -> list[TrialBalanceRow]:
    debit_expr = func.coalesce(
        func.sum(case((JournalEntry.status == "posted", JournalLine.debit), else_=0)), 0
    )
    credit_expr = func.coalesce(
        func.sum(case((JournalEntry.status == "posted", JournalLine.credit), else_=0)), 0
    )
    stmt = (
        select(
            Account.id,
            Account.code,
            Account.name,
            Account.account_type,
            debit_expr.label("debit"),
            credit_expr.label("credit"),
        )
        .outerjoin(JournalLine, JournalLine.account_id == Account.id)
        .outerjoin(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(Account.is_active.is_(True))
        .group_by(Account.id, Account.code, Account.name, Account.account_type)
        .order_by(Account.code)
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Account.tenant_id == user.tenant_id)
    rows = (await db.execute(stmt)).all()
    result = []
    for row in rows:
        debit = Decimal(str(row.debit or 0))
        credit = Decimal(str(row.credit or 0))
        result.append(
            TrialBalanceRow(
                account_id=row.id,
                code=row.code,
                name=row.name,
                account_type=row.account_type,
                debit=debit,
                credit=credit,
                balance=debit - credit,
            )
        )
    return result


def _aging_buckets(rows: list[tuple[Optional[date], Decimal]], *, today: date) -> list[dict]:
    buckets = [
        ("Not yet due", 0, None),
        ("1-30 days", 1, 30),
        ("31-60 days", 31, 60),
        ("61-90 days", 61, 90),
        ("Over 90 days", 91, None),
    ]
    result = []
    for label, minimum, maximum in buckets:
        matching = []
        for due_date, amount in rows:
            if amount <= 0:
                continue
            if due_date is None:
                days_overdue = 0
            else:
                days_overdue = max(0, (today - due_date).days)
            if minimum == 0:
                include = due_date is None or due_date >= today
            elif maximum is None:
                include = days_overdue >= minimum
            else:
                include = minimum <= days_overdue <= maximum
            if include:
                matching.append(amount)
        result.append({
            "label": label,
            "total": sum(matching, Decimal("0")),
            "count": len(matching),
        })
    return result


async def aging_report(db: AsyncSession, user: User):
    ar_rows = await receivables(db, user)
    ar = [(row.due_date, row.outstanding) for row in ar_rows]

    stmt = select(
        VendorInvoice,
        func.coalesce(func.sum(VendorPayment.amount), 0).label("pending_amount"),
    ).outerjoin(
        VendorPayment,
        (VendorPayment.vendor_invoice_id == VendorInvoice.id)
        & (VendorPayment.status == "pending_approval"),
    ).where(
        VendorInvoice.is_active.is_(True),
        VendorInvoice.status.in_(("approved", "partially_paid")),
    ).group_by(VendorInvoice.id)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(VendorInvoice.tenant_id == user.tenant_id)
    vendor_rows = list((await db.execute(stmt)).all())
    ap = []
    for invoice, pending_amount in vendor_rows:
        outstanding = invoice.amount + invoice.tax_amount - invoice.paid_amount - Decimal(str(pending_amount or 0))
        if outstanding > 0:
            ap.append((invoice.due_date, outstanding))

    return {
        "receivables": _aging_buckets(ar, today=date.today()),
        "payables": _aging_buckets(ap, today=date.today()),
    }


async def accounting_exceptions(db: AsyncSession, user: User) -> dict:
    def scope(stmt, model):
        if not user.is_superuser and user.tenant_id:
            return stmt.where(model.tenant_id == user.tenant_id)
        return stmt

    draft_journals = int(await db.scalar(scope(
        select(func.count()).select_from(JournalEntry).where(JournalEntry.status == "draft"),
        JournalEntry,
    )) or 0)
    pending_approvals = int(await db.scalar(scope(
        select(func.count()).select_from(FinanceApproval).where(FinanceApproval.status == "pending"),
        FinanceApproval,
    )) or 0)
    unmatched_bank_transactions = int(await db.scalar(scope(
        select(func.count()).select_from(BankTransaction).where(
            BankTransaction.reconciled.is_(False),
            BankTransaction.is_active.is_(True),
        ),
        BankTransaction,
    )) or 0)
    open_grni_receipts = int(await db.scalar(scope(
        select(func.count()).select_from(GRNAccrual).where(GRNAccrual.cleared_by_invoice_id.is_(None)),
        GRNAccrual,
    )) or 0)

    ar_rows = await receivables(db, user)
    overdue_receivables = sum(1 for row in ar_rows if row.days_overdue > 0)

    ap_stmt = select(VendorInvoice).where(
        VendorInvoice.is_active.is_(True),
        VendorInvoice.status.in_(("approved", "partially_paid")),
        VendorInvoice.due_date.is_not(None),
        VendorInvoice.due_date < date.today(),
    )
    if not user.is_superuser and user.tenant_id:
        ap_stmt = ap_stmt.where(VendorInvoice.tenant_id == user.tenant_id)
    invoices = list((await db.scalars(ap_stmt)).all())
    overdue_payables = 0
    for invoice in invoices:
        pending = await db.scalar(select(func.coalesce(func.sum(VendorPayment.amount), 0)).where(
            VendorPayment.vendor_invoice_id == invoice.id,
            VendorPayment.status == "pending_approval",
        ))
        outstanding = invoice.amount + invoice.tax_amount - invoice.paid_amount - Decimal(str(pending or 0))
        if outstanding > 0:
            overdue_payables += 1

    return {
        "draft_journals": draft_journals,
        "pending_approvals": pending_approvals,
        "overdue_receivables": overdue_receivables,
        "overdue_payables": overdue_payables,
        "unmatched_bank_transactions": unmatched_bank_transactions,
        "open_grni_receipts": open_grni_receipts,
    }


async def receivables(db: AsyncSession, user: User) -> list[ReceivableRow]:
    stmt = select(Invoice).where(
        Invoice.is_active.is_(True),
        Invoice.status.in_(("sent", "partially_paid", "overdue")),
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Invoice.tenant_id == user.tenant_id)
    invoices = list((await db.scalars(stmt.order_by(Invoice.issue_date))).all())
    today = date.today()
    rows = []
    for invoice in invoices:
        outstanding = invoice.total - invoice.amount_paid
        if outstanding <= 0:
            continue
        days_overdue = 0
        if invoice.due_date and invoice.due_date < today:
            days_overdue = (today - invoice.due_date).days
        rows.append(
            ReceivableRow(
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
                customer_id=invoice.customer_id,
                issue_date=invoice.issue_date,
                due_date=invoice.due_date,
                total=invoice.total,
                amount_paid=invoice.amount_paid,
                outstanding=outstanding,
                days_overdue=days_overdue,
            )
        )
    return rows
