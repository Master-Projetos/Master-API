"""add route poles analyses

Revision ID: 5d2b8f4e7a13
Revises: 3b7e9a1c5d20
Create Date: 2026-10-14 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d2b8f4e7a13'
down_revision: Union[str, Sequence[str], None] = '3b7e9a1c5d20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('route_analyses',
    sa.Column('code', sa.String(length=255), nullable=False),
    sa.Column('analysis_date', sa.Date(), nullable=False),
    sa.Column('city', sa.String(length=100), nullable=False),
    sa.Column('ibge_code', sa.String(length=10), nullable=False),
    sa.Column('routes_file', sa.String(length=255), nullable=False),
    sa.Column('poles_base', sa.String(length=100), nullable=False),
    sa.Column('radius_m', sa.Float(), nullable=False),
    sa.Column('city_poles', sa.Integer(), nullable=False),
    sa.Column('near_poles', sa.Integer(), nullable=False),
    sa.Column('near_poles_pct', sa.Float(), nullable=False),
    sa.Column('route_length_m', sa.Integer(), nullable=False),
    sa.Column('avg_span_m', sa.Float(), nullable=False),
    sa.Column('poles_kmz', sa.LargeBinary(), nullable=False),
    sa.Column('all_poles_kmz', sa.LargeBinary(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_route_analyses_analysis_date'), 'route_analyses', ['analysis_date'], unique=False)
    op.create_index(op.f('ix_route_analyses_ibge_code'), 'route_analyses', ['ibge_code'], unique=False)
    op.create_table('route_cable_types',
    sa.Column('analysis_id', sa.Uuid(), nullable=False),
    sa.Column('cable_type', sa.String(length=50), nullable=False),
    sa.Column('cables', sa.Integer(), nullable=False),
    sa.Column('length_m', sa.Integer(), nullable=False),
    sa.Column('near_poles', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_id'], ['route_analyses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_route_cable_types_analysis_id'), 'route_cable_types', ['analysis_id'], unique=False)
    op.create_table('route_cables',
    sa.Column('analysis_id', sa.Uuid(), nullable=False),
    sa.Column('folder', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('cable_type', sa.String(length=50), nullable=False),
    sa.Column('length_m', sa.Float(), nullable=False),
    sa.Column('near_poles', sa.Integer(), nullable=False),
    sa.Column('near_poles_5m', sa.Integer(), nullable=False),
    sa.Column('no_pole_m', sa.Integer(), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['analysis_id'], ['route_analyses.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_route_cables_analysis_id'), 'route_cables', ['analysis_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_route_cables_analysis_id'), table_name='route_cables')
    op.drop_table('route_cables')
    op.drop_index(op.f('ix_route_cable_types_analysis_id'), table_name='route_cable_types')
    op.drop_table('route_cable_types')
    op.drop_index(op.f('ix_route_analyses_ibge_code'), table_name='route_analyses')
    op.drop_index(op.f('ix_route_analyses_analysis_date'), table_name='route_analyses')
    op.drop_table('route_analyses')
