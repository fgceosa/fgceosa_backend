"""Add dashboard models - Project, APIRequest, CreditTransaction

Revision ID: add_dashboard_models
Revises: drop_item_table
Create Date: 2024-10-29 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = 'add_dashboard_models'
down_revision = 'drop_item_table'
branch_labels = None
depends_on = None


def upgrade():
    # Create project table
    op.create_table('project',
        sa.Column('id', postgresql.UUID(as_uuid=True), default=uuid.uuid4, nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_project_name'), 'project', ['name'], unique=False)

    # Create apirequest table
    op.create_table('apirequest',
        sa.Column('id', postgresql.UUID(as_uuid=True), default=uuid.uuid4, nullable=False),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('endpoint', sa.String(length=255), nullable=False),
        sa.Column('request_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('response_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost', sa.Numeric(precision=10, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='success'),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['project_id'], ['project.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_apirequest_model'), 'apirequest', ['model'], unique=False)
    op.create_index(op.f('ix_apirequest_created_at'), 'apirequest', ['created_at'], unique=False)

    # Create credittransaction table
    op.create_table('credittransaction',
        sa.Column('id', postgresql.UUID(as_uuid=True), default=uuid.uuid4, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('transaction_type', sa.String(length=50), nullable=False),
        sa.Column('description', sa.String(length=500), nullable=True),
        sa.Column('reference_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_credittransaction_user_id'), 'credittransaction', ['user_id'], unique=False)
    op.create_index(op.f('ix_credittransaction_transaction_type'), 'credittransaction', ['transaction_type'], unique=False)
    op.create_index(op.f('ix_credittransaction_created_at'), 'credittransaction', ['created_at'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_credittransaction_created_at'), table_name='credittransaction')
    op.drop_index(op.f('ix_credittransaction_transaction_type'), table_name='credittransaction')
    op.drop_index(op.f('ix_credittransaction_user_id'), table_name='credittransaction')
    op.drop_table('credittransaction')
    
    op.drop_index(op.f('ix_apirequest_created_at'), table_name='apirequest')
    op.drop_index(op.f('ix_apirequest_model'), table_name='apirequest')
    op.drop_table('apirequest')
    
    op.drop_index(op.f('ix_project_name'), table_name='project')
    op.drop_table('project')
