"""create oauth connection table

Revision ID: 002
Revises: 001
Create Date: 2025-12-16

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import sqlmodel

# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create oauth_connection table
    op.create_table(
        'oauth_connection',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('workspace_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('provider', sa.String(length=50), nullable=False),
        sa.Column('provider_user_id', sa.String(), nullable=True),
        sa.Column('provider_email', sa.String(), nullable=True),
        sa.Column('access_token', sa.String(length=1000), nullable=False),
        sa.Column('refresh_token', sa.String(length=1000), nullable=True),
        sa.Column('token_type', sa.String(length=50), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('scopes', sa.String(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metadata', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes
    op.create_index('ix_oauth_connection_user_id', 'oauth_connection', ['user_id'])
    op.create_index('ix_oauth_connection_workspace_id', 'oauth_connection', ['workspace_id'])
    op.create_index('ix_oauth_connection_provider', 'oauth_connection', ['provider'])
    op.create_index('ix_oauth_connection_user_provider', 'oauth_connection', ['user_id', 'provider'])


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_oauth_connection_user_provider', table_name='oauth_connection')
    op.drop_index('ix_oauth_connection_provider', table_name='oauth_connection')
    op.drop_index('ix_oauth_connection_workspace_id', table_name='oauth_connection')
    op.drop_index('ix_oauth_connection_user_id', table_name='oauth_connection')

    # Drop table
    op.drop_table('oauth_connection')
