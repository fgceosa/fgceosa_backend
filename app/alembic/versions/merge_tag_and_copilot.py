"""merge heads

Revision ID: merge_tag_and_copilot
Revises: add_tag_number_to_user, add_copilot_hub_tables
Create Date: 2025-12-18 04:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'merge_tag_and_copilot'
down_revision = ('add_tag_number_to_user', 'add_copilot_hub_tables')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
