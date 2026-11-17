"""role active flag

Revision ID: 9c41b7f3d2a8
Revises: 6a04e2a77f21
Create Date: 2026-11-16 22:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9c41b7f3d2a8'
down_revision: Union[str, None] = '6a04e2a77f21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'roles',
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_index(op.f('ix_roles_is_active'), 'roles', ['is_active'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_roles_is_active'), table_name='roles')
    op.drop_column('roles', 'is_active')
