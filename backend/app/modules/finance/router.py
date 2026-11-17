import math
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_all_permissions, require_permissions
from app.core.exceptions import NotFoundError, ValidationError
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.finance.models import (
    Account,
    BankAccount,
    BankTransaction,
    Invoice,
    JournalEntry,
    JournalLine,
    Payment,
)
from app.modules.finance.schemas import (
    AccountCreate,
    AccountRead,
    AccountUpdate,
    BankAccountCreate,
    BankAccountRead,
    BankAccountUpdate,
    BankTransactionCreate,
    BankTransactionRead,
    BankTransactionUpdate,
    FinancialReport,
    InvoiceCreate,
    InvoiceRead,
    InvoiceUpdate,
    JournalEntryCreate,
    JournalEntryRead,
    PaymentCreate,
    PaymentRead,
    PaymentUpdate,
    ReceivableRow,
    ReportSection,
    TallyImportResult,
    TrialBalanceRow,
)
from app.modules.finance.service import (
    create_journal_entry,
    create_payment,
    get_journal_entry,
    post_invoice_journal,
    post_journal_entry,
    receivables,
    trial_balance,
)
from app.modules.finance.tally import import_tally
from app.modules.identity.models import User

router = APIRouter(prefix="/finance")


def _include(**kwargs):
    child, _ = build_crud_router(module="finance", **kwargs)
    router.include_router(child)


_include(
    model=Account,
    read_schema=AccountRead,
    create_schema=AccountCreate,
    update_schema=AccountUpdate,
    prefix="/accounts",
    tags=["Finance · Chart of Accounts"],
    permission_prefix="finance.account",
    entity="Account",
    search_fields=("code", "name"),
    filter_fields=("account_type",),
)

_include(
    model=Invoice,
    read_schema=InvoiceRead,
    create_schema=InvoiceCreate,
    update_schema=InvoiceUpdate,
    prefix="/invoices",
    tags=["Finance · Invoices"],
    permission_prefix="finance.invoice",
    entity="Invoice",
    search_fields=("invoice_number", "notes"),
    filter_fields=("status", "customer_id"),
    number_field="invoice_number",
    number_prefix="INV",
)

_include(
    model=Payment,
    read_schema=PaymentRead,
    create_schema=PaymentCreate,
    update_schema=PaymentUpdate,
    prefix="/payments",
    tags=["Finance · Payments"],
    permission_prefix="finance.payment",
    entity="Payment",
    search_fields=("reference",),
    filter_fields=("invoice_id", "method"),
    soft_delete=False,
)

_include(
    model=BankAccount,
    read_schema=BankAccountRead,
    create_schema=BankAccountCreate,
    update_schema=BankAccountUpdate,
    prefix="/bank-accounts",
    tags=["Finance · Banking"],
    permission_prefix="finance.bankaccount",
    entity="BankAccount",
    search_fields=("name", "bank_name", "account_number"),
)

_include(
    model=BankTransaction,
    read_schema=BankTransactionRead,
    create_schema=BankTransactionCreate,
    update_schema=BankTransactionUpdate,
    prefix="/bank-transactions",
    tags=["Finance · Banking"],
    permission_prefix="finance.banktransaction",
    entity="BankTransaction",
    search_fields=("description", "reference"),
    filter_fields=("bank_account_id", "reconciled"),
    soft_delete=False,
)

read_journals = require_permissions("finance.journalentry.read")
create_journals = require_permissions("finance.journalentry.create")
post_permission = require_permissions("finance.journal.post")
read_reports = require_permissions("finance.report.read")


