"""add tag_number field to user table

Revision ID: add_tag_number_to_user
Revises: add_user_settings_fields
Create Date: 2025-12-18

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_tag_number_to_user'
down_revision = 'add_user_settings_fields'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add tag_number field to User table.

    New field:
    - tag_number: Unique user tag for identification (similar to ABEG tag)
      Format: @qor123456 or qor123456
      Used for easy credit transfers and user lookup
    """

    # Add tag_number column
    op.add_column('user', sa.Column(
        'tag_number',
        sa.String(length=50),
        nullable=True,
        comment='Unique user tag for identification (e.g., @qor123456)'
    ))

    # Create unique index on tag_number
    op.create_index(
        'ix_user_tag_number',
        'user',
        ['tag_number'],
        unique=True
    )


def downgrade():
    """
    Remove tag_number field from User table.
    """

    # Drop index first
    op.drop_index('ix_user_tag_number', table_name='user')

    # Drop column
    op.drop_column('user', 'tag_number')
