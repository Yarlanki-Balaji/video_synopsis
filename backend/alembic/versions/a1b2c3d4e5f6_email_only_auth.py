"""email_only_auth - make password_hash nullable, drop OTP tables

Revision ID: a1b2c3d4e5f6
Revises: 5fe158c1939d
Create Date: 2026-09-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '5fe158c1939d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Switch to email-only auth:
    - Make users.password_hash nullable (existing rows keep their hash; new rows have none).
    - Drop pending_signups table (OTP signup flow removed).
    - Drop password_reset_codes table (password reset flow removed).
    - Drop password_resets table (legacy token-based reset table).
    """
    # Make password_hash nullable on users table.
    # SQLite doesn't support ALTER COLUMN, so we use a batch migration.
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'password_hash',
            existing_type=sa.String(length=255),
            nullable=True,
        )

    # Drop OTP / password-reset tables (no longer needed).
    # Check existence first to make this migration safe to re-run on older DBs.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'password_reset_codes' in existing_tables:
        op.drop_index(op.f('ix_password_reset_codes_code_hash'), table_name='password_reset_codes')
        op.drop_index(op.f('ix_password_reset_codes_user_id'), table_name='password_reset_codes')
        op.drop_table('password_reset_codes')

    if 'password_resets' in existing_tables:
        op.drop_index(op.f('ix_password_resets_token_hash'), table_name='password_resets')
        op.drop_index(op.f('ix_password_resets_user_id'), table_name='password_resets')
        op.drop_table('password_resets')

    if 'pending_signups' in existing_tables:
        op.drop_index(op.f('ix_pending_signups_email'), table_name='pending_signups')
        op.drop_index(op.f('ix_pending_signups_code_hash'), table_name='pending_signups')
        op.drop_table('pending_signups')


def downgrade() -> None:
    """Restore password_hash as NOT NULL and recreate the OTP tables."""
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'password_hash',
            existing_type=sa.String(length=255),
            nullable=False,
            server_default='',
        )

    op.create_table('pending_signups',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_pending_signups_code_hash'), 'pending_signups', ['code_hash'], unique=False)
    op.create_index(op.f('ix_pending_signups_email'), 'pending_signups', ['email'], unique=True)

    op.create_table('password_reset_codes',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('code_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_password_reset_codes_code_hash'), 'password_reset_codes', ['code_hash'], unique=False)
    op.create_index(op.f('ix_password_reset_codes_user_id'), 'password_reset_codes', ['user_id'], unique=False)

    op.create_table('password_resets',
        sa.Column('id', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=32), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_password_resets_token_hash'), 'password_resets', ['token_hash'], unique=True)
    op.create_index(op.f('ix_password_resets_user_id'), 'password_resets', ['user_id'], unique=False)
