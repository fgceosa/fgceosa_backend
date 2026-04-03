"""add_copilot_hub_tables

Revision ID: add_copilot_hub_tables
Revises: b695c2f86266
Create Date: 2025-12-10

This migration creates all tables for the Copilot Hub feature:
- copilot: Main agent/copilot configuration
- copilot_conversation: Conversation threads
- copilot_message: Individual messages
- copilot_document: Uploaded documents for RAG
- copilot_document_chunk: Document chunks with embeddings
- copilot_tool: Tool configurations
- copilot_tool_execution: Tool execution logs
- copilot_execution: Long-running execution tracking
"""
from alembic import op
import sqlalchemy as sa
import sqlmodel.sql.sqltypes
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision = 'add_copilot_hub_tables'
down_revision = 'b695c2f86266'
branch_labels = None
depends_on = None


def upgrade():
    # Enable pgvector extension
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')

    # Create copilot table
    op.create_table('copilot',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('avatar', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column('category', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('visibility', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('tags', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('model', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('temperature', sa.Float(), nullable=False),
        sa.Column('max_tokens', sa.Integer(), nullable=False),
        sa.Column('top_p', sa.Float(), nullable=False),
        sa.Column('frequency_penalty', sa.Float(), nullable=False),
        sa.Column('presence_penalty', sa.Float(), nullable=False),
        sa.Column('stop_sequences', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('welcome_message', sa.Text(), nullable=True),
        sa.Column('suggested_prompts', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('capabilities', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('allow_file_uploads', sa.Boolean(), nullable=False),
        sa.Column('allow_web_search', sa.Boolean(), nullable=False),
        sa.Column('allow_code_execution', sa.Boolean(), nullable=False),
        sa.Column('memory_enabled', sa.Boolean(), nullable=False),
        sa.Column('memory_window_size', sa.Integer(), nullable=False),
        sa.Column('tools_config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('created_by', sa.Uuid(), nullable=False),
        sa.Column('workspace_id', sa.Uuid(), nullable=True),
        sa.Column('usage_count', sa.Integer(), nullable=False),
        sa.Column('rating', sa.Float(), nullable=True),
        sa.Column('is_featured', sa.Boolean(), nullable=False),
        sa.Column('is_official', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['user.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspace.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_name'), 'copilot', ['name'], unique=False)
    op.create_index(op.f('ix_copilot_category'), 'copilot', ['category'], unique=False)
    op.create_index(op.f('ix_copilot_status'), 'copilot', ['status'], unique=False)
    op.create_index(op.f('ix_copilot_visibility'), 'copilot', ['visibility'], unique=False)
    op.create_index(op.f('ix_copilot_created_by'), 'copilot', ['created_by'], unique=False)
    op.create_index(op.f('ix_copilot_created_at'), 'copilot', ['created_at'], unique=False)

    # Create copilot_conversation table
    op.create_table('copilot_conversation',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('copilot_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('context', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('memory_summary', sa.Text(), nullable=True),
        sa.Column('message_count', sa.Integer(), nullable=False),
        sa.Column('total_tokens_used', sa.Integer(), nullable=False),
        sa.Column('total_cost', sa.Numeric(precision=12, scale=4), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('last_message_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['copilot_id'], ['copilot.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_conversation_copilot_id'), 'copilot_conversation', ['copilot_id'], unique=False)
    op.create_index(op.f('ix_copilot_conversation_user_id'), 'copilot_conversation', ['user_id'], unique=False)
    op.create_index(op.f('ix_copilot_conversation_created_at'), 'copilot_conversation', ['created_at'], unique=False)

    # Create copilot_message table
    op.create_table('copilot_message',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('role', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('tool_calls', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('tool_call_id', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('attachments', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('model_used', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('tokens_used', sa.Integer(), nullable=True),
        sa.Column('cost', sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column('response_time_ms', sa.Integer(), nullable=True),
        sa.Column('feedback_rating', sa.Integer(), nullable=True),
        sa.Column('feedback_comment', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['copilot_conversation.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_message_conversation_id'), 'copilot_message', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_copilot_message_role'), 'copilot_message', ['role'], unique=False)
    op.create_index(op.f('ix_copilot_message_created_at'), 'copilot_message', ['created_at'], unique=False)

    # Create copilot_document table
    op.create_table('copilot_document',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('copilot_id', sa.Uuid(), nullable=False),
        sa.Column('uploaded_by', sa.Uuid(), nullable=False),
        sa.Column('filename', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column('original_filename', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=False),
        sa.Column('file_type', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('file_size', sa.Integer(), nullable=False),
        sa.Column('file_url', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('title', sqlmodel.sql.sqltypes.AutoString(length=500), nullable=True),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('total_chunks', sa.Integer(), nullable=False),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('processing_started_at', sa.DateTime(), nullable=True),
        sa.Column('processing_completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['copilot_id'], ['copilot.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['uploaded_by'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_document_copilot_id'), 'copilot_document', ['copilot_id'], unique=False)
    op.create_index(op.f('ix_copilot_document_status'), 'copilot_document', ['status'], unique=False)
    op.create_index(op.f('ix_copilot_document_created_at'), 'copilot_document', ['created_at'], unique=False)

    # Create copilot_document_chunk table with vector embedding
    op.create_table('copilot_document_chunk',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('start_char', sa.Integer(), nullable=True),
        sa.Column('end_char', sa.Integer(), nullable=True),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('section', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['copilot_document.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_document_chunk_document_id'), 'copilot_document_chunk', ['document_id'], unique=False)

    # Create vector similarity index for efficient search
    op.execute('''
        CREATE INDEX ix_copilot_document_chunk_embedding
        ON copilot_document_chunk
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
    ''')

    # Create copilot_tool table
    op.create_table('copilot_tool',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('copilot_id', sa.Uuid(), nullable=False),
        sa.Column('name', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=False),
        sa.Column('description', sqlmodel.sql.sqltypes.AutoString(length=1000), nullable=False),
        sa.Column('tool_type', sqlmodel.sql.sqltypes.AutoString(length=50), nullable=False),
        sa.Column('parameters_schema', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('config', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('is_enabled', sa.Boolean(), nullable=False),
        sa.Column('requires_confirmation', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['copilot_id'], ['copilot.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_tool_copilot_id'), 'copilot_tool', ['copilot_id'], unique=False)
    op.create_index(op.f('ix_copilot_tool_name'), 'copilot_tool', ['name'], unique=False)
    op.create_index(op.f('ix_copilot_tool_tool_type'), 'copilot_tool', ['tool_type'], unique=False)

    # Create copilot_tool_execution table
    op.create_table('copilot_tool_execution',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('tool_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('message_id', sa.Uuid(), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('input_params', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('output_result', postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['copilot_conversation.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['message_id'], ['copilot_message.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['tool_id'], ['copilot_tool.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_tool_execution_tool_id'), 'copilot_tool_execution', ['tool_id'], unique=False)
    op.create_index(op.f('ix_copilot_tool_execution_conversation_id'), 'copilot_tool_execution', ['conversation_id'], unique=False)
    op.create_index(op.f('ix_copilot_tool_execution_status'), 'copilot_tool_execution', ['status'], unique=False)
    op.create_index(op.f('ix_copilot_tool_execution_created_at'), 'copilot_tool_execution', ['created_at'], unique=False)

    # Create copilot_execution table for long-running tasks
    op.create_table('copilot_execution',
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('copilot_id', sa.Uuid(), nullable=False),
        sa.Column('conversation_id', sa.Uuid(), nullable=False),
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('celery_task_id', sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True),
        sa.Column('status', sqlmodel.sql.sqltypes.AutoString(length=20), nullable=False),
        sa.Column('input_message', sa.Text(), nullable=False),
        sa.Column('output_response', sa.Text(), nullable=True),
        sa.Column('model_used', sqlmodel.sql.sqltypes.AutoString(length=100), nullable=True),
        sa.Column('total_tokens', sa.Integer(), nullable=False),
        sa.Column('total_cost', sa.Numeric(precision=10, scale=6), nullable=False),
        sa.Column('error_message', sqlmodel.sql.sqltypes.AutoString(length=2000), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('execution_time_ms', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['copilot_id'], ['copilot.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['conversation_id'], ['copilot_conversation.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['user.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_copilot_execution_copilot_id'), 'copilot_execution', ['copilot_id'], unique=False)
    op.create_index(op.f('ix_copilot_execution_user_id'), 'copilot_execution', ['user_id'], unique=False)
    op.create_index(op.f('ix_copilot_execution_status'), 'copilot_execution', ['status'], unique=False)
    op.create_index(op.f('ix_copilot_execution_celery_task_id'), 'copilot_execution', ['celery_task_id'], unique=False)
    op.create_index(op.f('ix_copilot_execution_created_at'), 'copilot_execution', ['created_at'], unique=False)


def downgrade():
    # Drop tables in reverse order
    op.drop_index(op.f('ix_copilot_execution_created_at'), table_name='copilot_execution')
    op.drop_index(op.f('ix_copilot_execution_celery_task_id'), table_name='copilot_execution')
    op.drop_index(op.f('ix_copilot_execution_status'), table_name='copilot_execution')
    op.drop_index(op.f('ix_copilot_execution_user_id'), table_name='copilot_execution')
    op.drop_index(op.f('ix_copilot_execution_copilot_id'), table_name='copilot_execution')
    op.drop_table('copilot_execution')

    op.drop_index(op.f('ix_copilot_tool_execution_created_at'), table_name='copilot_tool_execution')
    op.drop_index(op.f('ix_copilot_tool_execution_status'), table_name='copilot_tool_execution')
    op.drop_index(op.f('ix_copilot_tool_execution_conversation_id'), table_name='copilot_tool_execution')
    op.drop_index(op.f('ix_copilot_tool_execution_tool_id'), table_name='copilot_tool_execution')
    op.drop_table('copilot_tool_execution')

    op.drop_index(op.f('ix_copilot_tool_tool_type'), table_name='copilot_tool')
    op.drop_index(op.f('ix_copilot_tool_name'), table_name='copilot_tool')
    op.drop_index(op.f('ix_copilot_tool_copilot_id'), table_name='copilot_tool')
    op.drop_table('copilot_tool')

    op.execute('DROP INDEX IF EXISTS ix_copilot_document_chunk_embedding')
    op.drop_index(op.f('ix_copilot_document_chunk_document_id'), table_name='copilot_document_chunk')
    op.drop_table('copilot_document_chunk')

    op.drop_index(op.f('ix_copilot_document_created_at'), table_name='copilot_document')
    op.drop_index(op.f('ix_copilot_document_status'), table_name='copilot_document')
    op.drop_index(op.f('ix_copilot_document_copilot_id'), table_name='copilot_document')
    op.drop_table('copilot_document')

    op.drop_index(op.f('ix_copilot_message_created_at'), table_name='copilot_message')
    op.drop_index(op.f('ix_copilot_message_role'), table_name='copilot_message')
    op.drop_index(op.f('ix_copilot_message_conversation_id'), table_name='copilot_message')
    op.drop_table('copilot_message')

    op.drop_index(op.f('ix_copilot_conversation_created_at'), table_name='copilot_conversation')
    op.drop_index(op.f('ix_copilot_conversation_user_id'), table_name='copilot_conversation')
    op.drop_index(op.f('ix_copilot_conversation_copilot_id'), table_name='copilot_conversation')
    op.drop_table('copilot_conversation')

    op.drop_index(op.f('ix_copilot_created_at'), table_name='copilot')
    op.drop_index(op.f('ix_copilot_created_by'), table_name='copilot')
    op.drop_index(op.f('ix_copilot_visibility'), table_name='copilot')
    op.drop_index(op.f('ix_copilot_status'), table_name='copilot')
    op.drop_index(op.f('ix_copilot_category'), table_name='copilot')
    op.drop_index(op.f('ix_copilot_name'), table_name='copilot')
    op.drop_table('copilot')
