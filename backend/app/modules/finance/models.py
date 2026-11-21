from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBaseModel


class Account(TenantBaseModel):
    __tablename__ = "finance_accounts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_finance_accounts_tenant_code"),
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="SET NULL"), nullable=True
    )
    group_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_account_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)


class AccountGroup(TenantBaseModel):
    __tablename__ = "finance_account_groups"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_finance_account_groups_tenant_code"),
        CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'income', 'expense')",
            name="ck_finance_account_groups_type",
        ),
        Index("ix_finance_account_groups_tenant_type", "tenant_id", "account_type"),
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    account_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    parent_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_account_groups.id", ondelete="SET NULL"),
        nullable=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class JournalEntry(TenantBaseModel):
    __tablename__ = "finance_journal_entries"
    __table_args__ = (
        UniqueConstraint(
            "reversal_of_id", name="uq_finance_journal_entries_reversal_of"
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_finance_journal_entries_tenant_idempotency",
        ),
        UniqueConstraint(
            "tenant_id",
            "entry_number",
            name="uq_finance_journal_entries_tenant_number",
        ),
        Index(
            "ix_finance_journal_entries_source_document",
            "tenant_id",
            "source_module",
            "source_document_type",
            "source_document_id",
        ),
    )

    entry_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    posted_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    reversal_of_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"), nullable=True
    )
    source_module: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    source_document_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    source_document_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    legal_entity_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )

    lines: Mapped[list["JournalLine"]] = relationship(
        back_populates="entry", lazy="selectin", cascade="all, delete-orphan"
    )


class FinanceApproval(TenantBaseModel):
    __tablename__ = "finance_approvals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_finance_approvals_status",
        ),
        CheckConstraint(
            "entity_type IN ('journal_entry', 'vendor_payment', 'inventory_adjustment')",
            name="ck_finance_approvals_entity_type",
        ),
        Index("ix_finance_approvals_tenant_status", "tenant_id", "status"),
        Index(
            "uq_finance_approvals_pending_entity",
            "tenant_id",
            "entity_type",
            "entity_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
            sqlite_where=text("status = 'pending'"),
        ),
    )

    entity_type: Mapped[str] = mapped_column(String(40), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    decided_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class JournalLine(TenantBaseModel):
    __tablename__ = "finance_journal_lines"

    journal_entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_journal_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )
    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    debit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    credit: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    branch_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    cost_center_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), nullable=True, index=True
    )
    department_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    project_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    tax_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    tax_rate: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), nullable=True)

    entry: Mapped[JournalEntry] = relationship(back_populates="lines")
    account: Mapped[Account] = relationship(lazy="selectin")


class FinancialPeriod(TenantBaseModel):
    __tablename__ = "finance_periods"
    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="ck_finance_periods_date_order"),
        CheckConstraint("status IN ('open', 'closed')", name="ck_finance_periods_status"),
        UniqueConstraint("tenant_id", "name", name="uq_finance_periods_tenant_name"),
        Index("ix_finance_periods_tenant_dates", "tenant_id", "start_date", "end_date"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    close_signed_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    close_signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    close_signoff_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class TaxRegistration(TenantBaseModel):
    __tablename__ = "finance_tax_registrations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "gstin", name="uq_finance_tax_registrations_tenant_gstin"),
        Index(
            "uq_finance_tax_registrations_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default IS TRUE"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    legal_name: Mapped[str] = mapped_column(String(200), nullable=False)
    gstin: Mapped[str] = mapped_column(String(15), nullable=False)
    state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class TaxCode(TenantBaseModel):
    __tablename__ = "finance_tax_codes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_finance_tax_codes_tenant_code"),
        CheckConstraint(
            "cgst_rate >= 0 AND sgst_rate >= 0 AND igst_rate >= 0",
            name="ck_finance_tax_codes_nonnegative_rates",
        ),
        CheckConstraint(
            "cgst_rate + sgst_rate = igst_rate",
            name="ck_finance_tax_codes_gst_rate_components",
        ),
        CheckConstraint(
            "tax_type IN ('taxable', 'exempt', 'zero_rated', 'non_gst')",
            name="ck_finance_tax_codes_tax_type",
        ),
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    tax_type: Mapped[str] = mapped_column(String(20), nullable=False, default="taxable")
    cgst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    sgst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    igst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0, nullable=False)
    can_claim_itc: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    output_cgst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    output_sgst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    output_igst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    input_cgst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    input_sgst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    input_igst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )


class Invoice(TenantBaseModel):
    __tablename__ = "finance_invoices"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "invoice_number",
            name="uq_finance_invoices_tenant_number",
        ),
    )

    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    customer_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    issue_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    amount_paid: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_order_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    tax_lines: Mapped[list["InvoiceTaxLine"]] = relationship(
        back_populates="invoice", lazy="selectin", cascade="all, delete-orphan"
    )


