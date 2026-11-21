"""finance control plane: audit, outbox, integration, statutory and dimension tables

Revision ID: 9b7e3c21f0a4
Revises: f761c2d94a80
Create Date: 2026-11-20 10:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "9b7e3c21f0a4"
down_revision: str | None = "f761c2d94a80"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def _common(table: str, *, created_by: bool = True, foreign_user: bool = False) -> list[sa.Column]:
    columns = [
        sa.Column("id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
    ]
    if created_by:
        columns.append(sa.Column("created_by_id", UUID, nullable=True))
    columns.extend(
        [
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        ]
    )
    return columns


def _common_constraints(table: str, *, created_by: bool = True, foreign_user: bool = False) -> list:
    constraints = [
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
    ]
    if created_by:
        constraints.append(
            sa.ForeignKeyConstraint(
                ["created_by_id"], ["users.id"], ondelete="SET NULL" if not foreign_user else "RESTRICT"
            )
        )
    return constraints


def _common_indexes(table: str, *, created_by: bool = True) -> None:
    op.create_index(f"ix_{table}_tenant_id", table, ["tenant_id"])
    op.create_index(f"ix_{table}_is_active", table, ["is_active"])
    if created_by:
        op.create_index(f"ix_{table}_created_by_id", table, ["created_by_id"])


def _create_common_table(
    name: str, columns: list[sa.Column], constraints: list, *, created_by: bool = True
) -> None:
    op.create_table(
        name,
        *columns,
        *_common(name, created_by=created_by),
        *_common_constraints(name, created_by=created_by),
        *constraints,
    )
    _common_indexes(name, created_by=created_by)


def upgrade() -> None:
    op.add_column("finance_fixed_assets", sa.Column("impairment_loss", sa.Numeric(14, 2), server_default="0", nullable=False))
    op.drop_constraint("ck_finance_fixed_assets_status", "finance_fixed_assets", type_="check")
    op.create_check_constraint(
        "ck_finance_fixed_assets_status",
        "finance_fixed_assets",
        "status IN ('draft', 'active', 'impaired', 'disposed', 'written_off')",
    )

    op.add_column("finance_journal_entries", sa.Column("legal_entity_id", UUID, nullable=True))
    op.create_index("ix_finance_journal_entries_legal_entity_id", "finance_journal_entries", ["legal_entity_id"])

    for column in ("branch_id", "cost_center_id", "department_id", "project_id"):
        op.add_column("finance_journal_lines", sa.Column(column, UUID, nullable=True))
        op.create_index(f"ix_finance_journal_lines_{column}", "finance_journal_lines", [column])
    op.add_column("finance_journal_lines", sa.Column("tax_code", sa.String(length=30), nullable=True))
    op.add_column("finance_journal_lines", sa.Column("tax_rate", sa.Numeric(5, 2), nullable=True))

    _create_common_table(
        "finance_audit_log",
        [
            sa.Column("entity_type", sa.String(length=60), nullable=False),
            sa.Column("entity_id", UUID, nullable=True),
            sa.Column("action", sa.String(length=60), nullable=False),
            sa.Column("source_module", sa.String(length=40), nullable=True),
            sa.Column("actor_id", UUID, nullable=True),
            sa.Column("actor_email", sa.String(length=255), nullable=True),
            sa.Column("actor_role", sa.String(length=120), nullable=True),
            sa.Column("before_state", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("after_state", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("reason", sa.Text(), nullable=True),
            sa.Column("correlation_id", sa.String(length=120), nullable=True),
            sa.Column("ip_address", sa.String(length=64), nullable=True),
            sa.Column("approval_context_id", UUID, nullable=True),
        ],
        [
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["approval_context_id"], ["finance_approvals.id"], ondelete="SET NULL"),
        ],
    )
    for name, cols in (
        ("ix_finance_audit_log_entity", ["tenant_id", "entity_type", "entity_id"]),
        ("ix_finance_audit_log_actor", ["tenant_id", "actor_id"]),
        ("ix_finance_audit_log_correlation", ["correlation_id"]),
    ):
        op.create_index(name, "finance_audit_log", cols)

    _create_common_table(
        "finance_source_events",
        [
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("source_module", sa.String(length=40), nullable=False),
            sa.Column("source_document_type", sa.String(length=60), nullable=True),
            sa.Column("source_document_id", UUID, nullable=True),
            sa.Column("idempotency_key", sa.String(length=180), nullable=False),
            sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("status", sa.String(length=20), server_default="received", nullable=False),
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("result_reference", sa.String(length=180), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        ],
        [
            sa.UniqueConstraint("tenant_id", "event_type", "idempotency_key", name="uq_finance_source_events_dedupe"),
        ],
    )
    op.create_index("ix_finance_source_events_status", "finance_source_events", ["tenant_id", "status"])

    _create_common_table(
        "finance_outbox_events",
        [
            sa.Column("event_type", sa.String(length=80), nullable=False),
            sa.Column("aggregate_type", sa.String(length=60), nullable=False),
            sa.Column("aggregate_id", UUID, nullable=False),
            sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
        ],
        [
            sa.UniqueConstraint("tenant_id", "event_type", "aggregate_id", name="uq_finance_outbox_event_aggregate"),
        ],
    )
    op.create_index("ix_finance_outbox_events_dispatch", "finance_outbox_events", ["status", "next_attempt_at"])

    _create_common_table(
        "finance_webhook_endpoints",
        [
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("secret", sa.String(length=128), nullable=False),
            sa.Column("event_types", sa.JSON(), server_default="[]", nullable=False),
            sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
        ],
        [sa.UniqueConstraint("tenant_id", "name", name="uq_finance_webhook_endpoints_tenant_name")],
    )

    _create_common_table(
        "finance_webhook_deliveries",
        [
            sa.Column("endpoint_id", UUID, nullable=False),
            sa.Column("outbox_event_id", UUID, nullable=False),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("response_status", sa.Integer(), nullable=True),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        ],
        [
            sa.ForeignKeyConstraint(["endpoint_id"], ["finance_webhook_endpoints.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["outbox_event_id"], ["finance_outbox_events.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("endpoint_id", "outbox_event_id", name="uq_finance_webhook_deliveries_unique"),
        ],
    )
    op.create_index("ix_finance_webhook_deliveries_status", "finance_webhook_deliveries", ["status", "created_at"])

    _create_common_table(
        "finance_bank_feeds",
        [
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("provider", sa.String(length=30), server_default="csv", nullable=False),
            sa.Column("bank_account_id", UUID, nullable=False),
            sa.Column("config", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("webhook_secret", sa.String(length=128), nullable=True),
            sa.Column("is_enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("last_imported_at", sa.DateTime(timezone=True), nullable=True),
        ],
        [
            sa.ForeignKeyConstraint(["bank_account_id"], ["finance_bank_accounts.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("tenant_id", "name", name="uq_finance_bank_feeds_tenant_name"),
        ],
    )
    op.create_index("ix_finance_bank_feeds_bank_account_id", "finance_bank_feeds", ["bank_account_id"])

    _create_common_table(
        "finance_bank_feed_imports",
        [
            sa.Column("feed_id", UUID, nullable=False),
            sa.Column("file_hash", sa.String(length=64), nullable=False),
            sa.Column("file_name", sa.String(length=180), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="completed", nullable=False),
            sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("imported_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("duplicate_count", sa.Integer(), server_default="0", nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
        ],
        [
            sa.ForeignKeyConstraint(["feed_id"], ["finance_bank_feeds.id"], ondelete="CASCADE"),
            sa.UniqueConstraint("tenant_id", "feed_id", "file_hash", name="uq_finance_bank_feed_imports_hash"),
        ],
    )
    op.create_index("ix_finance_bank_feed_imports_feed_id", "finance_bank_feed_imports", ["feed_id"])

    _create_common_table(
        "finance_gst_returns",
        [
            sa.Column("registration_id", UUID, nullable=False),
            sa.Column("return_type", sa.String(length=20), nullable=False),
            sa.Column("filing_period", sa.String(length=7), nullable=False),
            sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
            sa.Column("summary", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("filed_by_id", UUID, nullable=True),
            sa.Column("acknowledgement_number", sa.String(length=60), nullable=True),
        ],
        [
            sa.UniqueConstraint(
                "tenant_id", "registration_id", "return_type", "filing_period",
                name="uq_finance_gst_returns_period",
            ),
            sa.CheckConstraint("return_type IN ('GSTR1', 'GSTR3B')", name="ck_finance_gst_returns_type"),
            sa.CheckConstraint(
                "status IN ('draft', 'filed', 'acknowledged')", name="ck_finance_gst_returns_status"
            ),
        ],
    )
    op.create_index("ix_finance_gst_returns_period", "finance_gst_returns", ["tenant_id", "filing_period"])

    _create_common_table(
        "finance_e_invoices",
        [
            sa.Column("invoice_id", UUID, nullable=False),
            sa.Column("irn", sa.String(length=100), nullable=False),
            sa.Column("qr_payload", sa.Text(), nullable=True),
            sa.Column("acknowledgement_number", sa.String(length=60), nullable=True),
            sa.Column("acknowledgement_date", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
            sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("cancellation_reason", sa.Text(), nullable=True),
        ],
        [
            sa.ForeignKeyConstraint(["invoice_id"], ["finance_invoices.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("tenant_id", "invoice_id", name="uq_finance_e_invoices_invoice"),
            sa.UniqueConstraint("tenant_id", "irn", name="uq_finance_e_invoices_irn"),
            sa.CheckConstraint(
                "status IN ('draft', 'generated', 'cancelled', 'failed')",
                name="ck_finance_e_invoices_status",
            ),
        ],
    )
    op.create_index("ix_finance_e_invoices_invoice_id", "finance_e_invoices", ["invoice_id"])

    _create_common_table(
        "finance_e_waybills",
        [
            sa.Column("invoice_id", UUID, nullable=False),
            sa.Column("waybill_number", sa.String(length=40), nullable=False),
            sa.Column("transport_mode", sa.String(length=20), server_default="road", nullable=False),
            sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="active", nullable=False),
            sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        ],
        [
            sa.ForeignKeyConstraint(["invoice_id"], ["finance_invoices.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint("tenant_id", "waybill_number", name="uq_finance_e_waybills_number"),
        ],
    )
    op.create_index("ix_finance_e_waybills_invoice_id", "finance_e_waybills", ["invoice_id"])

    _create_common_table(
        "finance_gst_itc_matches",
        [
            sa.Column("filing_period", sa.String(length=7), nullable=False),
            sa.Column("registration_id", UUID, nullable=True),
            sa.Column("source_document_type", sa.String(length=60), nullable=False),
            sa.Column("source_document_id", UUID, nullable=False),
            sa.Column("tax_code_id", UUID, nullable=True),
            sa.Column("taxable_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
            sa.Column("invoice_tax", sa.Numeric(14, 2), server_default="0", nullable=False),
            sa.Column("posted_itc", sa.Numeric(14, 2), server_default="0", nullable=False),
            sa.Column("difference", sa.Numeric(14, 2), server_default="0", nullable=False),
            sa.Column("status", sa.String(length=20), server_default="matched", nullable=False),
        ],
        [
            sa.UniqueConstraint(
                "tenant_id", "filing_period", "source_document_id", "tax_code_id",
                name="uq_finance_gst_itc_match_key",
            ),
        ],
    )
    for name, cols in (
        ("ix_finance_gst_itc_matches_filing_period", ["tenant_id", "filing_period"]),
    ):
        op.create_index(name, "finance_gst_itc_matches", cols)

    _create_common_table(
        "finance_legal_entities",
        [
            sa.Column("code", sa.String(length=30), nullable=False),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("gstin", sa.String(length=15), nullable=True),
            sa.Column("currency", sa.String(length=10), server_default="INR", nullable=False),
            sa.Column("is_default", sa.Boolean(), server_default=sa.false(), nullable=False),
        ],
        [
            sa.UniqueConstraint("tenant_id", "code", name="uq_finance_legal_entities_tenant_code"),
        ],
    )
    op.create_index(
        "uq_finance_legal_entities_default",
        "finance_legal_entities",
        ["tenant_id"],
        unique=True,
        postgresql_where="is_default IS TRUE",
        sqlite_where="is_default = 1",
    )

    _create_common_table(
        "finance_branches",
        [
            sa.Column("code", sa.String(length=30), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("legal_entity_id", UUID, nullable=True),
            sa.Column("gstin", sa.String(length=15), nullable=True),
        ],
        [sa.UniqueConstraint("tenant_id", "code", name="uq_finance_branches_tenant_code")],
    )

    _create_common_table(
        "finance_cost_centers",
        [
            sa.Column("code", sa.String(length=30), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
            sa.Column("parent_id", UUID, nullable=True),
        ],
        [sa.UniqueConstraint("tenant_id", "code", name="uq_finance_cost_centers_tenant_code")],
    )

    _create_common_table(
        "finance_departments",
        [
            sa.Column("code", sa.String(length=30), nullable=False),
            sa.Column("name", sa.String(length=150), nullable=False),
        ],
        [sa.UniqueConstraint("tenant_id", "code", name="uq_finance_departments_tenant_code")],
    )

    _create_common_table(
        "finance_intercompany_transactions",
        [
            sa.Column("number", sa.String(length=50), nullable=False),
            sa.Column("from_entity_id", UUID, nullable=False),
            sa.Column("to_entity_id", UUID, nullable=False),
            sa.Column("transaction_date", sa.Date(), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
            sa.Column("currency", sa.String(length=10), server_default="INR", nullable=False),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
            sa.Column("journal_entry_id", UUID, nullable=True),
            sa.Column("elimination_journal_entry_id", UUID, nullable=True),
        ],
        [
            sa.CheckConstraint(
                "status IN ('draft', 'posted', 'eliminated', 'cancelled')",
                name="ck_finance_intercompany_status",
            ),
        ],
    )
    op.create_index(
        "ix_finance_intercompany_period",
        "finance_intercompany_transactions",
        ["tenant_id", "transaction_date"],
    )
    op.create_index("ix_finance_intercompany_transactions_number", "finance_intercompany_transactions", ["number"])

    _create_common_table(
        "finance_budgets",
        [
            sa.Column("name", sa.String(length=120), nullable=False),
            sa.Column("start_date", sa.Date(), nullable=False),
            sa.Column("end_date", sa.Date(), nullable=False),
            sa.Column("branch_id", UUID, nullable=True),
            sa.Column("cost_center_id", UUID, nullable=True),
            sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        ],
        [
            sa.UniqueConstraint("tenant_id", "name", name="uq_finance_budgets_tenant_name"),
            sa.CheckConstraint("start_date <= end_date", name="ck_finance_budgets_dates"),
        ],
    )

    _create_common_table(
        "finance_budget_lines",
        [
            sa.Column("budget_id", UUID, nullable=False),
            sa.Column("account_id", UUID, nullable=False),
            sa.Column("period", sa.String(length=7), nullable=False),
            sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        ],
        [
            sa.ForeignKeyConstraint(["budget_id"], ["finance_budgets.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["account_id"], ["finance_accounts.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint(
                "tenant_id", "budget_id", "account_id", "period", name="uq_finance_budget_lines_key"
            ),
        ],
    )
    op.create_index("ix_finance_budget_lines_budget_id", "finance_budget_lines", ["budget_id"])
    op.create_index("ix_finance_budget_lines_account_id", "finance_budget_lines", ["account_id"])

    _create_common_table(
        "finance_ledger_balances",
        [
            sa.Column("account_id", UUID, nullable=False),
            sa.Column("period_id", UUID, nullable=True),
            sa.Column("opening_balance", sa.Numeric(14, 2), server_default="0", nullable=False),
            sa.Column("debit_total", sa.Numeric(14, 2), server_default="0", nullable=False),
            sa.Column("credit_total", sa.Numeric(14, 2), server_default="0", nullable=False),
            sa.Column("closing_balance", sa.Numeric(14, 2), server_default="0", nullable=False),
        ],
        [
            sa.ForeignKeyConstraint(["account_id"], ["finance_accounts.id"], ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["period_id"], ["finance_periods.id"], ondelete="RESTRICT"),
            sa.UniqueConstraint(
                "tenant_id", "account_id", "period_id", name="uq_finance_ledger_balances_key"
            ),
        ],
    )
    op.create_index("ix_finance_ledger_balances_account_id", "finance_ledger_balances", ["account_id"])
    op.create_index("ix_finance_ledger_balances_period_id", "finance_ledger_balances", ["period_id"])


def downgrade() -> None:
    for table in (
        "finance_ledger_balances",
        "finance_budget_lines",
        "finance_budgets",
        "finance_intercompany_transactions",
        "finance_departments",
        "finance_cost_centers",
        "finance_branches",
        "finance_legal_entities",
        "finance_gst_itc_matches",
        "finance_e_waybills",
        "finance_e_invoices",
        "finance_gst_returns",
        "finance_bank_feed_imports",
        "finance_bank_feeds",
        "finance_webhook_deliveries",
        "finance_webhook_endpoints",
        "finance_outbox_events",
        "finance_source_events",
        "finance_audit_log",
    ):
        op.drop_table(table)

    op.drop_column("finance_journal_lines", "tax_rate")
    op.drop_column("finance_journal_lines", "tax_code")
    for column in ("project_id", "department_id", "cost_center_id", "branch_id"):
        op.drop_index(f"ix_finance_journal_lines_{column}", table_name="finance_journal_lines")
        op.drop_column("finance_journal_lines", column)
    op.drop_index("ix_finance_journal_entries_legal_entity_id", table_name="finance_journal_entries")
    op.drop_column("finance_journal_entries", "legal_entity_id")

    op.drop_constraint("ck_finance_fixed_assets_status", "finance_fixed_assets", type_="check")
    op.create_check_constraint(
        "ck_finance_fixed_assets_status",
        "finance_fixed_assets",
        "status IN ('draft', 'active', 'disposed')",
    )
    op.drop_column("finance_fixed_assets", "impairment_loss")
