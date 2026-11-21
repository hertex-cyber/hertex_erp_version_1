"""Settings 0015b: typed settings, change history, secrets, and document uniqueness.

Revision ID: b15c2d4e6f70
Revises: a15b1c3d4e5f
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b15c2d4e6f70"
down_revision: Union[str, None] = "a15b1c3d4e5f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in (
        sa.Column("scope_type", sa.String(16), server_default="tenant", nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("value_type", sa.String(16), server_default="json", nullable=False),
        sa.Column("is_secret", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("source", sa.String(16), server_default="admin", nullable=False),
        sa.Column("checksum", sa.String(64), server_default="", nullable=False),
    ):
        op.add_column("app_settings", column)
    op.create_index("ix_app_settings_tenant_key", "app_settings", ["tenant_id", "key"])
    op.create_index("ix_app_settings_scope_id", "app_settings", ["scope_id"])

    op.create_table(
        "setting_changes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("scope_type", sa.String(16), server_default="tenant", nullable=False),
        sa.Column("scope_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("old_value", sa.JSON(), nullable=True),
        sa.Column("new_value", sa.JSON(), nullable=True),
        sa.Column("change_type", sa.String(16), server_default="set", nullable=False),
        sa.Column("reason", sa.Text(), server_default="", nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_email", sa.String(255), server_default="system", nullable=False),
        sa.Column("approved_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("approval_state", sa.String(16), server_default="none", nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_id", sa.String(120), nullable=True),
        sa.Column("correlation_id", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_setting_changes_tenant_key", "setting_changes", ["tenant_id", "key"])
    op.create_index("ix_setting_changes_tenant_state", "setting_changes", ["tenant_id", "approval_state"])

    op.create_table(
        "setting_secrets",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("key", sa.String(120), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("key_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("algo", sa.String(32), server_default="AES-256-GCM", nullable=False),
        sa.Column("previous_ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("previous_nonce", sa.LargeBinary(), nullable=True),
        sa.Column("previous_key_version", sa.Integer(), nullable=True),
        sa.Column("previous_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(16), server_default="active", nullable=False),
        sa.Column("mask", sa.String(40), server_default="", nullable=False),
        sa.Column("rotated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rotated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["rotated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("tenant_id", "key", name="uq_setting_secrets_tenant_key"),
    )
    op.create_index("ix_setting_secrets_key", "setting_secrets", ["key"])
    op.create_index("ix_setting_secrets_tenant_id", "setting_secrets", ["tenant_id"])

    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE app_settings DROP CONSTRAINT IF EXISTS uq_app_settings_tenant_key")
        op.execute("ALTER TABLE app_settings DROP CONSTRAINT IF EXISTS uq_app_settings_scope_key")
        op.execute("ALTER TABLE app_settings ADD CONSTRAINT uq_app_settings_scope_key UNIQUE NULLS NOT DISTINCT (tenant_id, scope_type, scope_id, key)")

    constraints = (
        ("finance_journal_entries", "entry_number", "uq_finance_journal_entries_tenant_number"),
        ("finance_invoices", "invoice_number", "uq_finance_invoices_tenant_number"),
        ("sales_orders", "order_number", "uq_sales_orders_tenant_number"),
        ("sales_delivery_challans", "challan_number", "uq_sales_delivery_challans_tenant_number"),
        ("pos_sales", "sale_number", "uq_pos_sales_tenant_number"),
        ("procurement_purchase_orders", "po_number", "uq_procurement_purchase_orders_tenant_number"),
        ("procurement_goods_receipts", "grn_number", "uq_procurement_goods_receipts_tenant_number"),
        ("procurement_requisitions", "requisition_number", "uq_procurement_requisitions_tenant_number"),
        ("support_tickets", "ticket_number", "uq_support_tickets_tenant_number"),
    )
    for table, column, name in constraints:
        op.create_unique_constraint(name, table, ["tenant_id", column])


def downgrade() -> None:
    for table, _column, name in (
        ("support_tickets", "ticket_number", "uq_support_tickets_tenant_number"),
        ("procurement_requisitions", "requisition_number", "uq_procurement_requisitions_tenant_number"),
        ("procurement_goods_receipts", "grn_number", "uq_procurement_goods_receipts_tenant_number"),
        ("procurement_purchase_orders", "po_number", "uq_procurement_purchase_orders_tenant_number"),
        ("pos_sales", "sale_number", "uq_pos_sales_tenant_number"),
        ("sales_delivery_challans", "challan_number", "uq_sales_delivery_challans_tenant_number"),
        ("sales_orders", "order_number", "uq_sales_orders_tenant_number"),
        ("finance_invoices", "invoice_number", "uq_finance_invoices_tenant_number"),
        ("finance_journal_entries", "entry_number", "uq_finance_journal_entries_tenant_number"),
    ):
        op.drop_constraint(name, table, type_="unique")
    op.drop_table("setting_secrets")
    op.drop_table("setting_changes")
    op.drop_index("ix_app_settings_scope_id", table_name="app_settings")
    op.drop_index("ix_app_settings_tenant_key", table_name="app_settings")
    if op.get_bind().dialect.name == "postgresql":
        op.execute("ALTER TABLE app_settings DROP CONSTRAINT IF EXISTS uq_app_settings_scope_key")
        op.execute("ALTER TABLE app_settings ADD CONSTRAINT uq_app_settings_tenant_key UNIQUE (tenant_id, key)")
    for name in ("checksum", "source", "updated_by_id", "version", "is_secret", "value_type", "scope_id", "scope_type"):
        op.drop_column("app_settings", name)
