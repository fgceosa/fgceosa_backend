"""Add domain field to Copilot model

Revision ID: a24b576829bc
Revises: a2d13ee57700
Create Date: 2026-02-20 14:19:12.550600

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes


# revision identifiers, used by Alembic.
revision = 'a24b576829bc'
down_revision = 'a2d13ee57700'
branch_labels = None
depends_on = None


def upgrade():
    # Only add the domain column. 
    # Handled with a simple check to be safe if manual fixes were applied
    
    # Check if we are interacting with the database that has the copilot schema
    # Use op.get_bind().dialect.name to check if we are on postgres
    
    # We'll use a raw SQL execution to check if column exists before adding, 
    # to avoid "column already exists" errors during prestart if it was manually added.
    
    conn = op.get_bind()
    res = conn.execute(sa.text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_schema = 'copilot' 
        AND table_name = 'copilot' 
        AND column_name = 'domain';
    """)).fetchone()
    
    if not res:
        op.add_column('copilot', sa.Column('domain', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True), schema='copilot')

def downgrade():
    op.drop_column('copilot', 'domain', schema='copilot')
