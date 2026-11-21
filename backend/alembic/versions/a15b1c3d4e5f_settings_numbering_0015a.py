"""Settings 0015a: numbering counter and ledger tables.

Revision ID: a15b1c3d4e5f
Revises: 9b7e3c21f0a4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a15b1c3d4e5f"
down_revision: Union[str, None] = "9b7e3c21f0a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    for column in (
        sa.Column("doc_type", sa.String(40), nullable=False, server_default="internal"),
        sa.Column("owner_module", sa.String(40), nullable=False, server_default="general"),
        sa.Column("pattern", sa.String(120), nullable=True),
        sa.Column("suffix", sa.String(30), nullable=False, server_default=""),
        sa.Column("start_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("increment", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("implementation", sa.String(16), nullable=False, server_default="standard"),
        sa.Column("reset_policy", sa.String(16), nullable=False, server_default="fiscal_year"),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("gstin", sa.String(15), nullable=True),
        sa.Column("max_length", sa.Integer(), nullable=True),
        sa.Column("allowed_chars_regex", sa.String(160), nullable=True),
        sa.Column("irp_safe", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("manual_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("advance_on_manual", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("last_allocated_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("number_sequences", column)

    op.create_index("ix_number_sequences_tenant_module", "number_sequences", ["tenant_id", "owner_module"])
    op.create_index("ix_number_sequences_branch_id", "number_sequences", ["branch_id"])

    op.create_table(
        "number_sequence_periods",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sequence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_year", sa.String(9), server_default="", nullable=False),
        sa.Column("period_start", sa.Date(), nullable=False),
        sa.Column("period_end", sa.Date(), nullable=False),
        sa.Column("next_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("allocated_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(16), server_default="open", nullable=False),
        sa.Column("last_allocated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_allocated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sequence_id"], ["number_sequences.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["last_allocated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("sequence_id", "fiscal_year", name="uq_sequence_periods_seq_fy"),
    )
    op.create_index("ix_sequence_periods_tenant_fy", "number_sequence_periods", ["tenant_id", "fiscal_year"])
    op.create_index("ix_number_sequence_periods_sequence_id", "number_sequence_periods", ["sequence_id"])

    op.create_table(
        "number_allocations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sequence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_year", sa.String(9), server_default="", nullable=False),
        sa.Column("number", sa.BigInteger(), nullable=False),
        sa.Column("rendered", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), server_default="allocated", nullable=False),
        sa.Column("document_type", sa.String(40), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("branch_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("device_id", sa.String(80), nullable=True),
        sa.Column("idempotency_key", sa.String(120), nullable=True),
        sa.Column("reason_code", sa.String(24), nullable=True),
        sa.Column("reason_text", sa.String(200), nullable=True),
        sa.Column("allocated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("committed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("allocated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sequence_id"], ["number_sequences.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["period_id"], ["number_sequence_periods.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["allocated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("sequence_id", "fiscal_year", "number", name="uq_number_allocations_seq_fy_number"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_number_allocations_idempotency"),
    )
    op.create_index("ix_number_allocations_tenant_status", "number_allocations", ["tenant_id", "status", "allocated_at"])
    op.create_index("ix_number_allocations_document", "number_allocations", ["tenant_id", "document_type", "document_id"])
    op.create_index("ix_number_allocations_sequence_id", "number_allocations", ["sequence_id"])
    op.create_index("ix_number_allocations_period_id", "number_allocations", ["period_id"])
    op.create_index("ix_number_allocations_rendered", "number_allocations", ["rendered"])

    op.create_table(
        "number_sequence_blocks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sequence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("period_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fiscal_year", sa.String(9), server_default="", nullable=False),
        sa.Column("range_start", sa.BigInteger(), nullable=False),
        sa.Column("range_end", sa.BigInteger(), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("device_id", sa.String(80), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(16), server_default="issued", nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("returned_from", sa.BigInteger(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["sequence_id"], ["number_sequences.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["period_id"], ["number_sequence_periods.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sequence_blocks_device", "number_sequence_blocks", ["tenant_id", "device_id", "status"])
    op.create_index("ix_number_sequence_blocks_sequence_id", "number_sequence_blocks", ["sequence_id"])
    op.create_index("ix_number_sequence_blocks_period_id", "number_sequence_blocks", ["period_id"])


def downgrade() -> None:
    op.drop_table("number_sequence_blocks")
    op.drop_table("number_allocations")
    op.drop_table("number_sequence_periods")
    op.drop_index("ix_number_sequences_branch_id", table_name="number_sequences")
    op.drop_index("ix_number_sequences_tenant_module", table_name="number_sequences")
    for name in (
        "last_allocated_at", "status", "advance_on_manual", "manual_allowed", "irp_safe",
        "allowed_chars_regex", "max_length", "gstin", "branch_id", "reset_policy",
        "implementation", "increment", "start_number", "suffix", "pattern", "owner_module", "doc_type",
    ):
        op.drop_column("number_sequences", name)
