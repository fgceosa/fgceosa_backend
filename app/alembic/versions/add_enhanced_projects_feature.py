"""add enhanced projects feature with organizations and full RBAC

Revision ID: add_enhanced_projects
Revises:
Create Date: 2025-01-26

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_enhanced_projects'
down_revision = '88257c6a1c9c'  # Latest revision: Add TopUp and APIKey models
branch_labels = None
depends_on = None


def upgrade():
    """
    Upgrade database schema to support enhanced projects feature.

    Changes:
    1. Create Organization table
    2. Create OrganizationMember table
    3. Enhance Project table with new fields
    4. Add project relationship to APIKey table
    """

    # ==================== Create Organization Table ====================
    op.create_table(
        'organization',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(255), nullable=False, index=True),
        sa.Column('description', sa.String(500), nullable=True),
        sa.Column('owner_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['user.id'], ondelete='CASCADE'),
    )

    # ==================== Create OrganizationMember Table ====================
    op.create_table(
        'organization_member',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organization_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('role', sa.String(50), nullable=False, server_default='member'),
        sa.Column('joined_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organization.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
    )

    # ==================== Enhance Project Table ====================
    # Add new columns to existing project table
    op.add_column('project', sa.Column('type', sa.String(50), nullable=False, server_default='other'))
    op.add_column('project', sa.Column('status', sa.String(50), nullable=False, server_default='in_development'))
    op.add_column('project', sa.Column('project_url', sa.String(500), nullable=True))
    op.add_column('project', sa.Column('org_id', postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column('project', sa.Column('api_key_id', postgresql.UUID(as_uuid=True), nullable=True, unique=True))
    op.add_column('project', sa.Column('is_deleted', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('project', sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True))

    # Rename user_id to owner_user_id for clarity
    op.alter_column('project', 'user_id', new_column_name='owner_user_id')

    # Add foreign key constraints
    op.create_foreign_key(
        'fk_project_org_id',
        'project',
        'organization',
        ['org_id'],
        ['id'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'fk_project_api_key_id',
        'project',
        'apikey',
        ['api_key_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # ==================== Update Project Indexes ====================
    # Use IF NOT EXISTS to handle cases where indexes might already exist
    op.execute('CREATE INDEX IF NOT EXISTS ix_project_owner_user_id ON project (owner_user_id)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_project_type ON project (type)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_project_status ON project (status)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_project_is_deleted ON project (is_deleted)')


def downgrade():
    """
    Downgrade database schema (revert changes).

    Warning: This will drop organization tables and remove project enhancements.
    """

    # ==================== Revert Project Table ====================
    # Drop indexes
    op.execute('DROP INDEX IF EXISTS ix_project_is_deleted')
    op.execute('DROP INDEX IF EXISTS ix_project_status')
    op.execute('DROP INDEX IF EXISTS ix_project_type')
    op.execute('DROP INDEX IF EXISTS ix_project_owner_user_id')

    # Drop foreign keys
    op.drop_constraint('fk_project_api_key_id', 'project', type_='foreignkey')
    op.drop_constraint('fk_project_org_id', 'project', type_='foreignkey')

    # Rename owner_user_id back to user_id
    op.alter_column('project', 'owner_user_id', new_column_name='user_id')

    # Drop new columns
    op.drop_column('project', 'deleted_at')
    op.drop_column('project', 'is_deleted')
    op.drop_column('project', 'api_key_id')
    op.drop_column('project', 'org_id')
    op.drop_column('project', 'project_url')
    op.drop_column('project', 'status')
    op.drop_column('project', 'type')

    # ==================== Drop OrganizationMember Table ====================
    op.drop_table('organization_member')

    # ==================== Drop Organization Table ====================
    op.drop_table('organization')
