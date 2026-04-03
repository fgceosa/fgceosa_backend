"""Merge multiple heads

Revision ID: 0121fe057bc5
Revises: 7f803748390a, f4b8c9d0e1f3
Create Date: 2026-02-04 16:37:20.057809

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = '0121fe057bc5'
down_revision = ('7f803748390a', 'f4b8c9d0e1f3')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
