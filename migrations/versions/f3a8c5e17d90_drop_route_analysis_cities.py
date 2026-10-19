"""drop route analysis cities

Revision ID: f3a8c5e17d90
Revises: b6e2d9a4c731
Create Date: 2026-10-19 15:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f3a8c5e17d90'
down_revision: Union[str, Sequence[str], None] = 'b6e2d9a4c731'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index(op.f('ix_route_analysis_cities_analysis_id'), table_name='route_analysis_cities')
    op.drop_table('route_analysis_cities')


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table('route_analysis_cities',
    sa.Column('analysis_id', sa.Uuid(), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('ibge_code', sa.String(length=10), nullable=False),
    sa.Column('poles_base', sa.String(length=100), nullable=False),
    sa.Column('city_poles', sa.Integer(), nullable=False),
    sa.Column('near_poles', sa.Integer(), nullable=False),
    sa.Column('near_poles_pct', sa.Float(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_id'], ['route_analyses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_route_analysis_cities_analysis_id'), 'route_analysis_cities', ['analysis_id'], unique=False)
