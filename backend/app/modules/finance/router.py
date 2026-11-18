import csv
import hashlib
import io
import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Header, Query, Request, UploadFile
from sqlalchemy import case, delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_all_permissions, require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.schemas import Page
from app.db.session import get_db
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
    AccountCreate,
    AccountingExceptionSummary,
    AccountRead,
    AccountUpdate,
    AgingReport,
    BankAccountCreate,
    BankAccountRead,
    BankAccountUpdate,
    BankMatchCandidate,
    BankReconciliationSummary,
    BankReconciliationUndo,
    BankTransactionMatch,
    BankTransactionRead,
    FinanceApprovalDecision,
    FinanceApprovalRead,
    FinancialPeriodCreate,
    FinancialPeriodRead,
    FinancialReport,
    GRNISummary,
    InvoiceCreate,
    InvoiceRead,
    InvoiceTaxLineRead,
    InvoiceTaxLinesUpdate,
    InvoiceUpdate,
    JournalEntryCreate,
    JournalEntryRead,
    JournalReversalCreate,
    PaymentCreate,
    PaymentRead,
    PeriodCloseChecklist,
    PeriodCloseChecklistItem,
    PeriodCloseSignoffCreate,
    ReceivableRow,
    ReportSection,
    TallyImportResult,
    TaxCodeCreate,
    TaxCodeRead,
    TaxCodeUpdate,
    TaxRegistrationCreate,
    TaxRegistrationRead,
    TaxRegistrationUpdate,
    TrialBalanceRow,
    VendorPayableRead,
    VendorPayablesSummary,
    VendorPaymentCreate,
    VendorPaymentRead,
)
from app.modules.finance.service import (
    GST_STATE_CODES,
    accounting_exceptions,
    aging_report,
    calculate_tax_snapshot,
    create_financial_period,
    create_journal_entry,
    create_payment,
    create_vendor_payment,
    get_journal_entry,
    payment_matches_request,
    post_inventory_adjustment_journal,
    post_invoice_journal,
    post_journal_entry,
    post_vendor_payment_journal,
    receivables,
    reverse_journal_entry,
    set_financial_period_status,
    submit_finance_approval,
    tax_line_totals,
    trial_balance,
    vendor_payment_matches_request,
)
from app.modules.finance.tally import import_tally
from app.modules.identity.models import User
from app.modules.inventory.models import StockMove
from app.modules.procurement.models import GoodsReceipt, Vendor, VendorInvoice, VendorInvoiceTaxLine
from app.modules.sales.models import SalesOrder

router = APIRouter(prefix="/finance")


def _include(**kwargs):
    child, _ = build_crud_router(module="finance", **kwargs)
    router.include_router(child)


account_read = require_permissions("finance.account.read")
account_create = require_permissions("finance.account.create")
account_update = require_permissions("finance.account.update")
account_delete = require_permissions("finance.account.delete")
tax_registration_read = require_permissions("finance.taxregistration.read")
tax_registration_create = require_permissions("finance.taxregistration.create")
tax_registration_update = require_permissions("finance.taxregistration.update")
tax_code_read = require_permissions("finance.taxcode.read")
tax_code_create = require_permissions("finance.taxcode.create")
tax_code_update = require_permissions("finance.taxcode.update")


def _tenant_scope(stmt, model, user: User):
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(model.tenant_id == user.tenant_id)
    return stmt


async def _tax_account(
    db: AsyncSession, tenant_id: UUID, account_id: Optional[UUID], account_type: str
) -> Optional[Account]:
    if account_id is None:
        return None
    account = await db.scalar(
        select(Account).where(
            Account.id == account_id,
            Account.tenant_id == tenant_id,
            Account.is_active.is_(True),
            Account.account_type == account_type,
        )
    )
    if account is None:
        raise ValidationError(
            f"Tax account must be an active same-tenant {account_type} account"
        )
    return account


async def _validate_tax_code(
    db: AsyncSession, tenant_id: UUID, data: dict, existing: Optional[TaxCode] = None
) -> None:
    def value(field):
        return data.get(field, getattr(existing, field, None))

    rates = {
        "cgst": value("cgst_rate") or 0,
        "sgst": value("sgst_rate") or 0,
        "igst": value("igst_rate") or 0,
    }
    if rates["cgst"] + rates["sgst"] != rates["igst"]:
        raise ValidationError("IGST rate must equal the combined CGST and SGST rates")
    tax_type = value("tax_type") or "taxable"
    if tax_type != "taxable" and any(rates.values()):
        raise ValidationError("Exempt, zero-rated, and non-GST codes must have zero rates")

    mappings = {
        "cgst": (
            "output_cgst_account_id",
            "input_cgst_account_id",
        ),
        "sgst": (
            "output_sgst_account_id",
            "input_sgst_account_id",
        ),
        "igst": (
            "output_igst_account_id",
            "input_igst_account_id",
        ),
    }
    for component, (output_field, input_field) in mappings.items():
        if rates[component]:
            if value(output_field) is None:
                raise ValidationError(f"Map an output liability account for {component.upper()}")
            await _tax_account(db, tenant_id, value(output_field), "liability")
            if value("can_claim_itc") and value(input_field) is None:
                raise ValidationError(f"Map a recoverable input asset account for {component.upper()}")
        if value(input_field) is not None:
            await _tax_account(db, tenant_id, value(input_field), "asset")


@router.get("/tax/registrations", response_model=Page[TaxRegistrationRead], tags=["Finance · GST"])
async def list_tax_registrations(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(tax_registration_read),
    db: AsyncSession = Depends(get_db),
):
    stmt = _tenant_scope(
        select(TaxRegistration).where(TaxRegistration.is_active.is_(True)), TaxRegistration, user
    )
    count_stmt = _tenant_scope(
        select(func.count()).select_from(TaxRegistration).where(TaxRegistration.is_active.is_(True)),
        TaxRegistration,
        user,
    )
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(TaxRegistration.is_default.desc(), TaxRegistration.legal_name)
                .offset((page - 1) * size)
                .limit(size)
            )
        ).all()
    )
    return {"items": items, "total": total, "page": page, "size": size, "pages": max(1, math.ceil(total / size))}


@router.post(
    "/tax/registrations",
    response_model=TaxRegistrationRead,
    status_code=201,
    tags=["Finance · GST"],
)
async def create_tax_registration(
    payload: TaxRegistrationCreate,
    request: Request,
    user: User = Depends(tax_registration_create),
    db: AsyncSession = Depends(get_db),
):
    if payload.gstin[:2] != payload.state_code:
        raise ValidationError("GSTIN state prefix must match the registration state code")
    if payload.state_code not in GST_STATE_CODES:
        raise ValidationError("GST registration state code is not a valid Indian GST state")
    if user.tenant_id is None:
        raise ValidationError("A tenant is required to create a GST registration")
    has_registration = await db.scalar(
        select(TaxRegistration.id)
        .where(
            TaxRegistration.tenant_id == user.tenant_id,
            TaxRegistration.is_active.is_(True),
        )
        .limit(1)
    )
    registration = TaxRegistration(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        **payload.model_dump(),
    )
    registration.is_default = payload.is_default or has_registration is None
    if registration.is_default:
        await db.execute(
            update(TaxRegistration)
            .where(TaxRegistration.tenant_id == user.tenant_id)
            .values(is_default=False)
        )
    db.add(registration)
    await db.flush()
    await record_audit(
        db, user=user, action="create", module="finance", entity="TaxRegistration",
        entity_id=registration.id, changes=payload.model_dump(), request=request,
    )
    try:
        await db.commit()
        await db.refresh(registration)
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("GSTIN already exists for this tenant") from exc
    return registration


@router.patch(
    "/tax/registrations/{registration_id}",
    response_model=TaxRegistrationRead,
    tags=["Finance · GST"],
)
async def update_tax_registration(
    registration_id: UUID,
    payload: TaxRegistrationUpdate,
    request: Request,
    user: User = Depends(tax_registration_update),
    db: AsyncSession = Depends(get_db),
):
    registration = await db.scalar(
        _tenant_scope(select(TaxRegistration), TaxRegistration, user).where(
            TaxRegistration.id == registration_id
        )
    )
    if registration is None:
        raise NotFoundError("GST registration not found")
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("is_active") is False and changes.get("is_default") is True:
        raise ValidationError("An inactive GST registration cannot be the default")
    if changes.get("is_active") is False:
        if registration.is_default:
            changes["is_default"] = False
        referenced_sales = await db.scalar(
            select(InvoiceTaxLine.id).where(InvoiceTaxLine.registration_id == registration.id).limit(1)
        )
        referenced_orders = await db.scalar(
            select(SalesOrder.id)
            .where(SalesOrder.tax_registration_id == registration.id)
            .limit(1)
        )
        referenced_vendor = await db.scalar(
            select(VendorInvoiceTaxLine.id)
            .where(VendorInvoiceTaxLine.registration_id == registration.id)
            .limit(1)
        )
        if referenced_sales or referenced_orders or referenced_vendor:
            raise ConflictError("A GST registration used by invoice lines cannot be deactivated")
    if changes.get("is_default"):
        await db.execute(
            update(TaxRegistration)
            .where(
                TaxRegistration.tenant_id == registration.tenant_id,
                TaxRegistration.id != registration.id,
            )
            .values(is_default=False)
        )
    for field, value in changes.items():
        setattr(registration, field, value)
    await record_audit(
        db, user=user, action="update", module="finance", entity="TaxRegistration",
        entity_id=registration.id, changes=changes, request=request,
    )
    await db.commit()
    await db.refresh(registration)
    return registration


