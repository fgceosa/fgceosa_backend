#!/usr/bin/env python3
"""
Initialize Copilot Hub Database

This script creates all tables needed for the Copilot Hub feature
in the separate pgvector database (port 5433).

Run: python scripts/init_copilot_db.py
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import SQLModel
from sqlalchemy import text

from app.core.config import settings
from app.core.db import copilot_engine

# Import all copilot models to register them with SQLModel
from app.copilot.models import (
    Copilot,
    CopilotConversation,
    CopilotMessage,
    CopilotDocument,
    CopilotDocumentChunk,
    CopilotTool,
    CopilotToolExecution,
    CopilotExecution,
)


def init_copilot_database():
    """Initialize the Copilot Hub database with all required tables."""
    print(f"Connecting to Copilot database at port {settings.COPILOT_POSTGRES_PORT}...")

    # Create pgvector extension
    with copilot_engine.connect() as conn:
        print("Creating pgvector extension...")
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        conn.commit()

        # Check if extension was created
        result = conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        row = result.fetchone()
        if row:
            print(f"✓ pgvector extension v{row[0]} is installed")
        else:
            print("✗ Failed to install pgvector extension")
            return False

    # Create all tables
    print("Creating Copilot Hub tables...")
    SQLModel.metadata.create_all(copilot_engine)

    # Verify tables were created
    with copilot_engine.connect() as conn:
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            AND table_name LIKE 'copilot%'
            ORDER BY table_name
        """))
        tables = [row[0] for row in result.fetchall()]

        print(f"\n✓ Created {len(tables)} tables:")
        for table in tables:
            print(f"  - {table}")

    # Create vector index if not exists
    print("\nCreating vector similarity index...")
    with copilot_engine.connect() as conn:
        try:
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS ix_copilot_document_chunk_embedding
                ON copilot_document_chunk
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
            """))
            conn.commit()
            print("✓ Vector index created")
        except Exception as e:
            print(f"Note: Vector index may already exist or table has no data yet: {e}")

    print("\n✓ Copilot Hub database initialized successfully!")
    return True


if __name__ == "__main__":
    success = init_copilot_database()
    sys.exit(0 if success else 1)
