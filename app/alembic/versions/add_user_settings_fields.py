"""add user settings fields for profile management

Revision ID: add_user_settings_fields
Revises: add_enhanced_projects
Create Date: 2025-01-26

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_user_settings_fields'
down_revision = 'add_enhanced_projects'
branch_labels = None
depends_on = None


def upgrade():
    """
    Add user settings fields to User table.

    New fields:
    - first_name: User's first name
    - last_name: User's last name
    - phone: User's phone number
    - state: User's state/province
    - avatar: URL to user's avatar image
    - created_at: Account creation timestamp
    - updated_at: Last update timestamp
    """

    # Add new columns to user table
    op.add_column('user', sa.Column('first_name', sa.String(150), nullable=True))
    op.add_column('user', sa.Column('last_name', sa.String(150), nullable=True))
    op.add_column('user', sa.Column('phone', sa.String(50), nullable=True))
    op.add_column('user', sa.Column('state', sa.String(255), nullable=True))
    op.add_column('user', sa.Column('avatar', sa.String(500), nullable=True))
    op.add_column('user', sa.Column('created_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('user', sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))

    # Set default timestamps for existing users
    op.execute("""
        UPDATE "user"
        SET created_at = NOW(), updated_at = NOW()
        WHERE created_at IS NULL OR updated_at IS NULL
    """)

    # Make timestamps non-nullable after setting defaults
    op.alter_column('user', 'created_at', nullable=False)
    op.alter_column('user', 'updated_at', nullable=False)


def downgrade():
    """
    Remove user settings fields from User table.
    """

    # Remove new columns
    op.drop_column('user', 'updated_at')
    op.drop_column('user', 'created_at')
    op.drop_column('user', 'avatar')
    op.drop_column('user', 'state')
    op.drop_column('user', 'phone')
    op.drop_column('user', 'last_name')
    op.drop_column('user', 'first_name')
