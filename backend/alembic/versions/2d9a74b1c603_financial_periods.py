"""add finance periods and posting locks

Revision ID: 2d9a74b1c603
Revises: ece7476d64c5
Create Date: 2026-11-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2d9a74b1c603"
down_revision: Union[str, None] = "ece7476d64c5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_periods",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_by_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.CheckConstraint("start_date <= end_date", name="ck_finance_periods_date_order"),
        sa.CheckConstraint("status IN ('open', 'closed')", name="ck_finance_periods_status"),
        sa.ForeignKeyConstraint(["closed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_finance_periods_tenant_name"),
    )
    op.create_index(
        "ix_finance_periods_tenant_dates",
        "finance_periods",
        ["tenant_id", "start_date", "end_date"],
        unique=False,
    )
    op.create_index(
        op.f("ix_finance_periods_status"), "finance_periods", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_finance_periods_tenant_id"), "finance_periods", ["tenant_id"], unique=False
    )
    op.create_index(
        op.f("ix_finance_periods_is_active"), "finance_periods", ["is_active"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_finance_periods_is_active"), table_name="finance_periods")
    op.drop_index(op.f("ix_finance_periods_tenant_id"), table_name="finance_periods")
    op.drop_index(op.f("ix_finance_periods_status"), table_name="finance_periods")
    op.drop_index("ix_finance_periods_tenant_dates", table_name="finance_periods")
    op.drop_table("finance_periods")
