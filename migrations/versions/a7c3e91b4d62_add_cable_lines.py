"""add cable lines

Revision ID: a7c3e91b4d62
Revises: e5a9c2d7b134
Create Date: 2026-10-20 16:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a7c3e91b4d62'
down_revision: Union[str, Sequence[str], None] = 'e5a9c2d7b134'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'route_analyses',
        sa.Column('cable_lines', sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        'backbone_cities',
        sa.Column('cable_lines', sa.LargeBinary(), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('backbone_cities', 'cable_lines')
    op.drop_column('route_analyses', 'cable_lines')