class InvoiceTaxLine(TenantBaseModel):
    __tablename__ = "finance_invoice_tax_lines"

    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tax_code_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_tax_codes.id", ondelete="RESTRICT"), nullable=False
    )
    registration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_tax_registrations.id", ondelete="RESTRICT"), nullable=False
    )
    tax_type_snapshot: Mapped[str] = mapped_column(String(20), nullable=False)
    can_claim_itc_snapshot: Mapped[bool] = mapped_column(Boolean, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    place_of_supply_state_code: Mapped[str] = mapped_column(String(2), nullable=False)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cgst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    sgst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    igst_rate: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    cgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    sgst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    igst_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    output_cgst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    output_sgst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    output_igst_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    invoice: Mapped[Invoice] = relationship(back_populates="tax_lines")


class Payment(TenantBaseModel):
    __tablename__ = "finance_payments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_finance_payments_tenant_idempotency"
        ),
    )

    invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_invoices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    journal_entry_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    bank_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_bank_accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(40), default="bank")
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class VendorPayment(TenantBaseModel):
    __tablename__ = "finance_vendor_payments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "idempotency_key", name="uq_finance_vendor_payments_tenant_idempotency"
        ),
    )

    vendor_invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("procurement_vendor_invoices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    journal_entry_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )
    bank_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_bank_accounts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    method: Mapped[str] = mapped_column(String(40), nullable=False)
    paid_on: Mapped[date] = mapped_column(Date, nullable=False)
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending_approval", nullable=False, index=True)


class GRNAccrual(TenantBaseModel):
    __tablename__ = "finance_grn_accruals"
    __table_args__ = (
        UniqueConstraint("goods_receipt_id", name="uq_finance_grn_accruals_receipt"),
    )

    goods_receipt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("procurement_goods_receipts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    journal_entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,
    )
    cleared_by_invoice_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("procurement_vendor_invoices.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    accrued_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    cleared_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0"), nullable=False
    )


class VendorInvoiceReceiptAllocation(TenantBaseModel):
    __tablename__ = "finance_vendor_invoice_receipt_allocations"
    __table_args__ = (
        UniqueConstraint(
            "vendor_invoice_id",
            "grn_accrual_id",
            name="uq_finance_invoice_receipt_allocations_invoice_accrual",
        ),
        CheckConstraint("allocated_amount > 0", name="ck_finance_invoice_receipt_allocations_amount"),
        Index(
            "ix_finance_invoice_receipt_allocations_accrual",
            "tenant_id",
            "grn_accrual_id",
        ),
    )

    vendor_invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("procurement_vendor_invoices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    grn_accrual_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_grn_accruals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    goods_receipt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("procurement_goods_receipts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    allocated_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    journal_line_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_journal_lines.id", ondelete="SET NULL"),
        nullable=True,
    )


class BankAccount(TenantBaseModel):
    __tablename__ = "finance_bank_accounts"

    name: Mapped[str] = mapped_column(String(150), nullable=False)
    bank_name: Mapped[str] = mapped_column(String(150), nullable=False)
    account_number: Mapped[str] = mapped_column(String(60), nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    ledger_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )


class BankReconciliationStatement(TenantBaseModel):
    __tablename__ = "finance_bank_statements"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "bank_account_id",
            "statement_reference",
            name="uq_finance_bank_statements_account_reference",
        ),
        CheckConstraint(
            "period_start <= period_end",
            name="ck_finance_bank_statements_period",
        ),
        CheckConstraint(
            "status IN ('open', 'signed_off')",
            name="ck_finance_bank_statements_status",
        ),
    )

    bank_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_bank_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    statement_reference: Mapped[str] = mapped_column(String(120), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    signed_off_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    signed_off_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    signoff_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)


class BankTransaction(TenantBaseModel):
    __tablename__ = "finance_bank_transactions"
    __table_args__ = (
        UniqueConstraint(
            "bank_account_id",
            "transaction_hash",
            name="uq_finance_bank_transactions_account_hash",
        ),
    )

    bank_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_bank_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    statement_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_bank_statements.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    txn_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reference: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    transaction_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    reconciled: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_journal_line_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_journal_lines.id", ondelete="SET NULL"), nullable=True
    )


class FixedAsset(TenantBaseModel):
    __tablename__ = "finance_fixed_assets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "asset_tag", name="uq_finance_fixed_assets_tenant_tag"),
        CheckConstraint("cost > 0", name="ck_finance_fixed_assets_positive_cost"),
        CheckConstraint("residual_value >= 0 AND residual_value <= cost", name="ck_finance_fixed_assets_residual"),
        CheckConstraint("useful_life_months > 0", name="ck_finance_fixed_assets_life"),
        CheckConstraint(
            "status IN ('draft', 'active', 'impaired', 'disposed', 'written_off')",
            name="ck_finance_fixed_assets_status",
        ),
    )

    asset_tag: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acquisition_date: Mapped[date] = mapped_column(Date, nullable=False)
    in_service_date: Mapped[date] = mapped_column(Date, nullable=False)
    cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    residual_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    useful_life_months: Mapped[int] = mapped_column(Integer, nullable=False)
    accumulated_depreciation: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    impairment_loss: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False, index=True)
    asset_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    accumulated_depreciation_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    depreciation_expense_account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=False
    )
    acquisition_credit_account_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_accounts.id", ondelete="RESTRICT"), nullable=True
    )
    acquisition_journal_entry_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    disposal_journal_entry_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"), nullable=True, unique=True
    )
    disposed_at: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class AssetDepreciation(TenantBaseModel):
    __tablename__ = "finance_asset_depreciations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "asset_id", "period_end", name="uq_finance_asset_depreciations_period"),
        CheckConstraint("amount > 0", name="ck_finance_asset_depreciations_positive_amount"),
    )

    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_fixed_assets.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    journal_entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"), nullable=False, unique=True
    )
