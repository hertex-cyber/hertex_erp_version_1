from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "6f2a9d4c8b13"
down_revision: str | None = "b15c2d4e6f70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.create_table(
        "procurement_ocr_invoice_drafts",
        sa.Column("id", UUID, nullable=False),
        sa.Column("tenant_id", UUID, nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_by_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source_type", sa.String(20), nullable=False),
        sa.Column("source_digest", sa.String(64), nullable=False),
        sa.Column("filename", sa.String(255), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("provider", sa.String(40), server_default="local_stub", nullable=False),
        sa.Column("credential_key", sa.String(120), nullable=True),
        sa.Column("vendor_name", sa.String(200), nullable=False),
        sa.Column("vendor_id", UUID, nullable=True),
        sa.Column("invoice_number", sa.String(60), nullable=False),
        sa.Column("invoice_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), server_default="0", nullable=False),
        sa.Column("gstin", sa.String(30), nullable=True),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", nullable=False),
        sa.Column("confirmed_invoice_id", UUID, nullable=True),
        sa.Column("reviewed_by_id", UUID, nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("source_metadata", sa.JSON(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vendor_id"], ["procurement_vendors.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["confirmed_invoice_id"], ["procurement_vendor_invoices.id"], ondelete="SET NULL"
        ),
    )
    for column in (
        "tenant_id",
        "is_active",
        "created_by_id",
        "source_type",
        "source_digest",
        "vendor_name",
        "vendor_id",
        "invoice_number",
        "gstin",
        "status",
    ):
        op.create_index(
            f"ix_procurement_ocr_invoice_drafts_{column}",
            "procurement_ocr_invoice_drafts",
            [column],
        )


def downgrade() -> None:
    op.drop_table("procurement_ocr_invoice_drafts")
