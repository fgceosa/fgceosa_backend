"""merge heads

Revision ID: a8283c31fc96
Revises: 070ca04fb75a, a1b2c3d4e5f6
Create Date: 2026-05-22 17:14:56.632631

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'a8283c31fc96'
down_revision = ('070ca04fb75a', 'a1b2c3d4e5f6')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
