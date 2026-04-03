"""add invited email to workspace member

Revision ID: 7f803748390a
Revises: 6e602637289f
Create Date: 2026-02-04 13:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision = '7f803748390a'
down_revision = '6e602637289f'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('workspace_member', sa.Column('invited_email', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True))
    op.create_index(op.f('ix_workspace_member_invited_email'), 'workspace_member', ['invited_email'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_workspace_member_invited_email'), table_name='workspace_member')
    op.drop_column('workspace_member', 'invited_email')
