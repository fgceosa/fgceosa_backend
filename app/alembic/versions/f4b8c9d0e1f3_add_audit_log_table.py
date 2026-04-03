"""add audit_log table

Revision ID: f4b8c9d0e1f3
Revises: f4b8c9d0e1f2
Create Date: 2026-02-03 09:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'f4b8c9d0e1f3'
down_revision = 'f4b8c9d0e1f2'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    # Ensure audit_log table exists
    if 'audit_log' not in tables:
        op.create_table(
            'audit_log',
            sa.Column('id', sa.UUID(), nullable=False),
            sa.Column('timestamp', sa.DateTime(), nullable=False),
            sa.Column('actor_id', sa.UUID(), nullable=True),
            sa.Column('actor_name', sa.String(length=255), nullable=True),
            sa.Column('actor_role', sa.String(length=100), nullable=True),
            sa.Column('actor_type', sa.String(length=50), nullable=False, server_default='human'),
            sa.Column('action', sa.String(length=100), nullable=False),
            sa.Column('action_category', sa.String(length=100), nullable=True),
            sa.Column('target_id', sa.String(length=255), nullable=True),
            sa.Column('target_type', sa.String(length=100), nullable=True),
            sa.Column('organization_id', sa.UUID(), nullable=True),
            sa.Column('workspace_id', sa.UUID(), nullable=True),
            sa.Column('ip_address', sa.String(length=50), nullable=True),
            sa.Column('location', sa.String(length=255), nullable=True),
            sa.Column('user_agent', sa.String(length=500), nullable=True),
            sa.Column('severity', sa.String(length=20), nullable=False, server_default='low'),
            sa.Column('status', sa.String(length=20), nullable=False, server_default='success'),
            sa.Column('meta_data', sa.JSON(), nullable=False, server_default='{}'),
            sa.Column('correlation_id', sa.String(length=100), nullable=True),
            sa.Column('request_source', sa.String(length=50), nullable=False, server_default='ui'),
            sa.Column('auth_method', sa.String(length=50), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['actor_id'], ['user.id'], ondelete='SET NULL'),
        )
        op.create_index(op.f('ix_audit_log_action'), 'audit_log', ['action'], unique=False)
        op.create_index(op.f('ix_audit_log_actor_id'), 'audit_log', ['actor_id'], unique=False)
        op.create_index(op.f('ix_audit_log_correlation_id'), 'audit_log', ['correlation_id'], unique=False)
        op.create_index(op.f('ix_audit_log_organization_id'), 'audit_log', ['organization_id'], unique=False)
        op.create_index(op.f('ix_audit_log_target_id'), 'audit_log', ['target_id'], unique=False)
        op.create_index(op.f('ix_audit_log_timestamp'), 'audit_log', ['timestamp'], unique=False)
        op.create_index(op.f('ix_audit_log_workspace_id'), 'audit_log', ['workspace_id'], unique=False)


def downgrade():
    op.drop_table('audit_log')
