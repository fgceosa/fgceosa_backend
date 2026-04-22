"""add user registration fields

Revision ID: 2ff9d79e209
Revises: 1eff9d79e209
Create Date: 2026-04-03 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision = '2ff9d79e209'
down_revision = '1eff9d79e209'
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Add new columns to the user table
    op.add_column('user', sa.Column('nickname', sa.String(length=150), nullable=True))
    op.add_column('user', sa.Column('alternative_email', sa.String(length=255), nullable=True))
    op.add_column('user', sa.Column('gender', sa.String(length=50), nullable=True))
    op.add_column('user', sa.Column('fgce_set', sa.String(length=50), nullable=True))
    op.add_column('user', sa.Column('fgce_house', sa.String(length=150), nullable=True))

def downgrade() -> None:
    # Remove the columns from the user table
    op.drop_column('user', 'fgce_house')
    op.drop_column('user', 'fgce_set')
    op.drop_column('user', 'gender')
    op.drop_column('user', 'alternative_email')
    op.drop_column('user', 'nickname')
