"""align PM integration schema drift

Revision ID: f4e2c8a7b913
Revises: ee41c9d2a703
Create Date: 2026-11-18 02:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4e2c8a7b913"
down_revision: str | None = "ee41c9d2a703"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("hr_employees", sa.Column("date_of_exit", sa.Date(), nullable=True))
    op.create_index(
        "ix_hr_employees_date_of_exit", "hr_employees", ["date_of_exit"], unique=False
    )
    op.add_column(
        "support_tickets",
        sa.Column(
            "needs_project_work", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.execute("UPDATE support_tickets SET needs_project_work = false WHERE needs_project_work IS NULL")
    op.alter_column(
        "support_tickets",
        "needs_project_work",
        existing_type=sa.Boolean(),
        server_default=None,
    )
    op.add_column(
        "support_tickets",
        sa.Column("project_work_item_id", sa.UUID(), nullable=True),
    )
    op.create_index(
        "ix_support_tickets_needs_project_work",
        "support_tickets",
        ["needs_project_work"],
        unique=False,
    )
    op.create_index(
        "ix_support_tickets_project_work_item_id",
        "support_tickets",
        ["project_work_item_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_support_tickets_project_work_item_id",
        "support_tickets",
        "project_tasks",
        ["project_work_item_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column(
        "project_board_columns", "wip_enforced", existing_type=sa.Boolean(), server_default=None
    )
    op.alter_column(
        "project_resource_bookings", "capacity_override", existing_type=sa.Boolean(), server_default=None
    )
    op.alter_column(
        "project_resource_bookings", "split_allowed", existing_type=sa.Boolean(), server_default=None
    )
    for column in ("payload_json", "mapping_json", "validation_json", "dry_run_json"):
        op.alter_column(
            "project_import_batches",
            column,
            existing_type=sa.JSON(),
            server_default=None,
        )
    op.alter_column(
        "project_sprints",
        "metrics_json",
        existing_type=sa.JSON(),
        server_default=None,
    )
    op.drop_index("uq_project_outbox_events_idempotency", table_name="project_outbox_events")
    op.create_unique_constraint(
        "uq_project_outbox_events_idempotency",
        "project_outbox_events",
        ["event_name", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_project_outbox_events_idempotency",
        "project_outbox_events",
        type_="unique",
    )
    op.create_index(
        "uq_project_outbox_events_idempotency",
        "project_outbox_events",
        ["event_name", "idempotency_key"],
        unique=True,
    )
    op.alter_column(
        "project_sprints",
        "metrics_json",
        existing_type=sa.JSON(),
        server_default=sa.text("'{}'::json"),
    )
    for column in ("payload_json", "mapping_json", "validation_json", "dry_run_json"):
        op.alter_column(
            "project_import_batches",
            column,
            existing_type=sa.JSON(),
            server_default=sa.text("'{}'::json"),
        )
    op.alter_column(
        "project_resource_bookings", "split_allowed", existing_type=sa.Boolean(), server_default=sa.false()
    )
    op.alter_column(
        "project_resource_bookings", "capacity_override", existing_type=sa.Boolean(), server_default=sa.false()
    )
    op.alter_column(
        "project_board_columns", "wip_enforced", existing_type=sa.Boolean(), server_default=sa.false()
    )
    op.drop_constraint(
        "fk_support_tickets_project_work_item_id", "support_tickets", type_="foreignkey"
    )
    op.drop_index("ix_support_tickets_project_work_item_id", table_name="support_tickets")
    op.drop_index("ix_support_tickets_needs_project_work", table_name="support_tickets")
    op.drop_column("support_tickets", "project_work_item_id")
    op.drop_column("support_tickets", "needs_project_work")
    op.drop_index("ix_hr_employees_date_of_exit", table_name="hr_employees")
    op.drop_column("hr_employees", "date_of_exit")
