"""add bank statement deduplication for reconciliation

Revision ID: 91d6f20a7c43
Revises: 74c81e2a5b90
Create Date: 2026-11-18 00:57:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "91d6f20a7c43"
down_revision: str | None = "74c81e2a5b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "finance_bank_transactions",
        sa.Column("transaction_hash", sa.String(length=64), nullable=True),
    )
    op.create_unique_constraint(
        "uq_finance_bank_transactions_account_hash",
        "finance_bank_transactions",
        ["bank_account_id", "transaction_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_finance_bank_transactions_account_hash",
        "finance_bank_transactions",
        type_="unique",
    )
    op.drop_column("finance_bank_transactions", "transaction_hash")
