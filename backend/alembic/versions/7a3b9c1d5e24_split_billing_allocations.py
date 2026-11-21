from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7a3b9c1d5e24"
down_revision: str | None = "6f2a9d4c8b13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column(
        "finance_grn_accruals",
        sa.Column("cleared_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
    )
    op.execute(
        "UPDATE finance_grn_accruals SET cleared_amount = accrued_amount "
        "WHERE cleared_by_invoice_id IS NOT NULL"
    )
    op.create_table(
        "finance_vendor_invoice_receipt_allocations",
        sa.Column("id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("vendor_invoice_id", UUID, nullable=False),
        sa.Column("grn_accrual_id", UUID, nullable=False),
        sa.Column("goods_receipt_id", UUID, nullable=False),
        sa.Column("allocated_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("journal_line_id", UUID, nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["vendor_invoice_id"], ["procurement_vendor_invoices.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["grn_accrual_id"], ["finance_grn_accruals.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["goods_receipt_id"], ["procurement_goods_receipts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["journal_line_id"], ["finance_journal_lines.id"], ondelete="SET NULL"),
        sa.CheckConstraint("allocated_amount > 0", name="ck_finance_invoice_receipt_allocations_amount"),
        sa.UniqueConstraint(
            "vendor_invoice_id",
            "grn_accrual_id",
            name="uq_finance_invoice_receipt_allocations_invoice_accrual",
        ),
    )
    for column in ("tenant_id", "created_by_id", "vendor_invoice_id", "goods_receipt_id"):
        op.create_index(
            f"ix_finance_vendor_invoice_receipt_allocations_{column}",
            "finance_vendor_invoice_receipt_allocations",
            [column],
        )
    op.create_index(
        "ix_finance_invoice_receipt_allocations_accrual",
        "finance_vendor_invoice_receipt_allocations",
        ["tenant_id", "grn_accrual_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_finance_invoice_receipt_allocations_accrual",
        table_name="finance_vendor_invoice_receipt_allocations",
    )
    for column in ("tenant_id", "created_by_id", "vendor_invoice_id", "goods_receipt_id"):
        op.drop_index(
            f"ix_finance_vendor_invoice_receipt_allocations_{column}",
            table_name="finance_vendor_invoice_receipt_allocations",
        )
    op.drop_table("finance_vendor_invoice_receipt_allocations")
    op.drop_column("finance_grn_accruals", "cleared_amount")
