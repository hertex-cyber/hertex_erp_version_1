"""add project management hardening columns

Revision ID: b7c1d5e9f203
Revises: f2a39b18c7d4
Create Date: 2026-11-18 03:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7c1d5e9f203"
down_revision: str | None = "f2a39b18c7d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("audit_logs", sa.Column("on_behalf_of_id", sa.UUID(), nullable=True))
    op.add_column("audit_logs", sa.Column("correlation_id", sa.String(length=120), nullable=True))
    op.create_foreign_key(
        "fk_audit_logs_on_behalf_of_id_users",
        "audit_logs",
        "users",
        ["on_behalf_of_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_audit_logs_correlation_id"), "audit_logs", ["correlation_id"], unique=False
    )

    op.add_column("project_tasks", sa.Column("acceptance_criteria", sa.Text(), nullable=True))
    op.add_column(
        "project_board_columns",
        sa.Column(
            "wip_enforced", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "project_resource_bookings",
        sa.Column(
            "capacity_override", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column("project_resource_bookings", sa.Column("override_reason", sa.Text(), nullable=True))
    op.add_column(
        "project_outbox_events", sa.Column("correlation_id", sa.String(length=120), nullable=True)
    )
    op.add_column(
        "project_outbox_events", sa.Column("idempotency_key", sa.String(length=200), nullable=True)
    )
    op.create_index(
        op.f("ix_project_outbox_events_correlation_id"),
        "project_outbox_events",
        ["correlation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_project_outbox_events_idempotency_key"),
        "project_outbox_events",
        ["idempotency_key"],
        unique=False,
    )
    op.create_index(
        "uq_project_outbox_events_idempotency",
        "project_outbox_events",
        ["event_name", "idempotency_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_project_outbox_events_idempotency", table_name="project_outbox_events")
    op.drop_index(
        op.f("ix_project_outbox_events_idempotency_key"), table_name="project_outbox_events"
    )
    op.drop_index(
        op.f("ix_project_outbox_events_correlation_id"), table_name="project_outbox_events"
    )
    op.drop_column("project_outbox_events", "idempotency_key")
    op.drop_column("project_outbox_events", "correlation_id")
    op.drop_column("project_resource_bookings", "override_reason")
    op.drop_column("project_resource_bookings", "capacity_override")
    op.drop_column("project_board_columns", "wip_enforced")
    op.drop_column("project_tasks", "acceptance_criteria")
    op.drop_index(op.f("ix_audit_logs_correlation_id"), table_name="audit_logs")
    op.drop_constraint(
        "fk_audit_logs_on_behalf_of_id_users", "audit_logs", type_="foreignkey"
    )
    op.drop_column("audit_logs", "correlation_id")
    op.drop_column("audit_logs", "on_behalf_of_id")
