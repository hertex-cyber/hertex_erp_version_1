"""enforce tenant chart-of-accounts codes

Revision ID: 48ab7c10e2f6
Revises: 1f0c7d9a3e52
Create Date: 2026-11-18 00:17:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "48ab7c10e2f6"
down_revision: Union[str, None] = "1f0c7d9a3e52"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_index("ix_finance_accounts_code", table_name="finance_accounts")
    op.create_unique_constraint(
        "uq_finance_accounts_tenant_code",
        "finance_accounts",
        ["tenant_id", "code"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_finance_accounts_tenant_code",
        "finance_accounts",
        type_="unique",
    )
    op.create_index(
        "ix_finance_accounts_code",
        "finance_accounts",
        ["code"],
        unique=False,
    )
