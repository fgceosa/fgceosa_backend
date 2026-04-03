"""add notifications and workspace support for topups

Revision ID: add_notifications_v2
Revises: merge_tag_and_copilot
Create Date: 2025-12-19 06:20:00

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_notifications_v2'
down_revision = 'merge_tag_and_copilot'
branch_labels = None
depends_on = None


def upgrade():
    # --- Notification Table ---
    op.create_table('notification',
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=1000), nullable=False),
        sa.Column('type', sa.String(length=50), nullable=False),
        sa.Column('is_read', sa.Boolean(), nullable=False),
        sa.Column('metadata_json', sa.JSON(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_notification_created_at'), 'notification', ['created_at'], unique=False)
    op.create_index(op.f('ix_notification_is_read'), 'notification', ['is_read'], unique=False)
    op.create_index(op.f('ix_notification_user_id'), 'notification', ['user_id'], unique=False)

    # --- TopUp Workspace ID ---
    op.add_column('topup', sa.Column('workspace_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_topup_workspace_id'), 'topup', ['workspace_id'], unique=False)
    op.create_foreign_key('topup_workspace_id_fkey', 'topup', 'workspace', ['workspace_id'], ['id'])

    # --- Project Created At Index ---
    op.create_index(op.f('ix_project_created_at'), 'project', ['created_at'], unique=False)

def downgrade():
    op.drop_index(op.f('ix_project_created_at'), table_name='project')
    op.drop_constraint('topup_workspace_id_fkey', 'topup', type_='foreignkey')
    op.drop_index(op.f('ix_topup_workspace_id'), table_name='topup')
    op.drop_column('topup', 'workspace_id')
    op.drop_index(op.f('ix_notification_user_id'), table_name='notification')
    op.drop_index(op.f('ix_notification_is_read'), table_name='notification')
    op.drop_index(op.f('ix_notification_created_at'), table_name='notification')
    op.drop_table('notification')
