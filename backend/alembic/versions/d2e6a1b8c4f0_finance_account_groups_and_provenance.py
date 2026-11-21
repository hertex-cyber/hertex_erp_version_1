"""add account groups and journal provenance/idempotency

Revision ID: d2e6a1b8c4f0
Revises: f4e2c8a7b913
Create Date: 2026-11-19 19:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "d2e6a1b8c4f0"
down_revision: Union[str, None] = "f4e2c8a7b913"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'users'::regclass AND contype = 'p'
        ) THEN
            ALTER TABLE users ADD CONSTRAINT pk_users_id PRIMARY KEY (id);
        END IF;
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conrelid = 'tenants'::regclass AND contype = 'p'
        ) THEN
            ALTER TABLE tenants ADD CONSTRAINT pk_tenants_id PRIMARY KEY (id);
        END IF;
    END $$;
    """)
    op.create_table(
        "finance_account_groups",
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("account_type", sa.String(length=30), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "account_type IN ('asset', 'liability', 'equity', 'income', 'expense')",
            name="ck_finance_account_groups_type",
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["parent_id"], ["finance_account_groups.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_finance_account_groups_tenant_code"),
    )
    op.create_index(
        "ix_finance_account_groups_tenant_type",
        "finance_account_groups",
        ["tenant_id", "account_type"],
    )
    op.create_index(
        "ix_finance_account_groups_account_type",
        "finance_account_groups",
        ["account_type"],
    )
    op.create_index(
        "ix_finance_account_groups_is_active",
        "finance_account_groups",
        ["is_active"],
    )
    op.create_index(
        "ix_finance_account_groups_tenant_id",
        "finance_account_groups",
        ["tenant_id"],
    )
    op.create_index(
        "ix_finance_account_groups_created_by_id",
        "finance_account_groups",
        ["created_by_id"],
    )
    op.add_column(
        "finance_accounts",
        sa.Column("group_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_finance_accounts_group_id_finance_account_groups",
        "finance_accounts",
        "finance_account_groups",
        ["group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_finance_accounts_group_id", "finance_accounts", ["group_id"])
    op.add_column("finance_journal_entries", sa.Column("source_module", sa.String(length=40), nullable=True))
    op.add_column("finance_journal_entries", sa.Column("source_document_type", sa.String(length=60), nullable=True))
    op.add_column("finance_journal_entries", sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("finance_journal_entries", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.create_unique_constraint(
        "uq_finance_journal_entries_tenant_idempotency",
        "finance_journal_entries",
        ["tenant_id", "idempotency_key"],
    )
    op.create_index(
        "ix_finance_journal_entries_source_document",
        "finance_journal_entries",
        ["tenant_id", "source_module", "source_document_type", "source_document_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_finance_journal_entries_source_document", table_name="finance_journal_entries")
    op.drop_constraint(
        "uq_finance_journal_entries_tenant_idempotency",
        "finance_journal_entries",
        type_="unique",
    )
    op.drop_column("finance_journal_entries", "idempotency_key")
    op.drop_column("finance_journal_entries", "source_document_id")
    op.drop_column("finance_journal_entries", "source_document_type")
    op.drop_column("finance_journal_entries", "source_module")
    op.drop_index("ix_finance_accounts_group_id", table_name="finance_accounts")
    op.drop_constraint(
        "fk_finance_accounts_group_id_finance_account_groups",
        "finance_accounts",
        type_="foreignkey",
    )
    op.drop_column("finance_accounts", "group_id")
    op.drop_index("ix_finance_account_groups_created_by_id", table_name="finance_account_groups")
    op.drop_index("ix_finance_account_groups_tenant_id", table_name="finance_account_groups")
    op.drop_index("ix_finance_account_groups_is_active", table_name="finance_account_groups")
    op.drop_index("ix_finance_account_groups_account_type", table_name="finance_account_groups")
    op.drop_index("ix_finance_account_groups_tenant_type", table_name="finance_account_groups")
    op.drop_table("finance_account_groups")
