"""merge heads

Revision ID: f9664f1acfcf
Revises: add_ai_chat_001, add_dashboard_models
Create Date: 2025-11-02 14:14:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f9664f1acfcf'
down_revision = ('add_ai_chat_001', 'add_dashboard_models')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
