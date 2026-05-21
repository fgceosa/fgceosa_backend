"""add receipt_url and rejection_reason to payment

Revision ID: a1b2c3d4e5f6
Revises: 0121fe057bc5
Create Date: 2026-05-21 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0121fe057bc5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add receipt_url column
    op.add_column('payment', sa.Column('receipt_url', sa.String(length=1000), nullable=True))
    # Add rejection_reason column
    op.add_column('payment', sa.Column('rejection_reason', sa.TEXT(), nullable=True))
    # Widen status column from 20 to 30 chars for 'pending_verification'
    op.alter_column('payment', 'status', type_=sa.String(length=30), existing_type=sa.String(length=20))


def downgrade() -> None:
    op.drop_column('payment', 'rejection_reason')
    op.drop_column('payment', 'receipt_url')
    op.alter_column('payment', 'status', type_=sa.String(length=20), existing_type=sa.String(length=30))