@router.get("/tax/codes", response_model=Page[TaxCodeRead], tags=["Finance · GST"])
async def list_tax_codes(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(tax_code_read),
    db: AsyncSession = Depends(get_db),
):
    stmt = _tenant_scope(select(TaxCode).where(TaxCode.is_active.is_(True)), TaxCode, user)
    count_stmt = _tenant_scope(
        select(func.count()).select_from(TaxCode).where(TaxCode.is_active.is_(True)), TaxCode, user
    )
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(TaxCode.code).offset((page - 1) * size).limit(size)
            )
        ).all()
    )
    return {"items": items, "total": total, "page": page, "size": size, "pages": max(1, math.ceil(total / size))}


@router.post("/tax/codes", response_model=TaxCodeRead, status_code=201, tags=["Finance · GST"])
async def create_tax_code(
    payload: TaxCodeCreate,
    request: Request,
    user: User = Depends(tax_code_create),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump()
    if user.tenant_id is None:
        raise ValidationError("A tenant is required to create a GST tax code")
    await _validate_tax_code(db, user.tenant_id, data)
    tax_code = TaxCode(tenant_id=user.tenant_id, created_by_id=user.id, **data)
    db.add(tax_code)
    await db.flush()
    await record_audit(
        db, user=user, action="create", module="finance", entity="TaxCode",
        entity_id=tax_code.id, changes=data, request=request,
    )
    try:
        await db.commit()
        await db.refresh(tax_code)
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Tax code already exists for this tenant") from exc
    return tax_code


@router.patch("/tax/codes/{tax_code_id}", response_model=TaxCodeRead, tags=["Finance · GST"])
async def update_tax_code(
    tax_code_id: UUID,
    payload: TaxCodeUpdate,
    request: Request,
    user: User = Depends(tax_code_update),
    db: AsyncSession = Depends(get_db),
):
    tax_code = await db.scalar(
        _tenant_scope(select(TaxCode), TaxCode, user).where(TaxCode.id == tax_code_id)
    )
    if tax_code is None:
        raise NotFoundError("Tax code not found")
    changes = payload.model_dump(exclude_unset=True)
    await _validate_tax_code(db, tax_code.tenant_id, changes, tax_code)
    for field, value in changes.items():
        setattr(tax_code, field, value)
    await record_audit(
        db, user=user, action="update", module="finance", entity="TaxCode",
        entity_id=tax_code.id, changes=changes, request=request,
    )
    await db.commit()
    await db.refresh(tax_code)
    return tax_code


def _account_scope(stmt, user: User):
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Account.tenant_id == user.tenant_id)
    return stmt


async def _get_account(db: AsyncSession, user: User, account_id: UUID) -> Account:
    account = await db.scalar(_account_scope(select(Account), user).where(Account.id == account_id))
    if account is None:
        raise NotFoundError("Account not found")
    return account


async def _validate_account_definition(
    db: AsyncSession,
    user: User,
    data: dict,
    *,
    account: Optional[Account] = None,
) -> None:
    tenant_id = account.tenant_id if account is not None else user.tenant_id
    code = data.get("code", account.code if account else None)
    account_type = data.get("account_type", account.account_type if account else None)
    parent_id = data.get("parent_id", account.parent_id if account else None)

    if code is not None:
        duplicate_stmt = select(Account.id).where(
            Account.tenant_id == tenant_id,
            func.lower(Account.code) == code.lower(),
        )
        if account is not None:
            duplicate_stmt = duplicate_stmt.where(Account.id != account.id)
        if await db.scalar(duplicate_stmt.limit(1)):
            raise ConflictError(f"Account code '{code}' already exists in this tenant")

    if account is not None and account_type != account.account_type:
        posted_usage = await db.scalar(
            select(JournalLine.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalLine.account_id == account.id,
                JournalEntry.status == "posted",
            )
            .limit(1)
        )
        child_usage = await db.scalar(
            select(Account.id).where(Account.parent_id == account.id).limit(1)
        )
        if posted_usage:
            raise ConflictError("Account type cannot change after the account has posted history")
        if child_usage:
            raise ConflictError("Account type cannot change while it has child accounts")

    if account is not None and data.get("is_active") is False:
        posted_usage = await db.scalar(
            select(JournalLine.id)
            .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
            .where(
                JournalLine.account_id == account.id,
                JournalEntry.status == "posted",
            )
            .limit(1)
        )
        if posted_usage:
            raise ConflictError("Accounts with posted ledger history cannot be deactivated")
        active_children = await db.scalar(
            select(Account.id).where(
                Account.parent_id == account.id,
                Account.is_active.is_(True),
            ).limit(1)
        )
        if active_children:
            raise ConflictError("An account with active child accounts cannot be deactivated")

    if parent_id is None:
        return
    if account is not None and parent_id == account.id:
        raise ValidationError("An account cannot be its own parent")
    parent = await db.scalar(
        select(Account).where(
            Account.id == parent_id,
            Account.tenant_id == tenant_id,
            Account.is_active.is_(True),
        )
    )
    if parent is None:
        raise ValidationError("Parent account must be active and belong to this tenant")
    if parent.account_type != account_type:
        raise ValidationError("Parent and child accounts must have the same account type")

    ancestor_id = parent.parent_id
    visited = {parent.id}
    while ancestor_id is not None:
        if account is not None and ancestor_id == account.id:
            raise ValidationError("Account hierarchy cannot contain a cycle")
        if ancestor_id in visited:
            raise ConflictError("Existing chart of accounts contains a parent cycle")
        visited.add(ancestor_id)
        ancestor = await db.scalar(
            select(Account.id, Account.parent_id).where(
                Account.id == ancestor_id,
                Account.tenant_id == tenant_id,
            )
        )
        if ancestor is None:
            raise ValidationError("Parent account hierarchy is invalid")
        ancestor_id = ancestor.parent_id


