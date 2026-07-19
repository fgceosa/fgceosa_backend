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
    pass


def downgrade():
    pass
