"""add GST registrations, tax codes, and invoice tax snapshots

Revision ID: f2a39b18c7d4
Revises: 91d6f20a7c43
Create Date: 2026-11-18 02:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2a39b18c7d4"
down_revision: str | None = "91d6f20a7c43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _tenant_columns():
    return [
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
    ]


def _tax_line_columns(kind: str):
    account_prefix = "output" if kind == "sales" else "input"
    parent_table = "finance_invoices" if kind == "sales" else "procurement_vendor_invoices"
    parent_field = "invoice_id"
    return [
        *_tenant_columns(),
        sa.Column(parent_field, sa.UUID(), nullable=False),
        sa.Column("tax_code_id", sa.UUID(), nullable=False),
        sa.Column("registration_id", sa.UUID(), nullable=False),
        sa.Column("tax_type_snapshot", sa.String(length=20), nullable=False),
        sa.Column("can_claim_itc_snapshot", sa.Boolean(), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("place_of_supply_state_code", sa.String(length=2), nullable=False),
        sa.Column("taxable_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("cgst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("sgst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("igst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("cgst_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("sgst_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("igst_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(f"{account_prefix}_cgst_account_id", sa.UUID(), nullable=True),
        sa.Column(f"{account_prefix}_sgst_account_id", sa.UUID(), nullable=True),
        sa.Column(f"{account_prefix}_igst_account_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint([parent_field], [f"{parent_table}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tax_code_id"], ["finance_tax_codes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["registration_id"], ["finance_tax_registrations.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            [f"{account_prefix}_cgst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            [f"{account_prefix}_sgst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            [f"{account_prefix}_igst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    ]


def upgrade() -> None:
    op.create_table(
        "finance_tax_registrations",
        *_tenant_columns(),
        sa.Column("legal_name", sa.String(length=200), nullable=False),
        sa.Column("gstin", sa.String(length=15), nullable=False),
        sa.Column("state_code", sa.String(length=2), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "gstin", name="uq_finance_tax_registrations_tenant_gstin"),
    )
    op.create_index(
        "ix_finance_tax_registrations_tenant_id",
        "finance_tax_registrations",
        ["tenant_id"],
    )
    op.create_index(
        "ix_finance_tax_registrations_is_active",
        "finance_tax_registrations",
        ["is_active"],
    )
    op.create_index(
        "uq_finance_tax_registrations_default",
        "finance_tax_registrations",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("is_default IS TRUE"),
    )

    op.create_table(
        "finance_tax_codes",
        *_tenant_columns(),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=False),
        sa.Column("tax_type", sa.String(length=20), nullable=False),
        sa.Column("cgst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("sgst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("igst_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("can_claim_itc", sa.Boolean(), nullable=False),
        sa.Column("output_cgst_account_id", sa.UUID(), nullable=True),
        sa.Column("output_sgst_account_id", sa.UUID(), nullable=True),
        sa.Column("output_igst_account_id", sa.UUID(), nullable=True),
        sa.Column("input_cgst_account_id", sa.UUID(), nullable=True),
        sa.Column("input_sgst_account_id", sa.UUID(), nullable=True),
        sa.Column("input_igst_account_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["output_cgst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["output_sgst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["output_igst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["input_cgst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["input_sgst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["input_igst_account_id"], ["finance_accounts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "cgst_rate >= 0 AND sgst_rate >= 0 AND igst_rate >= 0",
            name="ck_finance_tax_codes_nonnegative_rates",
        ),
        sa.CheckConstraint(
            "cgst_rate + sgst_rate = igst_rate",
            name="ck_finance_tax_codes_gst_rate_components",
        ),
        sa.CheckConstraint(
            "tax_type IN ('taxable', 'exempt', 'zero_rated', 'non_gst')",
            name="ck_finance_tax_codes_tax_type",
        ),
        sa.UniqueConstraint("tenant_id", "code", name="uq_finance_tax_codes_tenant_code"),
    )
    op.create_index("ix_finance_tax_codes_tenant_id", "finance_tax_codes", ["tenant_id"])
    op.create_index("ix_finance_tax_codes_is_active", "finance_tax_codes", ["is_active"])

    op.create_table(
        "finance_invoice_tax_lines",
        *_tax_line_columns("sales"),
    )
    op.create_index(
        "ix_finance_invoice_tax_lines_invoice_id",
        "finance_invoice_tax_lines",
        ["invoice_id"],
    )
    op.create_index(
        "ix_finance_invoice_tax_lines_tenant_id",
        "finance_invoice_tax_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_finance_invoice_tax_lines_is_active",
        "finance_invoice_tax_lines",
        ["is_active"],
    )

    op.create_table(
        "procurement_vendor_invoice_tax_lines",
        *_tax_line_columns("vendor"),
    )
    op.create_index(
        "ix_procurement_vendor_invoice_tax_lines_invoice_id",
        "procurement_vendor_invoice_tax_lines",
        ["invoice_id"],
    )
    op.create_index(
        "ix_procurement_vendor_invoice_tax_lines_tenant_id",
        "procurement_vendor_invoice_tax_lines",
        ["tenant_id"],
    )
    op.create_index(
        "ix_procurement_vendor_invoice_tax_lines_is_active",
        "procurement_vendor_invoice_tax_lines",
        ["is_active"],
    )

    op.add_column(
        "sales_orders",
        sa.Column("tax_registration_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "sales_orders",
        sa.Column("place_of_supply_state_code", sa.String(length=2), nullable=True),
    )
    op.create_foreign_key(
        "fk_sales_orders_tax_registration_id",
        "sales_orders",
        "finance_tax_registrations",
        ["tax_registration_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.add_column(
        "sales_order_lines",
        sa.Column("tax_code_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("cgst_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("sgst_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("igst_amount", sa.Numeric(14, 2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("cgst_rate_snapshot", sa.Numeric(5, 2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("sgst_rate_snapshot", sa.Numeric(5, 2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("igst_rate_snapshot", sa.Numeric(5, 2), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("tax_type_snapshot", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("can_claim_itc_snapshot", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("output_cgst_account_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("output_sgst_account_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "sales_order_lines",
        sa.Column("output_igst_account_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_sales_order_lines_tax_code_id",
        "sales_order_lines",
        "finance_tax_codes",
        ["tax_code_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    for column in (
        "output_cgst_account_id",
        "output_sgst_account_id",
        "output_igst_account_id",
    ):
        op.create_foreign_key(
            f"fk_sales_order_lines_{column}",
            "sales_order_lines",
            "finance_accounts",
            [column],
            ["id"],
            ondelete="RESTRICT",
        )

    op.add_column(
        "inventory_products",
        sa.Column("tax_code_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_inventory_products_tax_code_id",
        "inventory_products",
        "finance_tax_codes",
        ["tax_code_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_inventory_products_tax_code_id", "inventory_products", type_="foreignkey"
    )
    op.drop_column("inventory_products", "tax_code_id")

    for column in ("output_igst_account_id", "output_sgst_account_id", "output_cgst_account_id"):
        op.drop_constraint(f"fk_sales_order_lines_{column}", "sales_order_lines", type_="foreignkey")
        op.drop_column("sales_order_lines", column)
    op.drop_constraint(
        "fk_sales_order_lines_tax_code_id", "sales_order_lines", type_="foreignkey"
    )
    for column in (
        "igst_rate_snapshot",
        "sgst_rate_snapshot",
        "cgst_rate_snapshot",
        "can_claim_itc_snapshot",
        "tax_type_snapshot",
        "igst_amount",
        "sgst_amount",
        "cgst_amount",
        "tax_code_id",
    ):
        op.drop_column("sales_order_lines", column)
    op.drop_constraint(
        "fk_sales_orders_tax_registration_id", "sales_orders", type_="foreignkey"
    )
    op.drop_column("sales_orders", "place_of_supply_state_code")
    op.drop_column("sales_orders", "tax_registration_id")

    for table in (
        "procurement_vendor_invoice_tax_lines",
        "finance_invoice_tax_lines",
    ):
        op.drop_index(f"ix_{table}_is_active", table_name=table)
        op.drop_index(f"ix_{table}_tenant_id", table_name=table)
        op.drop_index(f"ix_{table}_invoice_id", table_name=table)
        op.drop_table(table)
    op.drop_index("ix_finance_tax_codes_is_active", table_name="finance_tax_codes")
    op.drop_index("ix_finance_tax_codes_tenant_id", table_name="finance_tax_codes")
    op.drop_table("finance_tax_codes")
    op.drop_index(
        "uq_finance_tax_registrations_default",
        table_name="finance_tax_registrations",
    )
    op.drop_index("ix_finance_tax_registrations_is_active", table_name="finance_tax_registrations")
    op.drop_index("ix_finance_tax_registrations_tenant_id", table_name="finance_tax_registrations")
    op.drop_table("finance_tax_registrations")
