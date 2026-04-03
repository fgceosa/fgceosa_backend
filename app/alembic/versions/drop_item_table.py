"""Drop item table - remove item CRUD functionality

Revision ID: drop_item_table
Revises: add_rbac_tables
Create Date: 2024-10-07 23:20:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'drop_item_table'
down_revision = 'add_rbac_tables'
branch_labels = None
depends_on = None


def upgrade():
    # Drop the item table as we're removing item CRUD functionality
    op.drop_table('item')


def downgrade():
    # Recreate item table if we need to rollback
    op.create_table('item',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )