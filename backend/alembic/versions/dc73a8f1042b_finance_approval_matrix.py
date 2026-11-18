"""add maker-checker approval workflow for finance transactions

Revision ID: dc73a8f1042b
Revises: a1c2d3e4f5b6
Create Date: 2026-11-18 03:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "dc73a8f1042b"
down_revision: str | None = "a1c2d3e4f5b6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "finance_vendor_payments",
        sa.Column("status", sa.String(length=30), server_default="posted", nullable=False),
    )
    op.create_index(
        "ix_finance_vendor_payments_status",
        "finance_vendor_payments",
        ["status"],
    )
    op.alter_column("finance_vendor_payments", "status", server_default=None)

    op.add_column(
        "inventory_stock_moves",
        sa.Column("status", sa.String(length=30), server_default="posted", nullable=False),
    )
    op.add_column(
        "inventory_stock_moves",
        sa.Column("movement_date", sa.Date(), nullable=True),
    )
    op.create_index(
        "ix_inventory_stock_moves_status",
        "inventory_stock_moves",
        ["status"],
    )
    op.alter_column("inventory_stock_moves", "status", server_default=None)

    op.create_table(
        "finance_approvals",
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("summary", sa.String(length=255), nullable=False),
        sa.Column("requested_by_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("decided_by_id", sa.UUID(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.String(length=500), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')",
            name="ck_finance_approvals_status",
        ),
        sa.CheckConstraint(
            "entity_type IN ('journal_entry', 'vendor_payment', 'inventory_adjustment')",
            name="ck_finance_approvals_entity_type",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["requested_by_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("finance_approvals", "status", server_default=None)
    op.create_index(
        "ix_finance_approvals_tenant_status",
        "finance_approvals",
        ["tenant_id", "status"],
    )
    op.create_index(
        "ix_finance_approvals_status",
        "finance_approvals",
        ["status"],
    )
    op.create_index(
        "ix_finance_approvals_tenant_id",
        "finance_approvals",
        ["tenant_id"],
    )
    op.create_index(
        "ix_finance_approvals_is_active",
        "finance_approvals",
        ["is_active"],
    )
    op.create_index(
        "uq_finance_approvals_pending_entity",
        "finance_approvals",
        ["tenant_id", "entity_type", "entity_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_finance_approvals_pending_entity", table_name="finance_approvals"
    )
    op.drop_index("ix_finance_approvals_is_active", table_name="finance_approvals")
    op.drop_index("ix_finance_approvals_tenant_id", table_name="finance_approvals")
    op.drop_index("ix_finance_approvals_status", table_name="finance_approvals")
    op.drop_index("ix_finance_approvals_tenant_status", table_name="finance_approvals")
    op.drop_table("finance_approvals")
    op.drop_index("ix_inventory_stock_moves_status", table_name="inventory_stock_moves")
    op.drop_column("inventory_stock_moves", "movement_date")
    op.drop_column("inventory_stock_moves", "status")
    op.drop_index("ix_finance_vendor_payments_status", table_name="finance_vendor_payments")
    op.drop_column("finance_vendor_payments", "status")
