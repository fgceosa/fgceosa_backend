#!/usr/bin/env python3
"""
Fix Alembic database state by handling orphaned migrations.

This script resets the alembic_version table to match the codebase.
"""

import os
import sys
from pathlib import Path

# Add app to path
sys.path.insert(0, str(Path(__file__).parent.parent))

def main():
    """Reset alembic state and upgrade to head."""
    import subprocess
    from sqlalchemy import create_engine, text

    # Get database URL from environment
    db_user = os.getenv("POSTGRES_USER")
    db_pass = os.getenv("POSTGRES_PASSWORD")
    db_host = os.getenv("POSTGRES_SERVER")
    db_port = os.getenv("POSTGRES_PORT", "5432")
    db_name = os.getenv("POSTGRES_DB")

    if not all([db_user, db_pass, db_host, db_name]):
        print("❌ Error: Database environment variables not set")
        sys.exit(1)

    database_url = f"postgresql://{db_user}:{db_pass}@{db_host}:{db_port}/{db_name}"

    print("="*60)
    print("Alembic State Fix Script")
    print("="*60)

    try:
        engine = create_engine(database_url)

        with engine.connect() as conn:
            # Check current alembic_version
            print("\n📋 Checking current database migration state...")
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            current_versions = [row[0] for row in result]

            if current_versions:
                print(f"Current migrations in database: {current_versions}")
            else:
                print("No migrations found in database")

            # Clear alembic_version table
            print("\n🔧 Clearing alembic_version table...")
            conn.execute(text("DELETE FROM alembic_version"))
            conn.commit()
            print("✓ Alembic version table cleared")

        # Now use alembic to stamp and upgrade
        print("\n📌 Stamping database with merge point...")

        # Try to stamp with the merge head
        result = subprocess.run(
            ["alembic", "stamp", "f9664f1acfcf"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print(f"Warning: Stamp failed: {result.stderr}")
            print("Trying to stamp with base...")
            subprocess.run(["alembic", "stamp", "base"], check=True)
        else:
            print("✓ Database stamped successfully")

        # Now upgrade to head
        print("\n⬆️  Upgrading to latest migration...")
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            capture_output=True,
            text=True
        )

        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)

        if result.returncode == 0:
            print("\n✅ Migration completed successfully!")
        else:
            print("\n❌ Migration failed")
            sys.exit(1)

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
