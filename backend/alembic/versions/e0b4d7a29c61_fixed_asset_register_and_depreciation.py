"""add fixed asset register and straight-line depreciation

Revision ID: e0b4d7a29c61
Revises: d2e6a1b8c4f0
Create Date: 2026-11-19 19:25:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "e0b4d7a29c61"
down_revision: Union[str, None] = "d2e6a1b8c4f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "finance_fixed_assets",
        sa.Column("asset_tag", sa.String(length=60), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("acquisition_date", sa.Date(), nullable=False),
        sa.Column("in_service_date", sa.Date(), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("residual_value", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("useful_life_months", sa.Integer(), nullable=False),
        sa.Column("accumulated_depreciation", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="draft", nullable=False),
        sa.Column("asset_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("accumulated_depreciation_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("depreciation_expense_account_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("acquisition_credit_account_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acquisition_journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("disposal_journal_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("disposed_at", sa.Date(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("cost > 0", name="ck_finance_fixed_assets_positive_cost"),
        sa.CheckConstraint(
            "residual_value >= 0 AND residual_value <= cost",
            name="ck_finance_fixed_assets_residual",
        ),
        sa.CheckConstraint("useful_life_months > 0", name="ck_finance_fixed_assets_life"),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'disposed')",
            name="ck_finance_fixed_assets_status",
        ),
        sa.ForeignKeyConstraint(["asset_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["accumulated_depreciation_account_id"],
            ["finance_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["depreciation_expense_account_id"],
            ["finance_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["acquisition_credit_account_id"],
            ["finance_accounts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["acquisition_journal_entry_id"],
            ["finance_journal_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["disposal_journal_entry_id"],
            ["finance_journal_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "asset_tag", name="uq_finance_fixed_assets_tenant_tag"),
        sa.UniqueConstraint("acquisition_journal_entry_id"),
        sa.UniqueConstraint("disposal_journal_entry_id"),
    )
    op.create_index("ix_finance_fixed_assets_tenant_id", "finance_fixed_assets", ["tenant_id"])
    op.create_index("ix_finance_fixed_assets_is_active", "finance_fixed_assets", ["is_active"])
    op.create_index("ix_finance_fixed_assets_created_by_id", "finance_fixed_assets", ["created_by_id"])
    op.create_index("ix_finance_fixed_assets_status", "finance_fixed_assets", ["status"])

    op.create_table(
        "finance_asset_depreciations",
        sa.Column("asset_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("journal_entry_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("amount > 0", name="ck_finance_asset_depreciations_positive_amount"),
        sa.ForeignKeyConstraint(["asset_id"], ["finance_fixed_assets.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["finance_journal_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "asset_id", "period_end", name="uq_finance_asset_depreciations_period"),
        sa.UniqueConstraint("journal_entry_id"),
    )
    op.create_index(
        "ix_finance_asset_depreciations_asset_id",
        "finance_asset_depreciations",
        ["asset_id"],
    )
    op.create_index(
        "ix_finance_asset_depreciations_tenant_id",
        "finance_asset_depreciations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_finance_asset_depreciations_is_active",
        "finance_asset_depreciations",
        ["is_active"],
    )
    op.create_index(
        "ix_finance_asset_depreciations_created_by_id",
        "finance_asset_depreciations",
        ["created_by_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_finance_asset_depreciations_created_by_id", table_name="finance_asset_depreciations")
    op.drop_index("ix_finance_asset_depreciations_is_active", table_name="finance_asset_depreciations")
    op.drop_index("ix_finance_asset_depreciations_tenant_id", table_name="finance_asset_depreciations")
    op.drop_index("ix_finance_asset_depreciations_asset_id", table_name="finance_asset_depreciations")
    op.drop_table("finance_asset_depreciations")
    op.drop_index("ix_finance_fixed_assets_status", table_name="finance_fixed_assets")
    op.drop_index("ix_finance_fixed_assets_created_by_id", table_name="finance_fixed_assets")
    op.drop_index("ix_finance_fixed_assets_is_active", table_name="finance_fixed_assets")
    op.drop_index("ix_finance_fixed_assets_tenant_id", table_name="finance_fixed_assets")
    op.drop_table("finance_fixed_assets")
