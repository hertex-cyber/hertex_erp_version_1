"""add period close sign-off controls

Revision ID: ee41c9d2a703
Revises: dc73a8f1042b
Create Date: 2026-11-18 08:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ee41c9d2a703"
down_revision: str | None = "dc73a8f1042b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("finance_periods", sa.Column("close_signed_by_id", sa.UUID(), nullable=True))
    op.add_column("finance_periods", sa.Column("close_signed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("finance_periods", sa.Column("close_signoff_reason", sa.String(length=500), nullable=True))
    op.create_foreign_key(
        "fk_finance_periods_close_signed_by_id",
        "finance_periods",
        "users",
        ["close_signed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_finance_periods_close_signed_by_id",
        "finance_periods",
        type_="foreignkey",
    )
    op.drop_column("finance_periods", "close_signoff_reason")
    op.drop_column("finance_periods", "close_signed_at")
    op.drop_column("finance_periods", "close_signed_by_id")
