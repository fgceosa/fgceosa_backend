"""Add RBAC tables and user roles

Revision ID: add_rbac_tables
Revises: 1a31ce608336
Create Date: 2024-10-07 15:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

# revision identifiers, used by Alembic.
revision = 'add_rbac_tables'
down_revision = '1a31ce608336'
branch_labels = None
depends_on = None


def upgrade():
    # Create role table
    op.create_table('role',
        sa.Column('id', postgresql.UUID(as_uuid=True), default=uuid.uuid4, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_role_name'), 'role', ['name'], unique=False)

    # Create permission table
    op.create_table('permission',
        sa.Column('id', postgresql.UUID(as_uuid=True), default=uuid.uuid4, nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('description', sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_permission_name'), 'permission', ['name'], unique=False)

    # Create userrole table (junction table between user and role)
    op.create_table('userrole',
        sa.Column('id', postgresql.UUID(as_uuid=True), default=uuid.uuid4, nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(['role_id'], ['role.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create rolepermission table (junction table between role and permission)
    op.create_table('rolepermission',
        sa.Column('id', postgresql.UUID(as_uuid=True), default=uuid.uuid4, nullable=False),
        sa.Column('role_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('permission_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('allowed', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['permission_id'], ['permission.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['role_id'], ['role.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('rolepermission')
    op.drop_table('userrole')
    op.drop_index(op.f('ix_permission_name'), table_name='permission')
    op.drop_table('permission')
    op.drop_index(op.f('ix_role_name'), table_name='role')
    op.drop_table('role')