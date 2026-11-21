"""Finance control-plane models: audit, outbox, integrations, statutory filings and dimensions."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantBaseModel


class FinanceAuditLog(TenantBaseModel):
    __tablename__ = "finance_audit_log"
    __table_args__ = (
        Index("ix_finance_audit_log_entity", "tenant_id", "entity_type", "entity_id"),
        Index("ix_finance_audit_log_actor", "tenant_id", "actor_id"),
        Index("ix_finance_audit_log_correlation", "correlation_id"),
    )

    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(60), nullable=False)
    source_module: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    actor_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    actor_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    actor_role: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    before_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    after_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    approval_context_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class SourceEvent(TenantBaseModel):
    __tablename__ = "finance_source_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "event_type", "idempotency_key", name="uq_finance_source_events_dedupe"
        ),
        Index("ix_finance_source_events_status", "tenant_id", "status"),
    )

    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    source_module: Mapped[str] = mapped_column(String(40), nullable=False)
    source_document_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    source_document_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(180), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="received", nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    result_reference: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class OutboxEvent(TenantBaseModel):
    __tablename__ = "finance_outbox_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "event_type", "aggregate_id", name="uq_finance_outbox_event_aggregate"
        ),
        Index("ix_finance_outbox_events_dispatch", "status", "next_attempt_at"),
    )

    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(60), nullable=False)
    aggregate_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class WebhookEndpoint(TenantBaseModel):
    __tablename__ = "finance_webhook_endpoints"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_finance_webhook_endpoints_tenant_name"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    event_types: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class WebhookDelivery(TenantBaseModel):
    __tablename__ = "finance_webhook_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "endpoint_id", "outbox_event_id", name="uq_finance_webhook_deliveries_unique"
        ),
        Index("ix_finance_webhook_deliveries_status", "status", "created_at"),
    )

    endpoint_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    outbox_event_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    response_status: Mapped[Optional[int]] = mapped_column(nullable=True)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class BankFeed(TenantBaseModel):
    __tablename__ = "finance_bank_feeds"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_finance_bank_feeds_tenant_name"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="csv", nullable=False)
    bank_account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    webhook_secret: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_imported_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class BankFeedImport(TenantBaseModel):
    __tablename__ = "finance_bank_feed_imports"
    __table_args__ = (
        UniqueConstraint("tenant_id", "feed_id", "file_hash", name="uq_finance_bank_feed_imports_hash"),
    )

    feed_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_name: Mapped[Optional[str]] = mapped_column(String(180), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="completed", nullable=False)
    row_count: Mapped[int] = mapped_column(default=0, nullable=False)
    imported_count: Mapped[int] = mapped_column(default=0, nullable=False)
    duplicate_count: Mapped[int] = mapped_column(default=0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class GstReturn(TenantBaseModel):
    __tablename__ = "finance_gst_returns"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "registration_id", "return_type", "filing_period",
            name="uq_finance_gst_returns_period",
        ),
        CheckConstraint("return_type IN ('GSTR1', 'GSTR3B')", name="ck_finance_gst_returns_type"),
        CheckConstraint(
            "status IN ('draft', 'filed', 'acknowledged')", name="ck_finance_gst_returns_status"
        ),
        Index("ix_finance_gst_returns_period", "tenant_id", "filing_period"),
    )

    registration_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    return_type: Mapped[str] = mapped_column(String(20), nullable=False)
    filing_period: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    filed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    filed_by_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    acknowledgement_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)


class EInvoice(TenantBaseModel):
    __tablename__ = "finance_e_invoices"
    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_id", name="uq_finance_e_invoices_invoice"),
        UniqueConstraint("tenant_id", "irn", name="uq_finance_e_invoices_irn"),
        CheckConstraint(
            "status IN ('draft', 'generated', 'cancelled', 'failed')",
            name="ck_finance_e_invoices_status",
        ),
    )

    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    irn: Mapped[str] = mapped_column(String(100), nullable=False)
    qr_payload: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acknowledgement_number: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    acknowledgement_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class EWaybill(TenantBaseModel):
    __tablename__ = "finance_e_waybills"
    __table_args__ = (
        UniqueConstraint("tenant_id", "waybill_number", name="uq_finance_e_waybills_number"),
    )

    invoice_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    waybill_number: Mapped[str] = mapped_column(String(40), nullable=False)
    transport_mode: Mapped[str] = mapped_column(String(20), default="road", nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class GstItcMatch(TenantBaseModel):
    __tablename__ = "finance_gst_itc_matches"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "filing_period", "source_document_id", "tax_code_id",
            name="uq_finance_gst_itc_match_key",
        ),
        Index("ix_finance_gst_itc_matches_period", "tenant_id", "filing_period"),
    )

    filing_period: Mapped[str] = mapped_column(String(7), nullable=False)
    registration_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    source_document_type: Mapped[str] = mapped_column(String(60), nullable=False)
    source_document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    tax_code_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    taxable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    invoice_tax: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    posted_itc: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    difference: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="matched", nullable=False)


class LegalEntity(TenantBaseModel):
    __tablename__ = "finance_legal_entities"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_finance_legal_entities_tenant_code"),
        Index(
            "uq_finance_legal_entities_default",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default IS TRUE"),
            sqlite_where=text("is_default = 1"),
        ),
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Branch(TenantBaseModel):
    __tablename__ = "finance_branches"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_finance_branches_tenant_code"),
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    legal_entity_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)


class CostCenter(TenantBaseModel):
    __tablename__ = "finance_cost_centers"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_finance_cost_centers_tenant_code"),
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    parent_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)


class FinanceDepartment(TenantBaseModel):
    __tablename__ = "finance_departments"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_finance_departments_tenant_code"),
    )

    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)


class IntercompanyTransaction(TenantBaseModel):
    __tablename__ = "finance_intercompany_transactions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'posted', 'eliminated', 'cancelled')",
            name="ck_finance_intercompany_status",
        ),
        Index("ix_finance_intercompany_period", "tenant_id", "transaction_date"),
    )

    number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    from_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    to_entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR", nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    journal_entry_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    elimination_journal_entry_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), nullable=True
    )


class Budget(TenantBaseModel):
    __tablename__ = "finance_budgets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_finance_budgets_tenant_name"),
        CheckConstraint("start_date <= end_date", name="ck_finance_budgets_dates"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    branch_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    cost_center_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)


class BudgetLine(TenantBaseModel):
    __tablename__ = "finance_budget_lines"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "budget_id", "account_id", "period", name="uq_finance_budget_lines_key"
        ),
    )

    budget_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    period: Mapped[str] = mapped_column(String(7), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)


class LedgerBalance(TenantBaseModel):
    __tablename__ = "finance_ledger_balances"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "account_id", "period_id", name="uq_finance_ledger_balances_key"
        ),
    )

    account_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    period_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    opening_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    debit_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    credit_total: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
    closing_balance: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0, nullable=False)
