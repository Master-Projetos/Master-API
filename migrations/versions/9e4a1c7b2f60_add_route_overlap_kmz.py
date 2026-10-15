"""add overlap kmz to route analyses

Revision ID: 9e4a1c7b2f60
Revises: 5d2b8f4e7a13
Create Date: 2026-10-15 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9e4a1c7b2f60'
down_revision: Union[str, Sequence[str], None] = '5d2b8f4e7a13'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Nullable, no default: instant on existing rows
    op.add_column('route_analyses', sa.Column('overlap_kmz', sa.LargeBinary(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('route_analyses', 'overlap_kmz')
