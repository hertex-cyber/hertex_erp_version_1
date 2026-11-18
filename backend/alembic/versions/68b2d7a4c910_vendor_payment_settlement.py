"""add vendor payment settlement and AP balance tracking

Revision ID: 68b2d7a4c910
Revises: 67c2a1d9e40b
Create Date: 2026-11-18 00:35:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "68b2d7a4c910"
down_revision: str | None = "67c2a1d9e40b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "procurement_vendor_invoices",
        sa.Column("paid_amount", sa.Numeric(14, 2), nullable=False, server_default="0"),
    )
    op.alter_column("procurement_vendor_invoices", "paid_amount", server_default=None)
    op.create_table(
        "finance_vendor_payments",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("vendor_invoice_id", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
        sa.Column("bank_account_id", sa.UUID(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=128), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("method", sa.String(length=40), nullable=False),
        sa.Column("paid_on", sa.Date(), nullable=False),
        sa.Column("reference", sa.String(length=120), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["bank_account_id"], ["finance_bank_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["journal_entry_id"], ["finance_journal_entries.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["vendor_invoice_id"], ["procurement_vendor_invoices.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journal_entry_id", name="uq_finance_vendor_payments_journal_entry_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_finance_vendor_payments_tenant_idempotency",
        ),
    )
    op.create_index(
        "ix_finance_vendor_payments_vendor_invoice_id",
        "finance_vendor_payments",
        ["vendor_invoice_id"],
    )
    op.create_index(
        "ix_finance_vendor_payments_bank_account_id",
        "finance_vendor_payments",
        ["bank_account_id"],
    )
    op.create_index(
        "ix_finance_vendor_payments_tenant_id",
        "finance_vendor_payments",
        ["tenant_id"],
    )
    op.create_index(
        "ix_finance_vendor_payments_is_active",
        "finance_vendor_payments",
        ["is_active"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_finance_vendor_payments_bank_account_id", table_name="finance_vendor_payments"
    )
    op.drop_index("ix_finance_vendor_payments_is_active", table_name="finance_vendor_payments")
    op.drop_index("ix_finance_vendor_payments_tenant_id", table_name="finance_vendor_payments")
    op.drop_index(
        "ix_finance_vendor_payments_vendor_invoice_id", table_name="finance_vendor_payments"
    )
    op.drop_table("finance_vendor_payments")
    op.drop_column("procurement_vendor_invoices", "paid_amount")
