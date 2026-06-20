"""add style_scores to comprehension_profiles

Revision ID: 9a1f2b3c4d5e
Revises: f831bc159902
Create Date: 2026-06-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a1f2b3c4d5e'
down_revision: Union[str, Sequence[str], None] = 'f831bc159902'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the structured style-preference column (JSON dict as TEXT)."""
    op.add_column(
        'comprehension_profiles',
        sa.Column('style_scores', sa.Text(), nullable=False, server_default='{}'),
    )


def downgrade() -> None:
    """Drop style_scores (batch mode so SQLite can rewrite the table)."""
    with op.batch_alter_table('comprehension_profiles') as batch_op:
        batch_op.drop_column('style_scores')
