"""Add AI Chat tables

Revision ID: add_ai_chat_001
Revises: drop_item_table
Create Date: 2025-11-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import sqlmodel
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'add_ai_chat_001'
down_revision = 'drop_item_table'
branch_labels = None
depends_on = None


def upgrade():
    # Create ai_chats table
    op.create_table('ai_chats',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_chats_created_at'), 'ai_chats', ['created_at'], unique=False)
    op.create_index(op.f('ix_ai_chats_user_id'), 'ai_chats', ['user_id'], unique=False)
    
    # Create ai_chat_messages table
    op.create_table('ai_chat_messages',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('chat_id', sa.Uuid(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('content', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('model', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['chat_id'], ['ai_chats.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_chat_messages_chat_id'), 'ai_chat_messages', ['chat_id'], unique=False)
    op.create_index(op.f('ix_ai_chat_messages_created_at'), 'ai_chat_messages', ['created_at'], unique=False)
    op.create_index(op.f('ix_ai_chat_messages_role'), 'ai_chat_messages', ['role'], unique=False)


def downgrade():
    # Drop tables
    op.drop_index(op.f('ix_ai_chat_messages_role'), table_name='ai_chat_messages')
    op.drop_index(op.f('ix_ai_chat_messages_created_at'), table_name='ai_chat_messages')
    op.drop_index(op.f('ix_ai_chat_messages_chat_id'), table_name='ai_chat_messages')
    op.drop_table('ai_chat_messages')
    
    op.drop_index(op.f('ix_ai_chats_user_id'), table_name='ai_chats')
    op.drop_index(op.f('ix_ai_chats_created_at'), table_name='ai_chats')
    op.drop_table('ai_chats')
