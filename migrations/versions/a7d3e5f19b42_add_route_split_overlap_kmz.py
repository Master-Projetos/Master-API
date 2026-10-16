"""add with/without overlap kmz to route analyses

Revision ID: a7d3e5f19b42
Revises: c4f8a2d61e93
Create Date: 2026-10-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7d3e5f19b42'
down_revision: Union[str, Sequence[str], None] = 'c4f8a2d61e93'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, no default: instant on existing rows
    op.add_column('route_analyses', sa.Column('with_overlap_kmz', sa.LargeBinary(), nullable=True))
    op.add_column('route_analyses', sa.Column('without_overlap_kmz', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('route_analyses', 'without_overlap_kmz')
    op.drop_column('route_analyses', 'with_overlap_kmz')
