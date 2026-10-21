"""add backbones

Revision ID: b6e2d9a4c731
Revises: d8b3f6a2c915
Create Date: 2026-10-19 15:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b6e2d9a4c731'
down_revision: Union[str, Sequence[str], None] = 'd8b3f6a2c915'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'backbones',
        sa.Column('code', sa.String(length=255), nullable=False),
        sa.Column('backbone_date', sa.Date(), nullable=False),
        sa.Column('routes_file', sa.String(length=255), nullable=False),
        sa.Column('radius_m', sa.Float(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code'),
    )
    op.create_index(
        op.f('ix_backbones_backbone_date'),
        'backbones',
        ['backbone_date'],
        unique=False,
    )
    op.create_table(
        'backbone_cities',
        sa.Column('city', sa.String(length=100), nullable=False),
        sa.Column('ibge_code', sa.String(length=10), nullable=False),
        sa.Column('poles_base', sa.String(length=100), nullable=False),
        sa.Column('city_poles', sa.Integer(), nullable=False),
        sa.Column('near_poles', sa.Integer(), nullable=False),
        sa.Column('near_poles_pct', sa.Float(), nullable=False),
        sa.Column('route_length_m', sa.Integer(), nullable=False),
        sa.Column('avg_span_m', sa.Float(), nullable=False),
        sa.Column('poles_kmz', sa.LargeBinary(), nullable=False),
        sa.Column('all_poles_kmz', sa.LargeBinary(), nullable=True),
        sa.Column('overlap_kmz', sa.LargeBinary(), nullable=True),
        sa.Column('with_overlap_kmz', sa.LargeBinary(), nullable=True),
        sa.Column('without_overlap_kmz', sa.LargeBinary(), nullable=True),
        sa.Column('backbone_id', sa.Uuid(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['backbone_id'], ['backbones.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('backbone_id', 'ibge_code'),
    )
    op.create_index(
        op.f('ix_backbone_cities_backbone_id'),
        'backbone_cities',
        ['backbone_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_backbone_cities_ibge_code'),
        'backbone_cities',
        ['ibge_code'],
        unique=False,
    )
    op.create_table(
        'backbone_cable_types',
        sa.Column('cable_type', sa.String(length=50), nullable=False),
        sa.Column('cables', sa.Integer(), nullable=False),
        sa.Column('length_m', sa.Integer(), nullable=False),
        sa.Column('near_poles', sa.Integer(), nullable=False),
        sa.Column('backbone_city_id', sa.Uuid(), nullable=False),
        sa.Column('unique_length_m', sa.Integer(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['backbone_city_id'], ['backbone_cities.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_backbone_cable_types_backbone_city_id'),
        'backbone_cable_types',
        ['backbone_city_id'],
        unique=False,
    )
    op.create_table(
        'backbone_cables',
        sa.Column('folder', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('cable_type', sa.String(length=50), nullable=False),
        sa.Column('length_m', sa.Float(), nullable=False),
        sa.Column('near_poles', sa.Integer(), nullable=False),
        sa.Column('near_poles_5m', sa.Integer(), nullable=False),
        sa.Column('no_pole_m', sa.Integer(), nullable=False),
        sa.Column('backbone_city_id', sa.Uuid(), nullable=False),
        sa.Column('unique_length_m', sa.Float(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column(
            'created_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.Column(
            'updated_at',
            sa.DateTime(),
            server_default=sa.text('now()'),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ['backbone_city_id'], ['backbone_cities.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_backbone_cables_backbone_city_id'),
        'backbone_cables',
        ['backbone_city_id'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_backbone_cables_backbone_city_id'),
        table_name='backbone_cables',
    )
    op.drop_table('backbone_cables')
    op.drop_index(
        op.f('ix_backbone_cable_types_backbone_city_id'),
        table_name='backbone_cable_types',
    )
    op.drop_table('backbone_cable_types')
    op.drop_index(
        op.f('ix_backbone_cities_ibge_code'), table_name='backbone_cities'
    )
    op.drop_index(
        op.f('ix_backbone_cities_backbone_id'), table_name='backbone_cities'
    )
    op.drop_table('backbone_cities')
    op.drop_index(op.f('ix_backbones_backbone_date'), table_name='backbones')
    op.drop_table('backbones')
