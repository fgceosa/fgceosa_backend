"""refactor wallet to org level

Revision ID: refactor_wallet
Revises: add_org_id_to_role
Create Date: 2026-01-18 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'refactor_wallet'
down_revision = 'add_org_id_to_role'
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add credits_balance to organization table
    op.add_column('organization', sa.Column('credits_balance', sa.Numeric(precision=12, scale=4), nullable=False, server_default='0.0000'))
    
    # 2. Add monthly_credit_limit to workspace table
    op.add_column('workspace', sa.Column('monthly_credit_limit', sa.Numeric(precision=12, scale=4), nullable=False, server_default='0.0000'))
    
    # 3. Create organization_credit_transaction table
    op.create_table('organization_credit_transaction',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('balance_after', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('transaction_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column('workspace_id', sa.Uuid(), nullable=True),
        sa.Column('performed_by', sa.Uuid(), nullable=True),
        sa.Column('reference_id', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['performed_by'], ['user.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_organization_credit_transaction_organization_id'), 'organization_credit_transaction', ['organization_id'], unique=False)
    op.create_index(op.f('ix_organization_credit_transaction_transaction_type'), 'organization_credit_transaction', ['transaction_type'], unique=False)
    op.create_index(op.f('ix_organization_credit_transaction_workspace_id'), 'organization_credit_transaction', ['workspace_id'], unique=False)
    op.create_index(op.f('ix_organization_credit_transaction_created_at'), 'organization_credit_transaction', ['created_at'], unique=False)

    # 4. Create workspace_usage_tracking table
    op.create_table('workspace_usage_tracking',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('billing_period_start', sa.DateTime(), nullable=False),
        sa.Column('billing_period_end', sa.DateTime(), nullable=False),
        sa.Column('total_usage', sa.Numeric(precision=12, scale=4), nullable=False, server_default='0.0000'),
        sa.Column('usage_breakdown', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('workspace_id', 'billing_period_start', name='unique_workspace_period_usage')
    )
    op.create_index(op.f('ix_workspace_usage_tracking_organization_id'), 'workspace_usage_tracking', ['organization_id'], unique=False)
    op.create_index(op.f('ix_workspace_usage_tracking_workspace_id'), 'workspace_usage_tracking', ['workspace_id'], unique=False)


def downgrade():
    # Drop workspace_usage_tracking
    op.drop_index(op.f('ix_workspace_usage_tracking_workspace_id'), table_name='workspace_usage_tracking')
    op.drop_index(op.f('ix_workspace_usage_tracking_organization_id'), table_name='workspace_usage_tracking')
    op.drop_table('workspace_usage_tracking')

    # Drop organization_credit_transaction
    op.drop_index(op.f('ix_organization_credit_transaction_created_at'), table_name='organization_credit_transaction')
    op.drop_index(op.f('ix_organization_credit_transaction_workspace_id'), table_name='organization_credit_transaction')
    op.drop_index(op.f('ix_organization_credit_transaction_transaction_type'), table_name='organization_credit_transaction')
    op.drop_index(op.f('ix_organization_credit_transaction_organization_id'), table_name='organization_credit_transaction')
    op.drop_table('organization_credit_transaction')

    # Drop columns
    op.drop_column('workspace', 'monthly_credit_limit')
    op.drop_column('organization', 'credits_balance')
