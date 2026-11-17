from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class AccountBase(ORMModel):
    code: str = Field(min_length=1, max_length=30)
    name: str = Field(min_length=1, max_length=200)
    account_type: str = Field(pattern="^(asset|liability|equity|income|expense)$")
    parent_id: Optional[UUID] = None
    description: Optional[str] = None


class AccountCreate(AccountBase):
    pass


class AccountUpdate(ORMModel):
    code: Optional[str] = None
    name: Optional[str] = None
    account_type: Optional[str] = None
    parent_id: Optional[UUID] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


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
    posted_at: Optional[datetime] = None
    created_at: datetime
    lines: list[JournalLineRead] = []


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


class PaymentBase(ORMModel):
    invoice_id: UUID
    amount: Decimal = Field(gt=0)
    method: str = "bank"
    paid_on: date
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
    amount: Decimal
    method: str
    paid_on: date
    reference: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime


class BankAccountBase(ORMModel):
    name: str
    bank_name: str
    account_number: str
    opening_balance: Decimal = Decimal("0")
    currency: str = "INR"


class BankAccountCreate(BankAccountBase):
    pass


class BankAccountUpdate(ORMModel):
    name: Optional[str] = None
    bank_name: Optional[str] = None
    account_number: Optional[str] = None
    opening_balance: Optional[Decimal] = None
    currency: Optional[str] = None
    is_active: Optional[bool] = None


class BankAccountRead(ORMModel):
    id: UUID
    name: str
    bank_name: str
    account_number: str
    opening_balance: Decimal
    currency: str
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
    reconciled: Optional[bool] = None
    description: Optional[str] = None
    reference: Optional[str] = None
    is_active: Optional[bool] = None


class BankTransactionRead(ORMModel):
    id: UUID
    bank_account_id: UUID
    txn_date: date
    amount: Decimal
    description: Optional[str] = None
    reference: Optional[str] = None
    reconciled: bool
    created_at: datetime


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


class TallyImportResult(ORMModel):
    accounts_seen: int
    accounts_created: int
    accounts_updated: int
    opening_balance_posted: bool
    journal_entry_id: Optional[UUID] = None
    warnings: list[str] = []
