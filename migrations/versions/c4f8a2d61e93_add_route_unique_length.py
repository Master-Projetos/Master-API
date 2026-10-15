"""add unique length to route cable types and cables

Revision ID: c4f8a2d61e93
Revises: 9e4a1c7b2f60
Create Date: 2026-10-15 18:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4f8a2d61e93'
down_revision: Union[str, Sequence[str], None] = '9e4a1c7b2f60'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, no default: instant on existing rows, which stay null until
    # their KMZ is uploaded again
    op.add_column('route_cable_types', sa.Column('unique_length_m', sa.Integer(), nullable=True))
    op.add_column('route_cables', sa.Column('unique_length_m', sa.Float(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('route_cables', 'unique_length_m')
    op.drop_column('route_cable_types', 'unique_length_m')
