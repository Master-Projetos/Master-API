"""add licensed poles

Revision ID: e5a9c2d7b134
Revises: f3a8c5e17d90
Create Date: 2026-10-20 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e5a9c2d7b134'
down_revision: Union[str, Sequence[str], None] = 'f3a8c5e17d90'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('licensed_pole_sets',
    sa.Column('code', sa.String(length=255), nullable=False),
    sa.Column('set_date', sa.Date(), nullable=False),
    sa.Column('licensed_file', sa.String(length=255), nullable=False),
    sa.Column('outside_poles', sa.Integer(), nullable=False),
    sa.Column('outside_markers', sa.JSON(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_licensed_pole_sets_set_date'), 'licensed_pole_sets', ['set_date'], unique=False)
    op.create_table('licensed_pole_cities',
    sa.Column('set_id', sa.Uuid(), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('ibge_code', sa.String(length=10), nullable=False),
    sa.Column('poles', sa.Integer(), nullable=False),
    sa.Column('markers', sa.JSON(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['set_id'], ['licensed_pole_sets.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('set_id', 'ibge_code')
    )
    op.create_index(op.f('ix_licensed_pole_cities_ibge_code'), 'licensed_pole_cities', ['ibge_code'], unique=False)
    op.create_index(op.f('ix_licensed_pole_cities_set_id'), 'licensed_pole_cities', ['set_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_licensed_pole_cities_set_id'), table_name='licensed_pole_cities')
    op.drop_index(op.f('ix_licensed_pole_cities_ibge_code'), table_name='licensed_pole_cities')
    op.drop_table('licensed_pole_cities')
    op.drop_index(op.f('ix_licensed_pole_sets_set_date'), table_name='licensed_pole_sets')
    op.drop_table('licensed_pole_sets')
