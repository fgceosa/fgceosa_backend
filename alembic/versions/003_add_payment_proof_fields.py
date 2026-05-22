"""add payment proof fields

Revision ID: 003
Revises: 002
Create Date: 2026-05-22 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('payment', sa.Column('receipt_url', sqlmodel.sql.sqltypes.AutoString(), nullable=True))
    op.add_column('payment', sa.Column('rejection_reason', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('payment', 'rejection_reason')
    op.drop_column('payment', 'receipt_url')
