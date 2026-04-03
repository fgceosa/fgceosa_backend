"""Add account type organization name and terms acceptance to User

Revision ID: dcca84879561
Revises: add_notifications_v2
Create Date: 2025-12-28 17:23:27.540476

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'dcca84879561'
down_revision = 'add_notifications_v2'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to user table
    op.add_column('user', sa.Column('account_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False, server_default='individual'))
    op.add_column('user', sa.Column('organization_name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True))
    op.add_column('user', sa.Column('accepted_terms_at', sa.DateTime(), nullable=True))


def downgrade():
    # Remove columns from user table
    op.drop_column('user', 'accepted_terms_at')
    op.drop_column('user', 'organization_name')
    op.drop_column('user', 'account_type')
