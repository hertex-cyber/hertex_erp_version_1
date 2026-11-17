from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ValidationError
from app.core.numbering import next_number
from app.modules.finance.models import (
    Account,
    Invoice,
    JournalEntry,
    JournalLine,
    Payment,
)
from app.modules.finance.schemas import (
    JournalEntryCreate,
    PaymentCreate,
    ReceivableRow,
    TrialBalanceRow,
)
from app.modules.identity.models import User

# Canonical chart-of-accounts codes shared with the seed data.
CASH = "1010"
ACCOUNTS_RECEIVABLE = "1100"
INVENTORY = "1200"
ACCOUNTS_PAYABLE = "2000"
SALES_REVENUE = "4000"


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
        if (line.debit or 0) > 0 and (line.credit or 0) > 0:
            raise ValidationError("A journal line cannot have both debit and credit")
        if (line.debit or 0) < 0 or (line.credit or 0) < 0:
            raise ValidationError("Debit and credit values cannot be negative")
    return total_debit, total_credit


async def create_journal_entry(
    db: AsyncSession, user: User, payload: JournalEntryCreate
) -> JournalEntry:
    _validate_lines(payload.lines)
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
    total_debit = sum((line.debit or Decimal("0") for line in entry.lines), Decimal("0"))
    total_credit = sum((line.credit or Decimal("0") for line in entry.lines), Decimal("0"))
    if total_debit != total_credit or total_debit <= 0:
        raise ValidationError("Cannot post an unbalanced or empty journal entry")
    entry.status = "posted"
    entry.posted_by_id = user.id
    entry.posted_at = datetime.now(timezone.utc)
    await db.flush()
    return entry


async def _existing_posting(db: AsyncSession, tenant_id, reference: str) -> bool:
    stmt = select(JournalEntry.id).where(
        JournalEntry.reference == reference, JournalEntry.status == "posted"
    )
    if tenant_id:
        stmt = stmt.where(JournalEntry.tenant_id == tenant_id)
    return (await db.scalar(stmt)) is not None


async def post_invoice_journal(db: AsyncSession, user: User, invoice: Invoice) -> Optional[JournalEntry]:
    """Post AR debit / revenue credit for a customer invoice (idempotent)."""
    if invoice.total <= 0:
        return None
    reference = f"INV:{invoice.invoice_number}"
    if await _existing_posting(db, user.tenant_id, reference):
        return None
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
    db.add_all(
        [
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
                credit=invoice.total,
            ),
        ]
    )
    await db.flush()
    return entry


async def post_vendor_invoice_journal(
    db: AsyncSession, user: User, invoice
) -> Optional[JournalEntry]:
    """Post inventory debit / accounts-payable credit for an approved vendor invoice."""
    total = (invoice.amount or Decimal("0")) + (invoice.tax_amount or Decimal("0"))
    if total <= 0:
        return None
    reference = f"VINV:{invoice.invoice_number}"
    if await _existing_posting(db, user.tenant_id, reference):
        return None
    inventory = await _require_account(db, user.tenant_id, INVENTORY, "inventory")
    payable = await _require_account(db, user.tenant_id, ACCOUNTS_PAYABLE, "accounts payable")

    number = await next_number(db, JournalEntry, "entry_number", "JE", user.tenant_id)
    entry = JournalEntry(
        tenant_id=user.tenant_id,
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
    db.add_all(
        [
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=entry.id,
                account_id=inventory.id,
                description="Inventory received",
                debit=total,
                credit=Decimal("0"),
            ),
            JournalLine(
                tenant_id=user.tenant_id,
                journal_entry_id=entry.id,
                account_id=payable.id,
                description="Accounts payable",
                debit=Decimal("0"),
                credit=total,
            ),
        ]
    )
    await db.flush()
    return entry


async def create_payment(
    db: AsyncSession, user: User, invoice: Invoice, payload: PaymentCreate
) -> Payment:
    outstanding = invoice.total - invoice.amount_paid
    if payload.amount > outstanding:
        raise ValidationError(f"Payment exceeds outstanding balance of {outstanding}")
    payment = Payment(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        invoice_id=invoice.id,
        amount=payload.amount,
        method=payload.method,
        paid_on=payload.paid_on,
        reference=payload.reference,
        notes=payload.notes,
    )
    db.add(payment)
    invoice.amount_paid = invoice.amount_paid + payload.amount
    invoice.status = "paid" if invoice.amount_paid >= invoice.total else "partially_paid"

    cash = await _require_account(db, user.tenant_id, CASH, "cash")
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
                account_id=cash.id,
                description="Cash / bank received",
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
    return payment


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
