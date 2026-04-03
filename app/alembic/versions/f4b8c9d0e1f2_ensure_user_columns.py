"""ensure all user columns exist

Revision ID: f4b8c9d0e1f2
Revises: 6e602637289f
Create Date: 2026-02-03 09:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'f4b8c9d0e1f2'
down_revision = '6e602637289f'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    tables = inspector.get_table_names()
    
    # 1. Ensure User columns exist
    if 'user' in tables:
        columns = [c['name'] for c in inspector.get_columns('user')]
        
        # List of columns to ensure
        columns_to_add = [
            ('tag_number', sa.Column('tag_number', sa.String(length=50), nullable=True)),
            ('first_name', sa.Column('first_name', sa.String(length=150), nullable=True)),
            ('last_name', sa.Column('last_name', sa.String(length=150), nullable=True)),
            ('phone', sa.Column('phone', sa.String(length=50), nullable=True)),
            ('state', sa.Column('state', sa.String(length=255), nullable=True)),
            ('avatar', sa.Column('avatar', sa.String(length=500), nullable=True)),
            ('username', sa.Column('username', sa.String(length=150), nullable=True)),
            ('phone_number', sa.Column('phone_number', sa.String(length=50), nullable=True)),
            ('dial_code', sa.Column('dial_code', sa.String(length=10), nullable=True)),
            ('auth_provider', sa.Column('auth_provider', sa.String(length=20), nullable=False, server_default='password')),
            ('address', sa.Column('address', sa.String(length=500), nullable=True)),
            ('postcode', sa.Column('postcode', sa.String(length=50), nullable=True)),
            ('city', sa.Column('city', sa.String(length=255), nullable=True)),
            ('country', sa.Column('country', sa.String(length=255), nullable=True)),
            ('timezone', sa.Column('timezone', sa.String(length=100), nullable=True)),
            ('credits', sa.Column('credits', sa.Numeric(precision=12, scale=4), nullable=False, server_default='0.0000')),
            ('status', sa.Column('status', sa.String(length=20), nullable=False, server_default='active')),
            ('last_login', sa.Column('last_login', sa.DateTime(), nullable=True)),
            ('account_type', sa.Column('account_type', sa.String(length=50), nullable=False, server_default='individual')),
            ('organization_name', sa.Column('organization_name', sa.String(length=255), nullable=True)),
            ('accepted_terms_at', sa.Column('accepted_terms_at', sa.DateTime(), nullable=True)),
            ('created_at', sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'))),
            ('updated_at', sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()'))),
        ]
        
        for col_name, col_obj in columns_to_add:
            if col_name not in columns:
                op.add_column('user', col_obj)
                
        indices = [i['name'] for i in inspector.get_indexes('user')]
        if 'ix_user_username' not in indices and 'username' in [c['name'] for c in inspector.get_columns('user')]:
            op.create_index(op.f('ix_user_username'), 'user', ['username'], unique=False)
        if 'ix_user_tag_number' not in indices and 'tag_number' in [c['name'] for c in inspector.get_columns('user')]:
            op.create_index(op.f('ix_user_tag_number'), 'user', ['tag_number'], unique=True)


def downgrade():
    pass
