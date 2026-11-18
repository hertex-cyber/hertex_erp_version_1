"""post and clear goods received not invoiced accruals

Revision ID: 74c81e2a5b90
Revises: d9e13df4e8b4
Create Date: 2026-11-18 00:48:00.000000

"""
from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "74c81e2a5b90"
down_revision: str | None = "d9e13df4e8b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "procurement_goods_receipts",
        sa.Column("journal_entry_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_procurement_goods_receipts_journal_entry_id",
        "procurement_goods_receipts",
        "finance_journal_entries",
        ["journal_entry_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_unique_constraint(
        "uq_procurement_goods_receipts_journal_entry_id",
        "procurement_goods_receipts",
        ["journal_entry_id"],
    )
    op.create_table(
        "finance_grn_accruals",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column("goods_receipt_id", sa.UUID(), nullable=False),
        sa.Column("journal_entry_id", sa.UUID(), nullable=False),
        sa.Column("cleared_by_invoice_id", sa.UUID(), nullable=True),
        sa.Column("accrued_amount", sa.Numeric(14, 2), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id"],
            ["procurement_goods_receipts.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["journal_entry_id"],
            ["finance_journal_entries.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["cleared_by_invoice_id"],
            ["procurement_vendor_invoices.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("goods_receipt_id", name="uq_finance_grn_accruals_receipt"),
        sa.UniqueConstraint("journal_entry_id", name="uq_finance_grn_accruals_journal_entry"),
    )
    op.create_index(
        "ix_finance_grn_accruals_goods_receipt_id",
        "finance_grn_accruals",
        ["goods_receipt_id"],
    )
    op.create_index(
        "ix_finance_grn_accruals_cleared_by_invoice_id",
        "finance_grn_accruals",
        ["cleared_by_invoice_id"],
    )
    op.create_index(
        "ix_finance_grn_accruals_tenant_id",
        "finance_grn_accruals",
        ["tenant_id"],
    )
    op.create_index(
        "ix_finance_grn_accruals_is_active",
        "finance_grn_accruals",
        ["is_active"],
    )
    connection = op.get_bind()
    tenant_ids = connection.execute(sa.text("SELECT id FROM tenants")).scalars().all()
    params = [
        {"account_id": str(uuid4()), "tenant_id": str(tenant_id)}
        for tenant_id in tenant_ids
    ]
    if params:
        connection.execute(
            sa.text(
                """
                INSERT INTO finance_accounts
                    (id, tenant_id, code, name, account_type, is_system, is_active)
                SELECT
                    CAST(:account_id AS uuid), CAST(:tenant_id AS uuid), '2100',
                    'Goods Received Not Invoiced', 'liability', TRUE, TRUE
                WHERE NOT EXISTS (
                    SELECT 1 FROM finance_accounts
                    WHERE finance_accounts.tenant_id = CAST(:tenant_id AS uuid)
                      AND finance_accounts.code = '2100'
                )
                """
            ),
            params,
        )


def downgrade() -> None:
    op.drop_index(
        "ix_finance_grn_accruals_is_active", table_name="finance_grn_accruals"
    )
    op.drop_index(
        "ix_finance_grn_accruals_tenant_id", table_name="finance_grn_accruals"
    )
    op.drop_index(
        "ix_finance_grn_accruals_cleared_by_invoice_id",
        table_name="finance_grn_accruals",
    )
    op.drop_index(
        "ix_finance_grn_accruals_goods_receipt_id",
        table_name="finance_grn_accruals",
    )
    op.drop_table("finance_grn_accruals")
    op.drop_constraint(
        "uq_procurement_goods_receipts_journal_entry_id",
        "procurement_goods_receipts",
        type_="unique",
    )
    op.drop_constraint(
        "fk_procurement_goods_receipts_journal_entry_id",
        "procurement_goods_receipts",
        type_="foreignkey",
    )
    op.drop_column("procurement_goods_receipts", "journal_entry_id")
