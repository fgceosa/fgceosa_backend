"""fix credit transfer cascade

Revision ID: fix_credit_transfer_cascade
Revises: refactor_wallet
Create Date: 2026-01-19 17:35:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision = 'fix_credit_transfer_cascade'
down_revision = 'refactor_wallet'
branch_labels = None
depends_on = None

def upgrade():
    # Use reflection to find the constraint name if possible, or assume generic naming if widely used.
    # Postgres usually names them: table_column_fkey.
    # credit_transfer_sender_id_fkey
    # credit_transfer_recipient_id_fkey
    
    # We will try to drop them with expected names.
    # If using SQLite (locally), foreign keys are different.
    # But this project seems to use Postgres (Postgres types).
    
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    fk_constraints = inspector.get_foreign_keys('credit_transfer')
    
    sender_constraint = None
    recipient_constraint = None
    
    for fk in fk_constraints:
        if 'sender_id' in fk['constrained_columns']:
            sender_constraint = fk['name']
        if 'recipient_id' in fk['constrained_columns']:
            recipient_constraint = fk['name']
            
    if sender_constraint:
        op.drop_constraint(sender_constraint, 'credit_transfer', type_='foreignkey')
    
    if recipient_constraint:
        op.drop_constraint(recipient_constraint, 'credit_transfer', type_='foreignkey')
        
    op.create_foreign_key('fk_credit_transfer_sender_user', 'credit_transfer', 'user', ['sender_id'], ['id'], ondelete='CASCADE')
    op.create_foreign_key('fk_credit_transfer_recipient_user', 'credit_transfer', 'user', ['recipient_id'], ['id'], ondelete='CASCADE')


def downgrade():
    bind = op.get_bind()
    inspector = Inspector.from_engine(bind)
    fk_constraints = inspector.get_foreign_keys('credit_transfer')
    
    sender_constraint = None
    recipient_constraint = None
    
    for fk in fk_constraints:
        if 'sender_id' in fk['constrained_columns']:
            sender_constraint = fk['name']
        if 'recipient_id' in fk['constrained_columns']:
            recipient_constraint = fk['name']
            
    if sender_constraint:
        op.drop_constraint(sender_constraint, 'credit_transfer', type_='foreignkey')
    
    if recipient_constraint:
        op.drop_constraint(recipient_constraint, 'credit_transfer', type_='foreignkey')

    op.create_foreign_key('fk_credit_transfer_sender_user', 'credit_transfer', 'user', ['sender_id'], ['id'])
    op.create_foreign_key('fk_credit_transfer_recipient_user', 'credit_transfer', 'user', ['recipient_id'], ['id'])