@router.get(
    "/journal-entries",
    response_model=Page[JournalEntryRead],
    tags=["Finance · Journal"],
)
async def list_journal_entries(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    user: User = Depends(read_journals),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(JournalEntry).options(
        selectinload(JournalEntry.lines).selectinload(JournalLine.account)
    )
    count_stmt = select(func.count()).select_from(JournalEntry)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(JournalEntry.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(JournalEntry.tenant_id == user.tenant_id)
    if status:
        stmt = stmt.where(JournalEntry.status == status)
        count_stmt = count_stmt.where(JournalEntry.status == status)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(JournalEntry.entry_date.desc()).offset((page - 1) * size).limit(size)
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


@router.post(
    "/journal-entries",
    response_model=JournalEntryRead,
    status_code=201,
    tags=["Finance · Journal"],
)
async def new_journal_entry(
    payload: JournalEntryCreate,
    request: Request,
    user: User = Depends(create_journals),
    db: AsyncSession = Depends(get_db),
):
    entry = await create_journal_entry(db, user, payload)
    await record_audit(
        db,
        user=user,
        action="create",
        module="finance",
        entity="JournalEntry",
        entity_id=entry.id,
        changes={"entry_number": entry.entry_number},
        request=request,
    )
    await db.commit()
    return await get_journal_entry(db, user, entry.id)


@router.post(
    "/journal-entries/{entry_id}/post",
    response_model=JournalEntryRead,
    tags=["Finance · Journal"],
)
async def post_entry(
    entry_id: UUID,
    request: Request,
    user: User = Depends(post_permission),
    db: AsyncSession = Depends(get_db),
):
    entry = await get_journal_entry(db, user, entry_id)
    await post_journal_entry(db, user, entry)
    await record_audit(
        db,
        user=user,
        action="post",
        module="finance",
        entity="JournalEntry",
        entity_id=entry.id,
        changes={"status": "posted"},
        request=request,
    )
    await db.commit()
    return await get_journal_entry(db, user, entry.id)


@router.post("/invoices/{invoice_id}/post", response_model=InvoiceRead, tags=["Finance · Invoices"])
async def post_invoice(
    invoice_id: UUID,
    request: Request,
    user: User = Depends(post_permission),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    invoice = await db.scalar(stmt)
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if not user.is_superuser and invoice.tenant_id != user.tenant_id:
        raise NotFoundError("Invoice not found")
    await post_invoice_journal(db, user, invoice)
    if invoice.status == "draft":
        invoice.status = "sent"
    await record_audit(
        db,
        user=user,
        action="post",
        module="finance",
        entity="Invoice",
        entity_id=invoice.id,
        request=request,
    )
    await db.commit()
    await db.refresh(invoice)
    return invoice


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=PaymentRead,
    status_code=201,
    tags=["Finance · Payments"],
)
async def record_invoice_payment(
    invoice_id: UUID,
    payload: PaymentCreate,
    request: Request,
    user: User = Depends(require_permissions("finance.payment.create")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    invoice = await db.scalar(stmt)
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if not user.is_superuser and invoice.tenant_id != user.tenant_id:
        raise NotFoundError("Invoice not found")
    payload.invoice_id = invoice.id
    payment = await create_payment(db, user, invoice, payload)
    await record_audit(
        db,
        user=user,
        action="create",
        module="finance",
        entity="Payment",
        entity_id=payment.id,
        changes={"invoice": invoice.invoice_number, "amount": float(payload.amount)},
        request=request,
    )
    await db.commit()
    await db.refresh(payment)
    return payment


@router.get(
    "/reports/trial-balance",
    response_model=list[TrialBalanceRow],
    tags=["Finance · Reports"],
)
async def report_trial_balance(
    user: User = Depends(read_reports), db: AsyncSession = Depends(get_db)
):
    return await trial_balance(db, user)


@router.get("/reports/profit-loss", response_model=FinancialReport, tags=["Finance · Reports"])
async def report_profit_loss(
    user: User = Depends(read_reports), db: AsyncSession = Depends(get_db)
):
    rows = await trial_balance(db, user)
    income = sum((row.credit - row.debit for row in rows if row.account_type == "income"), Decimal("0"))
    expense = sum((row.debit - row.credit for row in rows if row.account_type == "expense"), Decimal("0"))
    return FinancialReport(
        total=income - expense,
        sections=[
            ReportSection(label="Income", amount=income),
            ReportSection(label="Expenses", amount=expense),
            ReportSection(label="Net profit", amount=income - expense),
        ],
    )


@router.get("/reports/balance-sheet", response_model=FinancialReport, tags=["Finance · Reports"])
async def report_balance_sheet(
    user: User = Depends(read_reports), db: AsyncSession = Depends(get_db)
):
    rows = await trial_balance(db, user)
    assets = sum((row.debit - row.credit for row in rows if row.account_type == "asset"), Decimal("0"))
    liabilities = sum(
        (row.credit - row.debit for row in rows if row.account_type == "liability"), Decimal("0")
    )
    equity = sum((row.credit - row.debit for row in rows if row.account_type == "equity"), Decimal("0"))
    return FinancialReport(
        total=assets,
        sections=[
            ReportSection(label="Assets", amount=assets),
            ReportSection(label="Liabilities", amount=liabilities),
            ReportSection(label="Equity", amount=equity),
        ],
    )


@router.get("/reports/receivables", response_model=list[ReceivableRow], tags=["Finance · Reports"])
async def report_receivables(
    user: User = Depends(read_reports), db: AsyncSession = Depends(get_db)
):
    return await receivables(db, user)


@router.get("/reports/cash-flow", response_model=FinancialReport, tags=["Finance · Reports"])
async def report_cash_flow(
    user: User = Depends(read_reports), db: AsyncSession = Depends(get_db)
):
    stmt = select(Payment.method, func.coalesce(func.sum(Payment.amount), 0)).group_by(Payment.method)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Payment.tenant_id == user.tenant_id)
    rows = (await db.execute(stmt)).all()
    sections = [
        ReportSection(label=f"Inflow · {row[0]}", amount=Decimal(str(row[1] or 0))) for row in rows
    ]
    total = sum((section.amount for section in sections), Decimal("0"))
    return FinancialReport(total=total, sections=sections)


@router.post("/tally/import", response_model=TallyImportResult, tags=["Finance · Tally Import"])
async def import_tally_file(
    request: Request,
    file: UploadFile = File(...),
    opening_date: Optional[date] = Form(None),
    post_opening_balance: bool = Form(True),
    user: User = Depends(
        require_all_permissions("finance.account.create", "finance.journal.post")
    ),
    db: AsyncSession = Depends(get_db),
):
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise ValidationError("Tally file is larger than the 10 MB limit")
    result = await import_tally(
        db,
        user,
        content,
        opening_date=opening_date or date.today(),
        post_opening_balance=post_opening_balance,
    )
    await record_audit(
        db,
        user=user,
        action="import",
        module="finance",
        entity="Account",
        changes=result.model_dump(mode="json"),
        request=request,
    )
    await db.commit()
    return result
