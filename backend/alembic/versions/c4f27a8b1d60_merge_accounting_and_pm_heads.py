"""merge accounting and project-management migration heads

Revision ID: c4f27a8b1d60
Revises: b19d4e63a870, b7c1d5e9f203
Create Date: 2026-11-18 02:00:00.000000

"""
from collections.abc import Sequence

revision: str = "c4f27a8b1d60"
down_revision: tuple[str, str] = ("b19d4e63a870", "b7c1d5e9f203")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
