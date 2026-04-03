"""make_workspace_member_user_id_nullable

Revision ID: b695c2f86266
Revises: 93510c4de6e8
Create Date: 2025-12-04 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'b695c2f86266'
down_revision = '93510c4de6e8'
branch_labels = None
depends_on = None


def upgrade():
    # Make user_id nullable in workspace_member table
    # This allows inviting users who haven't registered yet
    op.alter_column('workspace_member', 'user_id',
                    existing_type=sa.UUID(),
                    nullable=True)


def downgrade():
    # Revert user_id to not nullable
    op.alter_column('workspace_member', 'user_id',
                    existing_type=sa.UUID(),
                    nullable=False)
