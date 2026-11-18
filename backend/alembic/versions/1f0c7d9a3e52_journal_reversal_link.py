"""link journal reversal entries

Revision ID: 1f0c7d9a3e52
Revises: 2d9a74b1c603
Create Date: 2026-11-18 00:11:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1f0c7d9a3e52"
down_revision: Union[str, None] = "2d9a74b1c603"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "finance_journal_entries",
        sa.Column("reversal_of_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_finance_journal_entries_reversal_of_id",
        "finance_journal_entries",
        "finance_journal_entries",
        ["reversal_of_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_finance_journal_entries_reversal_of",
        "finance_journal_entries",
        ["reversal_of_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_finance_journal_entries_reversal_of",
        "finance_journal_entries",
        type_="unique",
    )
    op.drop_constraint(
        "fk_finance_journal_entries_reversal_of_id",
        "finance_journal_entries",
        type_="foreignkey",
    )
    op.drop_column("finance_journal_entries", "reversal_of_id")
