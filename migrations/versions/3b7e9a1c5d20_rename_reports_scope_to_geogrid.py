"""rename reports:read scope to geogrid:read

Revision ID: 3b7e9a1c5d20
Revises: 8c1f3e2a9d47
Create Date: 2026-09-30 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '3b7e9a1c5d20'
down_revision: Union[str, Sequence[str], None] = '8c1f3e2a9d47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Existing keys keep their access after the reports -> geogrid rename
    op.execute(
        "UPDATE api_keys "
        "SET scopes = array_replace(scopes, 'reports:read', 'geogrid:read') "
        "WHERE 'reports:read' = ANY(scopes)"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "UPDATE api_keys "
        "SET scopes = array_replace(scopes, 'geogrid:read', 'reports:read') "
        "WHERE 'geogrid:read' = ANY(scopes)"
    )
