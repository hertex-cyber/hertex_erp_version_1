"""add project workflow and import staging structures

Revision ID: a1c2d3e4f5b6
Revises: c4f27a8b1d60
Create Date: 2026-11-18 04:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1c2d3e4f5b6"
down_revision: str | None = "c4f27a8b1d60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("project_sprints", sa.Column("metrics_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("project_resource_bookings", sa.Column("split_allowed", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("project_activities", sa.Column("template_code", sa.String(length=80), nullable=True))
    op.add_column("project_activities", sa.Column("recipient", sa.String(length=255), nullable=True))
    op.add_column("project_activities", sa.Column("message_id", sa.String(length=150), nullable=True))
    op.add_column("project_activities", sa.Column("consent_reference", sa.String(length=150), nullable=True))
    op.create_index(op.f("ix_project_activities_message_id"), "project_activities", ["message_id"], unique=False)
    op.add_column("project_import_batches", sa.Column("payload_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("project_import_batches", sa.Column("mapping_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("project_import_batches", sa.Column("validation_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("project_import_batches", sa.Column("dry_run_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("project_import_batches", sa.Column("approved_by_id", sa.UUID(), nullable=True))
    op.add_column("project_import_batches", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("project_import_batches", sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("project_import_batches", sa.Column("rolled_back_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_project_import_batches_approved_by_id_users",
        "project_import_batches",
        "users",
        ["approved_by_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "project_import_rows",
        sa.Column("batch_id", sa.UUID(), nullable=False),
        sa.Column("row_key", sa.String(length=100), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("raw_json", sa.JSON(), nullable=False),
        sa.Column("normalized_json", sa.JSON(), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("target_id", sa.UUID(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["batch_id"], ["project_import_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "batch_id", "row_key", name="uq_pm_import_rows_key"),
    )
    op.create_index(op.f("ix_project_import_rows_batch_id"), "project_import_rows", ["batch_id"], unique=False)
    op.create_index(op.f("ix_project_import_rows_is_active"), "project_import_rows", ["is_active"], unique=False)
    op.create_index("ix_pm_import_rows_status", "project_import_rows", ["batch_id", "status"], unique=False)
    op.create_index(op.f("ix_project_import_rows_source_type"), "project_import_rows", ["source_type"], unique=False)
    op.create_index(op.f("ix_project_import_rows_status"), "project_import_rows", ["status"], unique=False)
    op.create_index(op.f("ix_project_import_rows_tenant_id"), "project_import_rows", ["tenant_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_import_rows_tenant_id"), table_name="project_import_rows")
    op.drop_index(op.f("ix_project_import_rows_status"), table_name="project_import_rows")
    op.drop_index(op.f("ix_project_import_rows_source_type"), table_name="project_import_rows")
    op.drop_index("ix_pm_import_rows_status", table_name="project_import_rows")
    op.drop_index(op.f("ix_project_import_rows_is_active"), table_name="project_import_rows")
    op.drop_index(op.f("ix_project_import_rows_batch_id"), table_name="project_import_rows")
    op.drop_table("project_import_rows")
    op.drop_constraint("fk_project_import_batches_approved_by_id_users", "project_import_batches", type_="foreignkey")
    op.drop_column("project_import_batches", "rolled_back_at")
    op.drop_column("project_import_batches", "committed_at")
    op.drop_column("project_import_batches", "approved_at")
    op.drop_column("project_import_batches", "approved_by_id")
    op.drop_column("project_import_batches", "dry_run_json")
    op.drop_column("project_import_batches", "validation_json")
    op.drop_column("project_import_batches", "mapping_json")
    op.drop_column("project_import_batches", "payload_json")
    op.drop_index(op.f("ix_project_activities_message_id"), table_name="project_activities")
    op.drop_column("project_activities", "consent_reference")
    op.drop_column("project_activities", "message_id")
    op.drop_column("project_activities", "recipient")
    op.drop_column("project_activities", "template_code")
    op.drop_column("project_resource_bookings", "split_allowed")
    op.drop_column("project_sprints", "metrics_json")
