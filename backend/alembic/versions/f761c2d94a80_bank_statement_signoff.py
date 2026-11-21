"""add statement-level bank reconciliation sign-off

Revision ID: f761c2d94a80
Revises: e0b4d7a29c61
Create Date: 2026-11-19 19:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "f761c2d94a80"
down_revision: Union[str, None] = "e0b4d7a29c61"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_bank_statements",
        sa.Column("bank_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("statement_reference", sa.String(length=120), nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("opening_balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("closing_balance", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="open", nullable=False),
        sa.Column("signed_off_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("signed_off_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("signoff_reason", sa.String(length=500), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "period_start <= period_end",
            name="ck_finance_bank_statements_period",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'signed_off')",
            name="ck_finance_bank_statements_status",
        ),
        sa.ForeignKeyConstraint(
            ["bank_account_id"], ["finance_bank_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["signed_off_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "bank_account_id",
            "statement_reference",
            name="uq_finance_bank_statements_account_reference",
        ),
    )
    op.create_index(
        "ix_finance_bank_statements_bank_account_id",
        "finance_bank_statements",
        ["bank_account_id"],
    )
    op.create_index(
        "ix_finance_bank_statements_status",
        "finance_bank_statements",
        ["status"],
    )
    op.create_index(
        "ix_finance_bank_statements_tenant_id",
        "finance_bank_statements",
        ["tenant_id"],
    )
    op.create_index(
        "ix_finance_bank_statements_is_active",
        "finance_bank_statements",
        ["is_active"],
    )
    op.create_index(
        "ix_finance_bank_statements_created_by_id",
        "finance_bank_statements",
        ["created_by_id"],
    )
    op.add_column(
        "finance_bank_transactions",
        sa.Column("statement_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_bank_tx_statement_finance_bank_statements",
        "finance_bank_transactions",
        "finance_bank_statements",
        ["statement_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_finance_bank_transactions_statement_id",
        "finance_bank_transactions",
        ["statement_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_finance_bank_transactions_statement_id",
        table_name="finance_bank_transactions",
    )
    op.drop_constraint(
        "fk_bank_tx_statement_finance_bank_statements",
        "finance_bank_transactions",
        type_="foreignkey",
    )
    op.drop_column("finance_bank_transactions", "statement_id")
    op.drop_index(
        "ix_finance_bank_statements_created_by_id",
        table_name="finance_bank_statements",
    )
    op.drop_index(
        "ix_finance_bank_statements_is_active",
        table_name="finance_bank_statements",
    )
    op.drop_index(
        "ix_finance_bank_statements_tenant_id",
        table_name="finance_bank_statements",
    )
    op.drop_index(
        "ix_finance_bank_statements_status",
        table_name="finance_bank_statements",
    )
    op.drop_index(
        "ix_finance_bank_statements_bank_account_id",
        table_name="finance_bank_statements",
    )
    op.drop_table("finance_bank_statements")
