from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.core.schemas import ORMModel


class AccountBase(ORMModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    account_type: str = Field(pattern="^(asset|liability|equity|income|expense)$")
    parent_id: Optional[UUID] = None
    description: Optional[str] = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Account code cannot be blank")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Account name cannot be blank")
        return normalized


class AccountCreate(AccountBase):
    pass


class AccountUpdate(ORMModel):
    code: Optional[str] = Field(default=None, min_length=1, max_length=30)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    account_type: Optional[str] = None
    parent_id: Optional[UUID] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("code")
    @classmethod
    def normalize_code(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Account code cannot be blank")
        return normalized

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Account name cannot be blank")
        return normalized

    @field_validator("account_type")
    @classmethod
    def validate_account_type(cls, value: Optional[str]) -> Optional[str]:
        allowed = {"asset", "liability", "equity", "income", "expense"}
        if value is not None and value not in allowed:
            raise ValueError("Unsupported account type")
        return value


class AccountRead(ORMModel):
    id: UUID
    code: str
    name: str
    account_type: str
    parent_id: Optional[UUID] = None
    description: Optional[str] = None
    is_active: bool
    created_at: datetime


class JournalLineCreate(ORMModel):
    account_id: UUID
    description: Optional[str] = None
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


class JournalEntryCreate(ORMModel):
    entry_date: date
    reference: Optional[str] = None
    memo: Optional[str] = None
    lines: list[JournalLineCreate] = Field(min_length=2)


class JournalLineRead(ORMModel):
    id: UUID
    account_id: UUID
    description: Optional[str] = None
    debit: Decimal
    credit: Decimal
    account: Optional[AccountRead] = None


class JournalEntryRead(ORMModel):
    id: UUID
    entry_number: str
    entry_date: date
    reference: Optional[str] = None
    memo: Optional[str] = None
    status: str
    approval_status: Optional[str] = None
    posted_at: Optional[datetime] = None
    reversal_of_id: Optional[UUID] = None
    reversed_by_entry_id: Optional[UUID] = None
    created_at: datetime
    lines: list[JournalLineRead] = []


class FinanceApprovalRead(ORMModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    amount: Decimal
    summary: str
    requested_by_id: UUID
    status: str
    decided_by_id: Optional[UUID] = None
    decided_at: Optional[datetime] = None
    decision_reason: Optional[str] = None
    created_at: datetime


class FinanceApprovalDecision(ORMModel):
    reason: str = Field(min_length=3, max_length=500)


class JournalReversalCreate(ORMModel):
    reversal_date: date
    reason: str = Field(min_length=3, max_length=500)


class FinancialPeriodCreate(ORMModel):
    name: str = Field(min_length=1, max_length=120)
    start_date: date
    end_date: date


class FinancialPeriodRead(ORMModel):
    id: UUID
    name: str
    start_date: date
    end_date: date
    status: str
    closed_at: Optional[datetime] = None
    closed_by_id: Optional[UUID] = None
    close_signed_at: Optional[datetime] = None
    close_signed_by_id: Optional[UUID] = None
    close_signoff_reason: Optional[str] = None
    created_at: datetime


class PeriodCloseSignoffCreate(ORMModel):
    reason: str = Field(min_length=3, max_length=500)


class PeriodCloseChecklistItem(ORMModel):
    key: str
    label: str
    count: int
    ready: bool


class PeriodCloseChecklist(ORMModel):
    period_id: UUID
    ready: bool
    items: list[PeriodCloseChecklistItem]


class TaxRegistrationCreate(ORMModel):
    legal_name: str = Field(min_length=1, max_length=200)
    gstin: str = Field(pattern=r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")
    state_code: str = Field(pattern=r"^[0-9]{2}$")
    is_default: bool = False


class TaxRegistrationUpdate(ORMModel):
    legal_name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class TaxRegistrationRead(ORMModel):
    id: UUID
    legal_name: str
    gstin: str
    state_code: str
    is_default: bool
    is_active: bool
    created_at: datetime


class TaxCodeCreate(ORMModel):
    code: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=200)
    tax_type: str = Field(default="taxable", pattern="^(taxable|exempt|zero_rated|non_gst)$")
    cgst_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    sgst_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    igst_rate: Decimal = Field(default=Decimal("0"), ge=0, le=100)
    can_claim_itc: bool = True
    output_cgst_account_id: Optional[UUID] = None
    output_sgst_account_id: Optional[UUID] = None
    output_igst_account_id: Optional[UUID] = None
    input_cgst_account_id: Optional[UUID] = None
    input_sgst_account_id: Optional[UUID] = None
    input_igst_account_id: Optional[UUID] = None

    @field_validator("code")
    @classmethod
    def normalize_tax_code(cls, value: str) -> str:
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("Tax code cannot be blank")
        return normalized


class TaxCodeUpdate(ORMModel):
    description: Optional[str] = Field(default=None, min_length=1, max_length=200)
    tax_type: Optional[str] = Field(default=None, pattern="^(taxable|exempt|zero_rated|non_gst)$")
    cgst_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    sgst_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    igst_rate: Optional[Decimal] = Field(default=None, ge=0, le=100)
    can_claim_itc: Optional[bool] = None
    output_cgst_account_id: Optional[UUID] = None
    output_sgst_account_id: Optional[UUID] = None
    output_igst_account_id: Optional[UUID] = None
    input_cgst_account_id: Optional[UUID] = None
    input_sgst_account_id: Optional[UUID] = None
    input_igst_account_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class TaxCodeRead(ORMModel):
    id: UUID
    code: str
    description: str
    tax_type: str
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
    can_claim_itc: bool
    output_cgst_account_id: Optional[UUID] = None
    output_sgst_account_id: Optional[UUID] = None
    output_igst_account_id: Optional[UUID] = None
    input_cgst_account_id: Optional[UUID] = None
    input_sgst_account_id: Optional[UUID] = None
    input_igst_account_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime


class InvoiceTaxLineCreate(ORMModel):
    tax_code_id: UUID
    registration_id: UUID
    place_of_supply_state_code: str = Field(pattern=r"^[0-9]{2}$")
    taxable_amount: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    description: Optional[str] = Field(default=None, max_length=255)


class InvoiceTaxLinesUpdate(ORMModel):
    lines: list[InvoiceTaxLineCreate] = Field(min_length=1, max_length=200)


class InvoiceTaxLineRead(ORMModel):
    id: UUID
    tax_code_id: UUID
    registration_id: UUID
    tax_type_snapshot: str
    can_claim_itc_snapshot: bool
    description: Optional[str] = None
    place_of_supply_state_code: str
    taxable_amount: Decimal
    cgst_rate: Decimal
    sgst_rate: Decimal
    igst_rate: Decimal
    cgst_amount: Decimal
    sgst_amount: Decimal
    igst_amount: Decimal


class InvoiceBase(ORMModel):
    customer_id: Optional[UUID] = None
    issue_date: date
    due_date: Optional[date] = None
    status: str = "draft"
    subtotal: Decimal = Decimal("0")
    tax: Decimal = Decimal("0")
    total: Decimal = Decimal("0")
    currency: str = "INR"
    notes: Optional[str] = None


class InvoiceCreate(InvoiceBase):
    pass


class InvoiceUpdate(ORMModel):
    customer_id: Optional[UUID] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    status: Optional[str] = None
    subtotal: Optional[Decimal] = None
    tax: Optional[Decimal] = None
    total: Optional[Decimal] = None
    amount_paid: Optional[Decimal] = None
    currency: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class InvoiceRead(ORMModel):
    id: UUID
    invoice_number: str
    customer_id: Optional[UUID] = None
    issue_date: date
    due_date: Optional[date] = None
    status: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    amount_paid: Decimal
    currency: str
    notes: Optional[str] = None
    source_order_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    tax_lines: list[InvoiceTaxLineRead] = []


class PaymentBase(ORMModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=0)
    method: str = Field(default="bank", pattern="^(bank|cash|upi|cheque|card)$")
    paid_on: date
    bank_account_id: Optional[UUID] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentCreate(PaymentBase):
    pass


class PaymentUpdate(ORMModel):
    method: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class PaymentRead(ORMModel):
    id: UUID
    invoice_id: UUID
    journal_entry_id: Optional[UUID] = None
    bank_account_id: Optional[UUID] = None
    amount: Decimal
    method: str
    paid_on: date
    reference: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class VendorPaymentCreate(ORMModel):
    vendor_invoice_id: UUID
    amount: Decimal = Field(gt=0)
    method: str = Field(default="bank", pattern="^(bank|cash|upi|cheque)$")
    paid_on: date
    bank_account_id: Optional[UUID] = None
    reference: Optional[str] = None
    notes: Optional[str] = None


class VendorPaymentRead(ORMModel):
    id: UUID
    vendor_invoice_id: UUID
    journal_entry_id: Optional[UUID] = None
    bank_account_id: Optional[UUID] = None
    amount: Decimal
    method: str
    paid_on: date
    reference: Optional[str] = None
    notes: Optional[str] = None
    status: str
    created_at: datetime


class VendorPayableRead(ORMModel):
    invoice_id: UUID
    invoice_number: str
    vendor_id: UUID
    vendor_name: str
    issue_date: date
    due_date: Optional[date] = None
    total: Decimal
    paid_amount: Decimal
    outstanding: Decimal
    status: str


class VendorPayablesSummary(ORMModel):
    bill_count: int
    outstanding_total: Decimal


class GRNISummary(ORMModel):
    receipt_count: int
    outstanding_total: Decimal


class BankAccountBase(ORMModel):
    name: str
    bank_name: str
    account_number: str
    opening_balance: Decimal = Decimal("0")
    currency: str = "INR"
    ledger_account_id: Optional[UUID] = None


class BankAccountCreate(BankAccountBase):
    pass


class BankAccountUpdate(ORMModel):
    name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    opening_balance: Optional[Decimal] = None
    currency: Optional[str] = None
    ledger_account_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class BankAccountRead(ORMModel):
    id: UUID
    name: str
    bank_name: str
    account_number: str
    opening_balance: Decimal
    currency: str
    ledger_account_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime


class BankTransactionBase(ORMModel):
    bank_account_id: UUID
    txn_date: date
    amount: Decimal
    description: Optional[str] = None
    reference: Optional[str] = None


class BankTransactionCreate(BankTransactionBase):
    pass


class BankTransactionUpdate(ORMModel):
    description: Optional[str] = None
    reference: Optional[str] = None


class BankTransactionRead(ORMModel):
    id: UUID
    bank_account_id: UUID
    txn_date: date
    amount: Decimal
    description: Optional[str] = None
    reference: Optional[str] = None
    reconciled: bool
    matched_journal_line_id: Optional[UUID] = None
    created_at: datetime


class BankReconciliationSummary(ORMModel):
    imported_count: int
    matched_count: int
    reconciled_count: int
    unmatched_count: int
    statement_balance: Decimal
    ledger_balance: Decimal
    difference: Decimal


class BankMatchCandidate(ORMModel):
    journal_line_id: UUID
    journal_entry_id: UUID
    entry_number: str
    entry_date: date
    reference: Optional[str] = None
    memo: Optional[str] = None
    description: Optional[str] = None
    signed_amount: Decimal


class BankTransactionMatch(ORMModel):
    journal_line_id: UUID


class BankReconciliationUndo(ORMModel):
    reason: str = Field(min_length=3, max_length=500)


class TrialBalanceRow(ORMModel):
    account_id: UUID
    code: str
    name: str
    account_type: str
    debit: Decimal
    credit: Decimal
    balance: Decimal


class ReportSection(ORMModel):
    label: str
    amount: Decimal


class FinancialReport(ORMModel):
    total: Decimal
    sections: list[ReportSection]


class ReceivableRow(ORMModel):
    invoice_id: UUID
    invoice_number: str
    customer_id: Optional[UUID] = None
    issue_date: date
    due_date: Optional[date] = None
    total: Decimal
    amount_paid: Decimal
    outstanding: Decimal
    days_overdue: int


class AgingBucket(ORMModel):
    label: str
    total: Decimal
    count: int


class AgingReport(ORMModel):
    receivables: list[AgingBucket]
    payables: list[AgingBucket]


class AccountingExceptionSummary(ORMModel):
    draft_journals: int
    pending_approvals: int
    overdue_receivables: int
    overdue_payables: int
    unmatched_bank_transactions: int
    open_grni_receipts: int


class TallyImportResult(ORMModel):
    accounts_seen: int
    accounts_created: int
    accounts_updated: int
    opening_balance_posted: bool
    journal_entry_id: Optional[UUID] = None
    warnings: list[str] = []
