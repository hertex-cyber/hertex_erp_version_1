"""role menu access

Revision ID: f4b8c2d9a601
Revises: c15d3e7f8a91
Create Date: 2026-11-21 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4b8c2d9a601'
down_revision: Union[str, None] = 'c15d3e7f8a91'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'roles',
        sa.Column('menu_keys', sa.JSON(), nullable=False, server_default='[]'),
    )


def downgrade() -> None:
    op.drop_column('roles', 'menu_keys')