@router.get(
    "/accounts",
    response_model=Page[AccountRead],
    tags=["Finance · Chart of Accounts"],
)
async def list_accounts(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    include_inactive: bool = False,
    account_type: Optional[str] = None,
    user: User = Depends(account_read),
    db: AsyncSession = Depends(get_db),
):
    stmt = _account_scope(select(Account), user)
    count_stmt = _account_scope(select(func.count()).select_from(Account), user)
    if not include_inactive:
        stmt = stmt.where(Account.is_active.is_(True))
        count_stmt = count_stmt.where(Account.is_active.is_(True))
    if q:
        search_filter = or_(Account.code.ilike(f"%{q}%"), Account.name.ilike(f"%{q}%"))
        stmt = stmt.where(search_filter)
        count_stmt = count_stmt.where(search_filter)
    if account_type:
        stmt = stmt.where(Account.account_type == account_type)
        count_stmt = count_stmt.where(Account.account_type == account_type)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(Account.code).offset((page - 1) * size).limit(size)
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
    "/accounts",
    response_model=AccountRead,
    status_code=201,
    tags=["Finance · Chart of Accounts"],
)
async def create_account(
    payload: AccountCreate,
    request: Request,
    user: User = Depends(account_create),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump()
    await _validate_account_definition(db, user, data)
    account = Account(tenant_id=user.tenant_id, created_by_id=user.id, **data)
    db.add(account)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Account conflicts with an existing account code") from exc
    await record_audit(
        db,
        user=user,
        action="create",
        module="finance",
        entity="Account",
        entity_id=account.id,
        changes=data,
        request=request,
    )
    await db.commit()
    await db.refresh(account)
    return account


@router.get(
    "/accounts/{account_id}",
    response_model=AccountRead,
    tags=["Finance · Chart of Accounts"],
)
async def get_account(
    account_id: UUID,
    user: User = Depends(account_read),
    db: AsyncSession = Depends(get_db),
):
    return await _get_account(db, user, account_id)


@router.patch(
    "/accounts/{account_id}",
    response_model=AccountRead,
    tags=["Finance · Chart of Accounts"],
)
async def update_account(
    account_id: UUID,
    payload: AccountUpdate,
    request: Request,
    user: User = Depends(account_update),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_account(db, user, account_id)
    data = payload.model_dump(exclude_unset=True)
    await _validate_account_definition(db, user, data, account=account)
    for field, value in data.items():
        setattr(account, field, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictError("Account conflicts with an existing account code") from exc
    await record_audit(
        db,
        user=user,
        action="update",
        module="finance",
        entity="Account",
        entity_id=account.id,
        changes=data,
        request=request,
    )
    await db.commit()
    await db.refresh(account)
    return account


@router.delete(
    "/accounts/{account_id}",
    tags=["Finance · Chart of Accounts"],
)
async def archive_account(
    account_id: UUID,
    request: Request,
    user: User = Depends(account_delete),
    db: AsyncSession = Depends(get_db),
):
    account = await _get_account(db, user, account_id)
    await _validate_account_definition(db, user, {"is_active": False}, account=account)
    account.is_active = False
    await record_audit(
        db,
        user=user,
        action="delete",
        module="finance",
        entity="Account",
        entity_id=account.id,
        request=request,
    )
    await db.commit()
    return {"message": "Account deleted"}

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

read_journals = require_permissions("finance.journalentry.read")
create_journals = require_permissions("finance.journalentry.create")
read_payments = require_permissions("finance.payment.read")
create_payments = require_permissions("finance.payment.create")
post_permission = require_permissions("finance.journal.post")


@router.get(
    "/approvals",
    response_model=Page[FinanceApprovalRead],
    tags=["Finance · Approvals"],
)
async def list_finance_approvals(
    status: Optional[str] = Query(default="pending", pattern="^(pending|approved|rejected)$"),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permissions("finance.approval.read")),
    db: AsyncSession = Depends(get_db),
):
    if user.tenant_id is None:
        raise ValidationError("A tenant is required to view accounting approvals")
    stmt = select(FinanceApproval).where(FinanceApproval.tenant_id == user.tenant_id)
    if status is not None:
        stmt = stmt.where(FinanceApproval.status == status)
    total = int(
        await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    )
    items = list(
        (
            await db.scalars(
                stmt.order_by(FinanceApproval.created_at.desc())
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


async def _decide_finance_approval(
    approval_id: UUID,
    payload: FinanceApprovalDecision,
    request: Request,
    user: User,
    db: AsyncSession,
    *,
    approve: bool,
):
    if user.tenant_id is None:
        raise ValidationError("A tenant is required to decide accounting approvals")
    approval = await db.scalar(
        select(FinanceApproval)
        .where(
            FinanceApproval.id == approval_id,
            FinanceApproval.tenant_id == user.tenant_id,
        )
        .with_for_update()
    )
    if approval is None:
        raise NotFoundError("Accounting approval not found")
    if approval.status != "pending":
        raise ConflictError("Accounting approval has already been decided")
    if approval.requested_by_id == user.id:
        raise ValidationError("The requester cannot approve or reject their own request")

    if approve:
        if approval.entity_type == "journal_entry":
            entry = await db.scalar(
                select(JournalEntry)
                .where(
                    JournalEntry.id == approval.entity_id,
                    JournalEntry.tenant_id == user.tenant_id,
                )
                .with_for_update()
            )
            if entry is None:
                raise NotFoundError("Journal entry for this approval no longer exists")
            if entry.status != "draft":
                raise ConflictError("Only a draft journal entry can be approved")
            await post_journal_entry(db, user, entry)
        elif approval.entity_type == "vendor_payment":
            payment = await db.scalar(
                select(VendorPayment)
                .where(
                    VendorPayment.id == approval.entity_id,
                    VendorPayment.tenant_id == user.tenant_id,
                )
                .with_for_update()
            )
            if payment is None:
                raise NotFoundError("Vendor payment for this approval no longer exists")
            await post_vendor_payment_journal(db, user, payment)
        elif approval.entity_type == "inventory_adjustment":
            move = await db.scalar(
                select(StockMove)
                .where(
                    StockMove.id == approval.entity_id,
                    StockMove.tenant_id == user.tenant_id,
                )
                .with_for_update()
            )
            if move is None:
                raise NotFoundError("Inventory adjustment for this approval no longer exists")
            if move.status != "pending_approval" or move.movement_date is None:
                raise ConflictError("Inventory adjustment is no longer pending approval")
            await post_inventory_adjustment_journal(
                db, user, move, entry_date=move.movement_date
            )
        else:
            raise ValidationError("Unsupported accounting approval type")
        approval.status = "approved"
    else:
        if approval.entity_type == "vendor_payment":
            payment = await db.scalar(
                select(VendorPayment)
                .where(
                    VendorPayment.id == approval.entity_id,
                    VendorPayment.tenant_id == user.tenant_id,
                )
                .with_for_update()
            )
            if payment is None:
                raise NotFoundError("Vendor payment for this approval no longer exists")
            if payment.status != "pending_approval":
                raise ConflictError("Vendor payment is no longer pending approval")
            payment.status = "rejected"
        elif approval.entity_type == "inventory_adjustment":
            move = await db.scalar(
                select(StockMove)
                .where(
                    StockMove.id == approval.entity_id,
                    StockMove.tenant_id == user.tenant_id,
                )
                .with_for_update()
            )
            if move is None:
                raise NotFoundError("Inventory adjustment for this approval no longer exists")
            if move.status != "pending_approval":
                raise ConflictError("Inventory adjustment is no longer pending approval")
            move.status = "rejected"
        elif approval.entity_type != "journal_entry":
            raise ValidationError("Unsupported accounting approval type")
        approval.status = "rejected"

    approval.decided_by_id = user.id
    approval.decided_at = datetime.now(timezone.utc)
    approval.decision_reason = payload.reason
    await record_audit(
        db,
        user=user,
        action="approve" if approve else "reject",
        module="finance",
        entity="FinanceApproval",
        entity_id=approval.id,
        changes={
            "entity_type": approval.entity_type,
            "entity_id": str(approval.entity_id),
            "reason": payload.reason,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(approval)
    return approval


@router.post(
    "/approvals/{approval_id}/approve",
    response_model=FinanceApprovalRead,
    tags=["Finance · Approvals"],
)
async def approve_finance_approval(
    approval_id: UUID,
    payload: FinanceApprovalDecision,
    request: Request,
    user: User = Depends(require_permissions("finance.approval.approve")),
    db: AsyncSession = Depends(get_db),
):
    return await _decide_finance_approval(
        approval_id, payload, request, user, db, approve=True
    )


@router.post(
    "/approvals/{approval_id}/reject",
    response_model=FinanceApprovalRead,
    tags=["Finance · Approvals"],
)
async def reject_finance_approval(
    approval_id: UUID,
    payload: FinanceApprovalDecision,
    request: Request,
    user: User = Depends(require_permissions("finance.approval.reject")),
    db: AsyncSession = Depends(get_db),
):
    return await _decide_finance_approval(
        approval_id, payload, request, user, db, approve=False
    )
reverse_permission = require_permissions("finance.journal.reverse")
read_reports = require_permissions("finance.report.read")
read_periods = require_permissions("finance.fiscalperiod.read")
create_periods = require_permissions("finance.fiscalperiod.create")
close_periods = require_permissions("finance.period.close")
reopen_periods = require_permissions("finance.period.reopen")
read_bank_transactions = require_permissions("finance.banktransaction.read")
create_bank_transactions = require_permissions("finance.banktransaction.create")
update_bank_transactions = require_permissions("finance.banktransaction.update")


async def _get_bank_account(
    db: AsyncSession, user: User, bank_account_id: UUID
) -> BankAccount:
    stmt = select(BankAccount).where(BankAccount.id == bank_account_id)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(BankAccount.tenant_id == user.tenant_id)
    bank_account = await db.scalar(stmt)
    if bank_account is None:
        raise NotFoundError("Bank account not found")
    return bank_account


def _transaction_hash(
    bank_account_id: UUID,
    txn_date: date,
    amount: Decimal,
    description: Optional[str],
    reference: Optional[str],
) -> str:
    canonical = "|".join(
        (
            str(bank_account_id),
            txn_date.isoformat(),
            format(amount, ".2f"),
            (reference or "").strip().casefold(),
            (description or "").strip().casefold(),
        )
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _parse_statement_date(value: str) -> date:
    value = value.strip()
    for pattern in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    raise ValidationError(f"Unsupported bank statement date '{value}'")


@router.get(
    "/bank-transactions",
    response_model=Page[BankTransactionRead],
    tags=["Finance · Banking"],
)
async def list_bank_transactions(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    bank_account_id: Optional[UUID] = None,
    reconciled: Optional[bool] = None,
    matched: Optional[bool] = None,
    q: Optional[str] = None,
    user: User = Depends(read_bank_transactions),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BankTransaction)
    count_stmt = select(func.count()).select_from(BankTransaction)
    if not user.is_superuser and user.tenant_id:
        tenant_filter = BankTransaction.tenant_id == user.tenant_id
        stmt = stmt.where(tenant_filter)
        count_stmt = count_stmt.where(tenant_filter)
    if bank_account_id:
        stmt = stmt.where(BankTransaction.bank_account_id == bank_account_id)
        count_stmt = count_stmt.where(BankTransaction.bank_account_id == bank_account_id)
    if reconciled is not None:
        stmt = stmt.where(BankTransaction.reconciled.is_(reconciled))
        count_stmt = count_stmt.where(BankTransaction.reconciled.is_(reconciled))
    if matched is not None:
        match_filter = (
            BankTransaction.matched_journal_line_id.is_not(None)
            if matched
            else BankTransaction.matched_journal_line_id.is_(None)
        )
        stmt = stmt.where(match_filter)
        count_stmt = count_stmt.where(match_filter)
    if q:
        search = or_(
            BankTransaction.description.ilike(f"%{q}%"),
            BankTransaction.reference.ilike(f"%{q}%"),
        )
        stmt = stmt.where(search)
        count_stmt = count_stmt.where(search)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(BankTransaction.txn_date.desc(), BankTransaction.created_at.desc())
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


@router.post(
    "/bank-transactions/import",
    tags=["Finance · Banking"],
)
async def import_bank_statement(
    request: Request,
    bank_account_id: UUID = Form(),
    file: UploadFile = File(),
    user: User = Depends(create_bank_transactions),
    db: AsyncSession = Depends(get_db),
):
    bank_account = await _get_bank_account(db, user, bank_account_id)
    if not bank_account.is_active:
        raise ValidationError("Select an active bank account")
    raw = await file.read(10 * 1024 * 1024 + 1)
    if len(raw) > 10 * 1024 * 1024:
        raise ValidationError("Bank statement file cannot exceed 10 MB")
    try:
        content = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationError("Bank statement CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(content))
    if not reader.fieldnames:
        raise ValidationError("Bank statement CSV must include a header row")
    columns = {name.strip().lower(): name for name in reader.fieldnames if name}
    date_column = next(
        (columns[key] for key in ("date", "txn_date", "transaction_date") if key in columns),
        None,
    )
    amount_column = next(
        (columns[key] for key in ("amount", "transaction_amount") if key in columns),
        None,
    )
    if date_column is None or amount_column is None:
        raise ValidationError("CSV requires date and amount columns")
    description_column = next(
        (columns[key] for key in ("description", "narration", "details") if key in columns),
        None,
    )
    reference_column = next(
        (columns[key] for key in ("reference", "ref", "transaction_id") if key in columns),
        None,
    )
    rows = [
        row
        for row in reader
        if any(value and value.strip() for value in row.values())
    ]
    if not rows:
        raise ValidationError("Bank statement CSV contains no transactions")
    if len(rows) > 10000:
        raise ValidationError("A statement import cannot exceed 10,000 rows")

    parsed = []
    seen_hashes = set()
    for row_number, row in enumerate(rows, start=2):
        try:
            txn_date = _parse_statement_date(row.get(date_column) or "")
            raw_amount = (row.get(amount_column) or "").strip().replace(",", "")
            amount = Decimal(raw_amount)
        except (InvalidOperation, ValueError) as exc:
            raise ValidationError(f"Invalid date or amount on CSV row {row_number}") from exc
        if (
            not amount.is_finite()
            or amount == 0
            or abs(amount) >= Decimal("1000000000000")
        ):
            raise ValidationError(f"Invalid transaction amount on CSV row {row_number}")
        if amount != amount.quantize(Decimal("0.01")):
            raise ValidationError(f"Transaction amount has excess precision on row {row_number}")
        description = (
            (row.get(description_column) or "").strip()[:255]
            if description_column
            else None
        )
        reference = (
            (row.get(reference_column) or "").strip()[:120]
            if reference_column
            else None
        )
        transaction_hash = _transaction_hash(
            bank_account.id, txn_date, amount, description, reference
        )
        if transaction_hash in seen_hashes:
            continue
        seen_hashes.add(transaction_hash)
        parsed.append(
            {
                "txn_date": txn_date,
                "amount": amount,
                "description": description or None,
                "reference": reference or None,
                "transaction_hash": transaction_hash,
            }
        )

    existing_hashes = set(
        (
            await db.scalars(
                select(BankTransaction.transaction_hash).where(
                    BankTransaction.bank_account_id == bank_account.id,
                    BankTransaction.transaction_hash.in_(
                        [item["transaction_hash"] for item in parsed]
                    ),
                )
            )
        ).all()
    ) if parsed else set()
    if parsed:
        legacy_transactions = list(
            (
                await db.scalars(
                    select(BankTransaction).where(
                        BankTransaction.bank_account_id == bank_account.id,
                        BankTransaction.transaction_hash.is_(None),
                        BankTransaction.txn_date.in_(
                            {item["txn_date"] for item in parsed}
                        ),
                        BankTransaction.amount.in_(
                            {item["amount"] for item in parsed}
                        ),
                    )
                )
            ).all()
        )
        existing_hashes.update(
            _transaction_hash(
                bank_account.id,
                item.txn_date,
                item.amount,
                item.description,
                item.reference,
            )
            for item in legacy_transactions
        )
    created = [
        BankTransaction(
            tenant_id=bank_account.tenant_id,
            created_by_id=user.id,
            bank_account_id=bank_account.id,
            **item,
        )
        for item in parsed
        if item["transaction_hash"] not in existing_hashes
    ]
    db.add_all(created)
    await record_audit(
        db,
        user=user,
        action="import",
        module="finance",
        entity="BankStatement",
        changes={
            "bank_account_id": str(bank_account.id),
            "rows": len(rows),
            "imported": len(created),
            "duplicates": len(rows) - len(created),
        },
        request=request,
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        integrity_detail = str(exc.orig)
        if (
            "uq_finance_bank_transactions_account_hash" not in integrity_detail
            and "finance_bank_transactions.bank_account_id" not in integrity_detail
        ):
            raise
        raise ConflictError(
            "A concurrent statement import added matching rows; retry the import"
        ) from exc
    return {
        "rows_received": len(rows),
        "imported": len(created),
        "duplicates": len(rows) - len(created),
    }


@router.get(
    "/bank-transactions/{transaction_id}/matches",
    response_model=list[BankMatchCandidate],
    tags=["Finance · Banking"],
)
async def suggest_bank_matches(
    transaction_id: UUID,
    user: User = Depends(read_bank_transactions),
    db: AsyncSession = Depends(get_db),
):
    transaction_stmt = select(BankTransaction).where(BankTransaction.id == transaction_id)
    if not user.is_superuser and user.tenant_id:
        transaction_stmt = transaction_stmt.where(
            BankTransaction.tenant_id == user.tenant_id
        )
    transaction = await db.scalar(transaction_stmt)
    if transaction is None:
        raise NotFoundError("Bank transaction not found")
    if transaction.reconciled:
        raise ConflictError("Reconciled bank transactions cannot be rematched")
    if transaction.matched_journal_line_id is not None:
        raise ConflictError("Unmatch the current journal line before selecting a new match")
    bank_account = await _get_bank_account(db, user, transaction.bank_account_id)
    if bank_account.ledger_account_id is None:
        raise ValidationError("Map the bank account to a GL account before matching")
    await _require_bank_asset_account(db, bank_account)
    lower_date = transaction.txn_date - timedelta(days=14)
    upper_date = transaction.txn_date + timedelta(days=14)
    matched_lines = select(BankTransaction.matched_journal_line_id).where(
        BankTransaction.tenant_id == bank_account.tenant_id,
        BankTransaction.matched_journal_line_id.is_not(None),
        BankTransaction.id != transaction.id,
    )
    stmt = (
        select(JournalLine, JournalEntry)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            JournalLine.account_id == bank_account.ledger_account_id,
            JournalLine.tenant_id == bank_account.tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date >= lower_date,
            JournalEntry.entry_date <= upper_date,
            JournalLine.debit - JournalLine.credit == transaction.amount,
            JournalLine.id.not_in(matched_lines),
        )
        .order_by(
            func.abs(JournalEntry.entry_date - transaction.txn_date),
            JournalEntry.entry_date.desc(),
        )
        .limit(20)
    )
    rows = (await db.execute(stmt)).all()
    return [
        BankMatchCandidate(
            journal_line_id=line.id,
            journal_entry_id=entry.id,
            entry_number=entry.entry_number,
            entry_date=entry.entry_date,
            reference=entry.reference,
            memo=entry.memo,
            description=line.description,
            signed_amount=line.debit - line.credit,
        )
        for line, entry in rows
    ]


@router.post(
    "/bank-transactions/{transaction_id}/match",
    response_model=BankTransactionRead,
    tags=["Finance · Banking"],
)
async def match_bank_transaction(
    transaction_id: UUID,
    payload: BankTransactionMatch,
    request: Request,
    user: User = Depends(update_bank_transactions),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BankTransaction).where(BankTransaction.id == transaction_id).with_for_update()
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(BankTransaction.tenant_id == user.tenant_id)
    transaction = await db.scalar(stmt)
    if transaction is None:
        raise NotFoundError("Bank transaction not found")
    if transaction.reconciled:
        raise ConflictError("Reconciled bank transactions cannot be rematched")
    bank_account = await _get_bank_account(db, user, transaction.bank_account_id)
    if bank_account.ledger_account_id is None:
        raise ValidationError("Map the bank account to a GL account before matching")
    await _require_bank_asset_account(db, bank_account)
    line = await db.scalar(
        select(JournalLine)
        .join(JournalEntry, JournalEntry.id == JournalLine.journal_entry_id)
        .where(
            JournalLine.id == payload.journal_line_id,
            JournalLine.account_id == bank_account.ledger_account_id,
            JournalLine.tenant_id == bank_account.tenant_id,
            JournalEntry.status == "posted",
            JournalEntry.entry_date.between(
                transaction.txn_date - timedelta(days=14),
                transaction.txn_date + timedelta(days=14),
            ),
            JournalLine.debit - JournalLine.credit == transaction.amount,
        )
        .with_for_update()
    )
    if line is None:
        raise ValidationError(
            "Select a posted journal line for this bank account with the same signed amount and a date within 14 days"
        )
    already_matched = await db.scalar(
        select(BankTransaction.id).where(
            BankTransaction.matched_journal_line_id == line.id,
            BankTransaction.id != transaction.id,
        )
    )
    if already_matched:
        raise ConflictError("Journal line is already matched to another bank transaction")
    transaction.matched_journal_line_id = line.id
    await record_audit(
        db,
        user=user,
        action="match",
        module="finance",
        entity="BankTransaction",
        entity_id=transaction.id,
        changes={"journal_line_id": str(line.id)},
        request=request,
    )
    await db.commit()
    await db.refresh(transaction)
    return transaction


@router.post(
    "/bank-transactions/{transaction_id}/reconcile",
    response_model=BankTransactionRead,
    tags=["Finance · Banking"],
)
async def reconcile_bank_transaction(
    transaction_id: UUID,
    request: Request,
    user: User = Depends(update_bank_transactions),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BankTransaction).where(BankTransaction.id == transaction_id).with_for_update()
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(BankTransaction.tenant_id == user.tenant_id)
    transaction = await db.scalar(stmt)
    if transaction is None:
        raise NotFoundError("Bank transaction not found")
    if transaction.matched_journal_line_id is None:
        raise ConflictError("Match this bank transaction to a posted journal line before reconciling")
    if not transaction.reconciled:
        transaction.reconciled = True
        await record_audit(
            db,
            user=user,
            action="reconcile",
            module="finance",
            entity="BankTransaction",
            entity_id=transaction.id,
            changes={"journal_line_id": str(transaction.matched_journal_line_id)},
            request=request,
        )
    await db.commit()
    await db.refresh(transaction)
    return transaction


async def _require_bank_asset_account(
    db: AsyncSession, bank_account: BankAccount
) -> Account:
    account = await db.scalar(
        select(Account).where(
            Account.id == bank_account.ledger_account_id,
            Account.tenant_id == bank_account.tenant_id,
            Account.account_type == "asset",
            Account.is_active.is_(True),
        )
    )
    if account is None:
        raise ValidationError("Bank account must map to an active asset GL account")
    return account


@router.post(
    "/bank-transactions/{transaction_id}/unreconcile",
    response_model=BankTransactionRead,
    tags=["Finance · Banking"],
)
async def unreconcile_bank_transaction(
    transaction_id: UUID,
    payload: BankReconciliationUndo,
    request: Request,
    user: User = Depends(update_bank_transactions),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BankTransaction).where(BankTransaction.id == transaction_id).with_for_update()
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(BankTransaction.tenant_id == user.tenant_id)
    transaction = await db.scalar(stmt)
    if transaction is None:
        raise NotFoundError("Bank transaction not found")
    if not transaction.reconciled:
        raise ConflictError("Bank transaction is not reconciled")
    transaction.reconciled = False
    await record_audit(
        db,
        user=user,
        action="unreconcile",
        module="finance",
        entity="BankTransaction",
        entity_id=transaction.id,
        changes={
            "journal_line_id": str(transaction.matched_journal_line_id),
            "reason": payload.reason.strip(),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(transaction)
    return transaction


@router.post(
    "/bank-transactions/{transaction_id}/unmatch",
    response_model=BankTransactionRead,
    tags=["Finance · Banking"],
)
async def unmatch_bank_transaction(
    transaction_id: UUID,
    request: Request,
    user: User = Depends(update_bank_transactions),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(BankTransaction).where(BankTransaction.id == transaction_id).with_for_update()
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(BankTransaction.tenant_id == user.tenant_id)
    transaction = await db.scalar(stmt)
    if transaction is None:
        raise NotFoundError("Bank transaction not found")
    if transaction.reconciled:
        raise ConflictError("Reconciled transactions cannot be unmatched; reverse the reconciliation first")
    matched_line_id = transaction.matched_journal_line_id
    transaction.matched_journal_line_id = None
    await record_audit(
        db,
        user=user,
        action="unmatch",
        module="finance",
        entity="BankTransaction",
        entity_id=transaction.id,
        changes={"journal_line_id": str(matched_line_id) if matched_line_id else None},
        request=request,
    )
    await db.commit()
    await db.refresh(transaction)
    return transaction


@router.get(
    "/bank-accounts/{bank_account_id}/reconciliation-summary",
    response_model=BankReconciliationSummary,
    tags=["Finance · Banking"],
)
async def bank_reconciliation_summary(
    bank_account_id: UUID,
    user: User = Depends(read_bank_transactions),
    db: AsyncSession = Depends(get_db),
):
    bank_account = await _get_bank_account(db, user, bank_account_id)
    transaction_totals = (
        await db.execute(
            select(
                func.count(BankTransaction.id),
                func.count(BankTransaction.matched_journal_line_id),
                func.sum(
                    case((BankTransaction.reconciled.is_(True), 1), else_=0)
                ),
                func.coalesce(func.sum(BankTransaction.amount), 0),
            ).where(
                BankTransaction.bank_account_id == bank_account.id,
                BankTransaction.tenant_id == bank_account.tenant_id,
            )
        )
    ).one()
    imported_count, matched_count, reconciled_count, statement_net = transaction_totals
    ledger_net = Decimal("0")
    if matched_count:
        ledger_net = Decimal(
            str(
                (
                    await db.scalar(
                        select(
                            func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)
                        )
                        .join(BankTransaction, BankTransaction.matched_journal_line_id == JournalLine.id)
                        .where(
                            BankTransaction.bank_account_id == bank_account.id,
                            BankTransaction.tenant_id == bank_account.tenant_id,
                            BankTransaction.matched_journal_line_id.is_not(None),
                        )
                    )
                )
                or 0
            )
        )
    statement_net = Decimal(str(statement_net or 0))
    return BankReconciliationSummary(
        imported_count=imported_count or 0,
        matched_count=matched_count or 0,
        reconciled_count=reconciled_count or 0,
        unmatched_count=(imported_count or 0) - (matched_count or 0),
        statement_balance=statement_net,
        ledger_balance=ledger_net,
        difference=statement_net - ledger_net,
    )


def _vendor_invoice_has_posted_entry():
    return (
        select(JournalEntry.id)
        .where(
            JournalEntry.tenant_id == VendorInvoice.tenant_id,
            JournalEntry.reference == "VINV:" + VendorInvoice.invoice_number,
            JournalEntry.status == "posted",
        )
        .exists()
    )


def _pending_vendor_payment_total():
    return (
        select(func.coalesce(func.sum(VendorPayment.amount), 0))
        .where(
            VendorPayment.vendor_invoice_id == VendorInvoice.id,
            VendorPayment.status == "pending_approval",
        )
        .correlate(VendorInvoice)
        .scalar_subquery()
    )


@router.get(
    "/payments",
    response_model=Page[PaymentRead],
    tags=["Finance · Payments"],
)
async def list_payments(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    invoice_id: Optional[UUID] = None,
    method: Optional[str] = None,
    user: User = Depends(read_payments),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Payment)
    count_stmt = select(func.count()).select_from(Payment)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Payment.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(Payment.tenant_id == user.tenant_id)
    if invoice_id:
        stmt = stmt.where(Payment.invoice_id == invoice_id)
        count_stmt = count_stmt.where(Payment.invoice_id == invoice_id)
    if method:
        stmt = stmt.where(Payment.method == method)
        count_stmt = count_stmt.where(Payment.method == method)
    if q:
        search = Payment.reference.ilike(f"%{q}%")
        stmt = stmt.where(search)
        count_stmt = count_stmt.where(search)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(Payment.paid_on.desc(), Payment.created_at.desc())
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


async def _get_invoice_for_payment(
    db: AsyncSession, user: User, invoice_id: UUID
) -> Invoice:
    stmt = select(Invoice).where(Invoice.id == invoice_id).with_for_update()
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Invoice.tenant_id == user.tenant_id)
    invoice = await db.scalar(stmt)
    if invoice is None:
        raise NotFoundError("Invoice not found")
    return invoice


@router.post(
    "/payments",
    response_model=PaymentRead,
    status_code=201,
    tags=["Finance · Payments"],
)
async def record_payment(
    payload: PaymentCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(create_payments),
    db: AsyncSession = Depends(get_db),
):
    invoice = await _get_invoice_for_payment(db, user, payload.invoice_id)
    invoice_id = invoice.id
    tenant_id = user.tenant_id
    try:
        payment, created = await create_payment(
            db, user, invoice, payload, idempotency_key=idempotency_key
        )
    except IntegrityError as exc:
        await db.rollback()
        payment = await db.scalar(
            select(Payment).where(
                Payment.tenant_id == tenant_id,
                Payment.idempotency_key == idempotency_key.strip(),
            )
        )
        if payment is None:
            raise ConflictError("Payment conflicts with an existing ledger update") from exc
        if not payment_matches_request(payment, invoice_id, payload):
            raise ConflictError("Idempotency-Key was already used for a different payment") from exc
        created = False
    if created:
        await record_audit(
            db,
            user=user,
            action="create",
            module="finance",
            entity="Payment",
            entity_id=payment.id,
            changes={
                "invoice": invoice.invoice_number,
                "amount": str(payment.amount),
                "journal_entry_id": str(payment.journal_entry_id),
            },
            request=request,
        )
    await db.commit()
    await db.refresh(payment)
    return payment


@router.get(
    "/vendor-payments/outstanding",
    response_model=Page[VendorPayableRead],
    tags=["Finance · Accounts Payable"],
)
async def list_outstanding_vendor_invoices(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    user: User = Depends(read_payments),
    db: AsyncSession = Depends(get_db),
):
    available_balance = (
        VendorInvoice.amount
        + VendorInvoice.tax_amount
        - VendorInvoice.paid_amount
        - _pending_vendor_payment_total()
    )
    stmt = (
        select(VendorInvoice, Vendor.name, _pending_vendor_payment_total())
        .join(Vendor, Vendor.id == VendorInvoice.vendor_id)
        .where(
            VendorInvoice.tenant_id == user.tenant_id,
            VendorInvoice.is_active.is_(True),
            VendorInvoice.status.in_(("approved", "partially_paid")),
            available_balance > 0,
            _vendor_invoice_has_posted_entry(),
        )
    )
    count_stmt = (
        select(func.count())
        .select_from(VendorInvoice)
        .join(Vendor, Vendor.id == VendorInvoice.vendor_id)
        .where(
            VendorInvoice.tenant_id == user.tenant_id,
            VendorInvoice.is_active.is_(True),
            VendorInvoice.status.in_(("approved", "partially_paid")),
            available_balance > 0,
            _vendor_invoice_has_posted_entry(),
        )
    )
    if q:
        search = or_(
            VendorInvoice.invoice_number.ilike(f"%{q}%"),
            Vendor.name.ilike(f"%{q}%"),
        )
        stmt = stmt.where(search)
        count_stmt = count_stmt.where(search)
    total = int((await db.scalar(count_stmt)) or 0)
    rows = (
        await db.execute(
            stmt.order_by(VendorInvoice.due_date.asc().nulls_last(), VendorInvoice.issue_date.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()
    items = [
        VendorPayableRead(
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
            vendor_id=invoice.vendor_id,
            vendor_name=vendor_name,
            issue_date=invoice.issue_date,
            due_date=invoice.due_date,
            total=invoice.amount + invoice.tax_amount,
            paid_amount=invoice.paid_amount,
            outstanding=invoice.amount + invoice.tax_amount - invoice.paid_amount - Decimal(pending_total or 0),
            status=invoice.status,
        )
        for invoice, vendor_name, pending_total in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }


@router.get(
    "/vendor-payments/summary",
    response_model=VendorPayablesSummary,
    tags=["Finance · Accounts Payable"],
)
async def summarize_outstanding_vendor_invoices(
    user: User = Depends(read_payments),
    db: AsyncSession = Depends(get_db),
):
    available_balance = (
        VendorInvoice.amount
        + VendorInvoice.tax_amount
        - VendorInvoice.paid_amount
        - _pending_vendor_payment_total()
    )
    open_bills = (
        VendorInvoice.tenant_id == user.tenant_id,
        VendorInvoice.is_active.is_(True),
        VendorInvoice.status.in_(("approved", "partially_paid")),
        available_balance > 0,
        _vendor_invoice_has_posted_entry(),
    )
    count, outstanding = (
        await db.execute(
            select(
                func.count(VendorInvoice.id),
                func.coalesce(
                    func.sum(
                        available_balance
                    ),
                    0,
                ),
            ).where(*open_bills)
        )
    ).one()
    return {"bill_count": count, "outstanding_total": outstanding}


@router.get(
    "/vendor-payments",
    response_model=Page[VendorPaymentRead],
    tags=["Finance · Accounts Payable"],
)
async def list_vendor_payments(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(read_payments),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(VendorPayment).where(VendorPayment.tenant_id == user.tenant_id)
    total = int(
        (
            await db.scalar(
                select(func.count())
                .select_from(VendorPayment)
                .where(VendorPayment.tenant_id == user.tenant_id)
            )
        )
        or 0
    )
    items = list(
        (
            await db.scalars(
                stmt.order_by(VendorPayment.paid_on.desc(), VendorPayment.created_at.desc())
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


@router.post(
    "/vendor-payments",
    response_model=VendorPaymentRead,
    status_code=201,
    tags=["Finance · Accounts Payable"],
)
async def record_vendor_payment(
    payload: VendorPaymentCreate,
    request: Request,
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(create_payments),
    db: AsyncSession = Depends(get_db),
):
    invoice_stmt = (
        select(VendorInvoice)
        .where(VendorInvoice.id == payload.vendor_invoice_id)
        .with_for_update()
    )
    if not user.is_superuser and user.tenant_id:
        invoice_stmt = invoice_stmt.where(VendorInvoice.tenant_id == user.tenant_id)
    invoice = await db.scalar(invoice_stmt)
    if invoice is None:
        raise NotFoundError("Vendor invoice not found")
    invoice_id = invoice.id
    tenant_id = invoice.tenant_id
    try:
        payment, created = await create_vendor_payment(
            db, user, invoice, payload, idempotency_key=idempotency_key
        )
    except IntegrityError as exc:
        await db.rollback()
        payment = await db.scalar(
            select(VendorPayment).where(
                VendorPayment.tenant_id == tenant_id,
                VendorPayment.idempotency_key == idempotency_key.strip(),
            )
        )
        if payment is None:
            raise ConflictError("Payment conflicts with an existing ledger update") from exc
        if not vendor_payment_matches_request(payment, invoice_id, payload):
            raise ConflictError("Idempotency-Key was already used for a different payment") from exc
        created = False
    if created:
        approval = await submit_finance_approval(
            db,
            user,
            entity_type="vendor_payment",
            entity_id=payment.id,
            amount=payment.amount,
            summary=f"Vendor payment: {invoice.invoice_number}",
            tenant_id=invoice.tenant_id,
        )
        await record_audit(
            db,
            user=user,
            action="submit_for_approval",
            module="finance",
            entity="VendorPayment",
            entity_id=payment.id,
            changes={
                "invoice": invoice.invoice_number,
                "amount": str(payment.amount),
                "approval_id": str(approval.id),
            },
            request=request,
        )
    await db.commit()
    await db.refresh(payment)
    return payment


@router.get(
    "/periods",
    response_model=Page[FinancialPeriodRead],
    tags=["Finance · Periods"],
)
async def list_financial_periods(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    status: Optional[str] = None,
    user: User = Depends(read_periods),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(FinancialPeriod).where(FinancialPeriod.tenant_id == user.tenant_id)
    count_stmt = (
        select(func.count())
        .select_from(FinancialPeriod)
        .where(FinancialPeriod.tenant_id == user.tenant_id)
    )
    if status:
        stmt = stmt.where(FinancialPeriod.status == status)
        count_stmt = count_stmt.where(FinancialPeriod.status == status)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (
            await db.scalars(
                stmt.order_by(FinancialPeriod.start_date.desc())
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


@router.post(
    "/periods",
    response_model=FinancialPeriodRead,
    status_code=201,
    tags=["Finance · Periods"],
)
async def new_financial_period(
    payload: FinancialPeriodCreate,
    request: Request,
    user: User = Depends(create_periods),
    db: AsyncSession = Depends(get_db),
):
    period = await create_financial_period(
        db,
        user,
        name=payload.name,
        start_date=payload.start_date,
        end_date=payload.end_date,
    )
    await record_audit(
        db,
        user=user,
        action="create",
        module="finance",
        entity="FinancialPeriod",
        entity_id=period.id,
        changes={
            "name": period.name,
            "start_date": period.start_date.isoformat(),
            "end_date": period.end_date.isoformat(),
        },
        request=request,
    )
    await db.commit()
    await db.refresh(period)
    return period


async def _get_financial_period(db: AsyncSession, user: User, period_id: UUID) -> FinancialPeriod:
    stmt = select(FinancialPeriod).where(FinancialPeriod.id == period_id)
    stmt = stmt.where(FinancialPeriod.tenant_id == user.tenant_id)
    stmt = stmt.with_for_update()
    period = await db.scalar(stmt)
    if period is None:
        raise NotFoundError("Financial period not found")
    return period


async def _period_close_checklist(db: AsyncSession, user: User, period: FinancialPeriod) -> PeriodCloseChecklist:
    period_window = (
        JournalEntry.tenant_id == period.tenant_id,
        JournalEntry.entry_date >= period.start_date,
        JournalEntry.entry_date <= period.end_date,
    )
    draft_count = int(await db.scalar(
        select(func.count()).select_from(JournalEntry).where(
            *period_window,
            JournalEntry.status == "draft",
            JournalEntry.is_active.is_(True),
        )
    ) or 0)

    journal_ids = list((await db.scalars(select(JournalEntry.id).where(*period_window))).all())
    vendor_ids = list((await db.scalars(select(VendorPayment.id).where(
        VendorPayment.tenant_id == period.tenant_id,
        VendorPayment.paid_on >= period.start_date,
        VendorPayment.paid_on <= period.end_date,
    ))).all())
    move_ids = list((await db.scalars(select(StockMove.id).where(
        StockMove.tenant_id == period.tenant_id,
        StockMove.movement_date >= period.start_date,
        StockMove.movement_date <= period.end_date,
    ))).all())
    approval_pending_filters = []
    if journal_ids:
        approval_pending_filters.append(
            (FinanceApproval.entity_type == "journal_entry")
            & FinanceApproval.entity_id.in_(journal_ids)
        )
    if vendor_ids:
        approval_pending_filters.append(
            (FinanceApproval.entity_type == "vendor_payment")
            & FinanceApproval.entity_id.in_(vendor_ids)
        )
    if move_ids:
        approval_pending_filters.append(
            (FinanceApproval.entity_type == "inventory_adjustment")
            & FinanceApproval.entity_id.in_(move_ids)
        )
    pending_count = 0
    if approval_pending_filters:
        pending_count = int(await db.scalar(
            select(func.count()).select_from(FinanceApproval).where(
                FinanceApproval.tenant_id == period.tenant_id,
                FinanceApproval.status == "pending",
                or_(*approval_pending_filters),
            )
        ) or 0)

    overdue_ar_count = int(await db.scalar(
        select(func.count()).select_from(Invoice).where(
            Invoice.tenant_id == period.tenant_id,
            Invoice.is_active.is_(True),
            Invoice.status.in_(("sent", "partially_paid", "overdue")),
            Invoice.issue_date >= period.start_date,
            Invoice.issue_date <= period.end_date,
            Invoice.due_date.is_not(None),
            Invoice.due_date < date.today(),
            Invoice.total > Invoice.amount_paid,
        )
    ) or 0)

    overdue_ap_count = int(await db.scalar(
        select(func.count()).select_from(VendorInvoice).where(
            VendorInvoice.tenant_id == period.tenant_id,
            VendorInvoice.is_active.is_(True),
            VendorInvoice.status.in_(("approved", "partially_paid")),
            VendorInvoice.issue_date >= period.start_date,
            VendorInvoice.issue_date <= period.end_date,
            VendorInvoice.due_date.is_not(None),
            VendorInvoice.due_date < date.today(),
            VendorInvoice.amount + VendorInvoice.tax_amount > VendorInvoice.paid_amount,
        )
    ) or 0)

    unmatched_bank_count = int(await db.scalar(
        select(func.count()).select_from(BankTransaction).where(
            BankTransaction.tenant_id == period.tenant_id,
            BankTransaction.txn_date >= period.start_date,
            BankTransaction.txn_date <= period.end_date,
            BankTransaction.reconciled.is_(False),
            BankTransaction.is_active.is_(True),
        )
    ) or 0)

    open_grni_count = int(await db.scalar(
        select(func.count()).select_from(GRNAccrual)
        .join(GoodsReceipt, GoodsReceipt.id == GRNAccrual.goods_receipt_id)
        .where(
            GRNAccrual.tenant_id == period.tenant_id,
            GoodsReceipt.received_date >= period.start_date,
            GoodsReceipt.received_date <= period.end_date,
            GRNAccrual.cleared_by_invoice_id.is_(None),
        )
    ) or 0)

    items = [
        PeriodCloseChecklistItem(key="draft_journals", label="Draft journals in period", count=draft_count, ready=draft_count == 0),
        PeriodCloseChecklistItem(key="pending_approvals", label="Pending finance approvals", count=pending_count, ready=pending_count == 0),
        PeriodCloseChecklistItem(key="overdue_receivables", label="Overdue receivables", count=overdue_ar_count, ready=overdue_ar_count == 0),
        PeriodCloseChecklistItem(key="overdue_payables", label="Overdue payables", count=overdue_ap_count, ready=overdue_ap_count == 0),
        PeriodCloseChecklistItem(key="unmatched_bank", label="Unmatched bank transactions", count=unmatched_bank_count, ready=unmatched_bank_count == 0),
        PeriodCloseChecklistItem(key="open_grni", label="Open GRNI receipts", count=open_grni_count, ready=open_grni_count == 0),
    ]
    return PeriodCloseChecklist(period_id=period.id, ready=all(item.ready for item in items), items=items)


@router.get(
    "/periods/{period_id}/close-checklist",
    response_model=PeriodCloseChecklist,
    tags=["Finance · Periods"],
)
async def get_period_close_checklist(
    period_id: UUID,
    user: User = Depends(close_periods),
    db: AsyncSession = Depends(get_db),
):
    period = await _get_financial_period(db, user, period_id)
    return await _period_close_checklist(db, user, period)


@router.post(
    "/periods/{period_id}/sign-off",
    response_model=FinancialPeriodRead,
    tags=["Finance · Periods"],
)
async def sign_off_period_close(
    period_id: UUID,
    payload: PeriodCloseSignoffCreate,
    request: Request,
    user: User = Depends(close_periods),
    db: AsyncSession = Depends(get_db),
):
    period = await _get_financial_period(db, user, period_id)
    checklist = await _period_close_checklist(db, user, period)
    if not checklist.ready:
        unresolved = ", ".join(item.label for item in checklist.items if not item.ready)
        raise ConflictError(f"Cannot sign off period close while the checklist has exceptions: {unresolved}")
    period.close_signed_by_id = user.id
    period.close_signed_at = datetime.now(timezone.utc)
    period.close_signoff_reason = payload.reason.strip()
    await record_audit(
        db,
        user=user,
        action="signoff",
        module="finance",
        entity="FinancialPeriod",
        entity_id=period.id,
        changes={"reason": payload.reason.strip()},
        request=request,
    )
    await db.commit()
    await db.refresh(period)
    return period


@router.post(
    "/periods/{period_id}/close",
    response_model=FinancialPeriodRead,
    tags=["Finance · Periods"],
)
async def close_financial_period(
    period_id: UUID,
    request: Request,
    user: User = Depends(close_periods),
    db: AsyncSession = Depends(get_db),
):
    period = await _get_financial_period(db, user, period_id)
    await set_financial_period_status(db, user, period, status="closed")
    await record_audit(
        db,
        user=user,
        action="close",
        module="finance",
        entity="FinancialPeriod",
        entity_id=period.id,
        changes={"status": "closed"},
        request=request,
    )
    await db.commit()
    await db.refresh(period)
    return period


@router.post(
    "/periods/{period_id}/reopen",
    response_model=FinancialPeriodRead,
    tags=["Finance · Periods"],
)
async def reopen_financial_period(
    period_id: UUID,
    request: Request,
    user: User = Depends(reopen_periods),
    db: AsyncSession = Depends(get_db),
):
    period = await _get_financial_period(db, user, period_id)
    await set_financial_period_status(db, user, period, status="open")
    await record_audit(
        db,
        user=user,
        action="reopen",
        module="finance",
        entity="FinancialPeriod",
        entity_id=period.id,
        changes={"status": "open"},
        request=request,
    )
    await db.commit()
    await db.refresh(period)
    return period


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
    approval_rows = list(
        (
            await db.execute(
                select(FinanceApproval.entity_id, FinanceApproval.status)
                .where(
                    FinanceApproval.tenant_id == user.tenant_id,
                    FinanceApproval.entity_type == "journal_entry",
                    FinanceApproval.entity_id.in_([item.id for item in items]),
                )
                .order_by(FinanceApproval.created_at.desc())
            )
        ).all()
    ) if items else []
    approval_statuses = {}
    for entity_id, approval_status in approval_rows:
        approval_statuses.setdefault(entity_id, approval_status)
    reversals_stmt = select(JournalEntry).where(
        JournalEntry.reversal_of_id.in_([item.id for item in items]),
    )
    reversals = list((await db.scalars(reversals_stmt)).all()) if items else []
    reversed_by = {item.reversal_of_id: item.id for item in reversals}
    return {
        "items": [
            {
                **JournalEntryRead.model_validate(item).model_dump(),
                "approval_status": approval_statuses.get(item.id),
                "reversed_by_entry_id": reversed_by.get(item.id),
            }
            for item in items
        ],
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
    entry_stmt = select(JournalEntry).options(
        selectinload(JournalEntry.lines)
    ).where(JournalEntry.id == entry_id)
    if not user.is_superuser and user.tenant_id:
        entry_stmt = entry_stmt.where(JournalEntry.tenant_id == user.tenant_id)
    entry = await db.scalar(entry_stmt.with_for_update())
    if entry is None:
        raise NotFoundError("Journal entry not found")
    if entry.status != "draft":
        raise ConflictError("Only draft journal entries can be submitted for approval")
    pending = await db.scalar(
        select(FinanceApproval.id).where(
            FinanceApproval.tenant_id == entry.tenant_id,
            FinanceApproval.entity_type == "journal_entry",
            FinanceApproval.entity_id == entry.id,
            FinanceApproval.status == "pending",
        )
    )
    if pending is None:
        amount = sum((line.debit for line in entry.lines), Decimal("0"))
        approval = await submit_finance_approval(
            db,
            user,
            entity_type="journal_entry",
            entity_id=entry.id,
            amount=amount,
            summary=f"Manual journal: {entry.entry_number}",
            tenant_id=entry.tenant_id,
        )
        await record_audit(
            db,
            user=user,
            action="submit_for_approval",
            module="finance",
            entity="JournalEntry",
            entity_id=entry.id,
            changes={"approval_id": str(approval.id)},
            request=request,
        )
    await db.commit()
    result = JournalEntryRead.model_validate(await get_journal_entry(db, user, entry.id))
    result.approval_status = "pending"
    return result


@router.post(
    "/journal-entries/{entry_id}/reverse",
    response_model=JournalEntryRead,
    tags=["Finance · Journal"],
)
async def reverse_entry(
    entry_id: UUID,
    payload: JournalReversalCreate,
    request: Request,
    user: User = Depends(reverse_permission),
    db: AsyncSession = Depends(get_db),
):
    entry = await get_journal_entry(db, user, entry_id)
    reversal, created = await reverse_journal_entry(db, user, entry, payload)
    if created:
        await record_audit(
            db,
            user=user,
            action="reverse",
            module="finance",
            entity="JournalEntry",
            entity_id=entry.id,
            changes={
                "reversal_entry_id": str(reversal.id),
                "reversal_entry_number": reversal.entry_number,
                "reversal_date": reversal.entry_date.isoformat(),
                "reason": payload.reason.strip(),
            },
            request=request,
        )
    await db.commit()
    return await get_journal_entry(db, user, reversal.id)


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


@router.put(
    "/invoices/{invoice_id}/tax-lines",
    response_model=list[InvoiceTaxLineRead],
    tags=["Finance · GST"],
)
async def replace_invoice_tax_lines(
    invoice_id: UUID,
    payload: InvoiceTaxLinesUpdate,
    request: Request,
    user: User = Depends(require_permissions("finance.invoice.update")),
    db: AsyncSession = Depends(get_db),
):
    invoice = await db.scalar(
        _tenant_scope(select(Invoice).where(Invoice.id == invoice_id).with_for_update(), Invoice, user)
    )
    if invoice is None:
        raise NotFoundError("Invoice not found")
    if invoice.status != "draft":
        raise ConflictError("GST lines can only be changed on a draft invoice")
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
            InvoiceTaxLine(
                tenant_id=invoice.tenant_id,
                created_by_id=user.id,
                invoice_id=invoice.id,
                **{
                    key: value
                    for key, value in values.items()
                    if key.startswith("output_") or key not in {
                        "input_cgst_account_id",
                        "input_sgst_account_id",
                        "input_igst_account_id",
                    }
                },
            )
        )
    base, tax = tax_line_totals(tax_lines)
    invoice.subtotal = base
    invoice.tax = tax
    invoice.total = base + tax
    await db.execute(
        delete(InvoiceTaxLine).where(InvoiceTaxLine.invoice_id == invoice.id)
    )
    db.add_all(tax_lines)
    await record_audit(
        db,
        user=user,
        action="replace_tax_lines",
        module="finance",
        entity="Invoice",
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
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=8, max_length=128),
    user: User = Depends(require_permissions("finance.payment.create")),
    db: AsyncSession = Depends(get_db),
):
    invoice = await _get_invoice_for_payment(db, user, invoice_id)
    if payload.invoice_id != invoice.id:
        raise ValidationError("Payment invoice_id does not match the route")
    payload.invoice_id = invoice.id
    requested_invoice_id = invoice.id
    tenant_id = user.tenant_id
    try:
        payment, created = await create_payment(
            db, user, invoice, payload, idempotency_key=idempotency_key
        )
    except IntegrityError as exc:
        await db.rollback()
        payment = await db.scalar(
            select(Payment).where(
                Payment.tenant_id == tenant_id,
                Payment.idempotency_key == idempotency_key.strip(),
            )
        )
        if payment is None:
            raise ConflictError("Payment conflicts with an existing ledger update") from exc
        if not payment_matches_request(payment, requested_invoice_id, payload):
            raise ConflictError("Idempotency-Key was already used for a different payment") from exc
        created = False
    if created:
        await record_audit(
            db,
            user=user,
            action="create",
            module="finance",
            entity="Payment",
            entity_id=payment.id,
            changes={"invoice": invoice.invoice_number, "amount": str(payload.amount)},
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


@router.get(
    "/reports/grni",
    response_model=GRNISummary,
    tags=["Finance · Reports"],
)
async def report_grni(
    user: User = Depends(read_reports), db: AsyncSession = Depends(get_db)
):
    stmt = select(
        func.count(GRNAccrual.id),
        func.coalesce(func.sum(GRNAccrual.accrued_amount), 0),
    ).where(
        GRNAccrual.is_active.is_(True),
        GRNAccrual.cleared_by_invoice_id.is_(None),
    )
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(GRNAccrual.tenant_id == user.tenant_id)
    receipt_count, outstanding_total = (await db.execute(stmt)).one()
    return {
        "receipt_count": receipt_count,
        "outstanding_total": outstanding_total,
    }


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


@router.get("/reports/aging", response_model=AgingReport, tags=["Finance · Reports"])
async def report_aging(
    user: User = Depends(read_reports), db: AsyncSession = Depends(get_db)
):
    data = await aging_report(db, user)
    return AgingReport(**data)


@router.get("/reports/exceptions", response_model=AccountingExceptionSummary, tags=["Finance · Reports"])
async def report_accounting_exceptions(
    user: User = Depends(read_reports), db: AsyncSession = Depends(get_db)
):
    data = await accounting_exceptions(db, user)
    return AccountingExceptionSummary(**data)


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
