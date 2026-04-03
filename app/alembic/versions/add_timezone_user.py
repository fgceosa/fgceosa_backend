"""Add timezone to user model

Revision ID: add_timezone_user
Revises: b066011b6f82
Create Date: 2026-01-03 01:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'add_timezone_user'
down_revision = 'b066011b6f82'
branch_labels = None
depends_on = None


def upgrade():
    # Check if column exists first to avoid errors if partially applied
    conn = op.get_bind()
    res = conn.execute(sa.text("SELECT column_name FROM information_schema.columns WHERE table_name='user' AND column_name='timezone'"))
    if not res.first():
        op.add_column('user', sa.Column('timezone', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True))


def downgrade():
    op.drop_column('user', 'timezone')
