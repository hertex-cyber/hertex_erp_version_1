"""link stock adjustments to their posted accounting entry

Revision ID: a6c82d1f409b
Revises: f2a39b18c7d4
Create Date: 2026-11-18 01:45:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a6c82d1f409b"
down_revision: str | None = "f2a39b18c7d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "inventory_stock_moves",
        sa.Column("idempotency_key", sa.String(length=120), nullable=True),
    )
    op.add_column(
        "inventory_stock_moves",
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_stock_moves_journal_entry_id",
        "inventory_stock_moves",
        "finance_journal_entries",
        ["journal_entry_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_inventory_stock_moves_idempotency",
        "inventory_stock_moves",
        ["tenant_id", "idempotency_key"],
    )
    op.create_unique_constraint(
        "uq_inventory_stock_moves_journal_entry",
        "inventory_stock_moves",
        ["journal_entry_id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_inventory_stock_moves_journal_entry",
        "inventory_stock_moves",
        type_="unique",
    )
    op.drop_constraint(
        "uq_inventory_stock_moves_idempotency",
        "inventory_stock_moves",
        type_="unique",
    )
    op.drop_constraint(
        "fk_inventory_stock_moves_journal_entry_id",
        "inventory_stock_moves",
        type_="foreignkey",
    )
    op.drop_column("inventory_stock_moves", "journal_entry_id")
    op.drop_column("inventory_stock_moves", "idempotency_key")
