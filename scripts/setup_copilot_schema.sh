#!/bin/bash

# Setup Copilot Schema and pgvector Extension
# This script should be run after the main database is created

set -e

echo "=================================="
echo "Setting up Copilot Schema..."
echo "=================================="

# Wait for database to be ready
echo "Waiting for database connection..."
sleep 2

# Run Python script to setup schema
python3 << 'EOF'
import os
import psycopg
from psycopg import sql

# Get database connection details
db_user = os.getenv("POSTGRES_USER")
db_pass = os.getenv("POSTGRES_PASSWORD")
db_host = os.getenv("POSTGRES_SERVER")
db_port = os.getenv("POSTGRES_PORT", "5432")
db_name = os.getenv("POSTGRES_DB")

# Build connection string - Render requires SSL for managed databases
conn_string = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}?sslmode=require"

print(f"Connecting to database: {db_host}:{db_port}/{db_name}")

try:
    # Connect to database
    with psycopg.connect(conn_string) as conn:
        with conn.cursor() as cur:
            # Enable pgvector extension
            print("Enabling pgvector extension...")
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            
            # Create copilot schema
            print("Creating copilot schema...")
            cur.execute("CREATE SCHEMA IF NOT EXISTS copilot;")
            
            # Grant permissions
            print("Granting permissions...")
            cur.execute(sql.SQL("GRANT ALL ON SCHEMA copilot TO {};").format(
                sql.Identifier(db_user)
            ))
            cur.execute(sql.SQL("GRANT ALL ON ALL TABLES IN SCHEMA copilot TO {};").format(
                sql.Identifier(db_user)
            ))
            cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES IN SCHEMA copilot GRANT ALL ON TABLES TO {};").format(
                sql.Identifier(db_user)
            ))
            
            # Verify setup
            cur.execute("SELECT schema_name FROM information_schema.schemata WHERE schema_name = 'copilot';")
            if cur.fetchone():
                print("✅ Copilot schema created successfully!")
            
            cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
            if cur.fetchone():
                print("✅ pgvector extension enabled successfully!")
            
        conn.commit()
        print("✅ Copilot schema setup completed!")
        
except Exception as e:
    print(f"❌ Error setting up copilot schema: {e}")
    exit(1)
EOF

echo "=================================="
echo "Copilot schema setup complete!"
echo "=================================="
