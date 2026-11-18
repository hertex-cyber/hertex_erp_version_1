"""link payment settlements to journals and bank ledgers

Revision ID: 67c2a1d9e40b
Revises: 48ab7c10e2f6
Create Date: 2026-11-18 00:22:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "67c2a1d9e40b"
down_revision: Union[str, None] = "48ab7c10e2f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "finance_bank_accounts",
        sa.Column("ledger_account_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_finance_bank_accounts_ledger_account_id",
        "finance_bank_accounts",
        "finance_accounts",
        ["ledger_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column(
        "finance_payments",
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "finance_payments",
        sa.Column("bank_account_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "finance_payments",
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
    )
    op.create_foreign_key(
        "fk_finance_payments_journal_entry_id",
        "finance_payments",
        "finance_journal_entries",
        ["journal_entry_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_finance_payments_bank_account_id",
        "finance_payments",
        "finance_bank_accounts",
        ["bank_account_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_finance_payments_bank_account_id",
        "finance_payments",
        ["bank_account_id"],
        unique=False,
    )
    op.create_unique_constraint(
        "uq_finance_payments_journal_entry_id",
        "finance_payments",
        ["journal_entry_id"],
    )
    op.create_unique_constraint(
        "uq_finance_payments_tenant_idempotency",
        "finance_payments",
        ["tenant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_finance_payments_tenant_idempotency",
        "finance_payments",
        type_="unique",
    )
    op.drop_constraint(
        "uq_finance_payments_journal_entry_id",
        "finance_payments",
        type_="unique",
    )
    op.drop_index("ix_finance_payments_bank_account_id", table_name="finance_payments")
    op.drop_constraint(
        "fk_finance_payments_bank_account_id",
        "finance_payments",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_finance_payments_journal_entry_id",
        "finance_payments",
        type_="foreignkey",
    )
    op.drop_column("finance_payments", "idempotency_key")
    op.drop_column("finance_payments", "bank_account_id")
    op.drop_column("finance_payments", "journal_entry_id")
    op.drop_constraint(
        "fk_finance_bank_accounts_ledger_account_id",
        "finance_bank_accounts",
        type_="foreignkey",
    )
    op.drop_column("finance_bank_accounts", "ledger_account_id")
