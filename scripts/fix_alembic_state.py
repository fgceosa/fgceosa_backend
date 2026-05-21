#!/usr/bin/env python3
"""
Safe Alembic database state fix script.
Identifies and removes ONLY orphaned migration revision tracking entries from the 
alembic_version database table without touching any valid migrations.
"""

import os
import sys
import re
import subprocess
from pathlib import Path

# Add app's parent directory to path to allow importing app configs
sys.path.insert(0, str(Path(__file__).parent.parent))

def get_codebase_revisions() -> set[str]:
    """Extract revision IDs from all migration files in the codebase."""
    revisions = set()
    versions_dir = Path(__file__).parent.parent / "app" / "alembic" / "versions"
    if not versions_dir.exists():
        print(f"⚠️  Versions directory not found at: {versions_dir}")
        return revisions

    # Match: revision = '...' or revision: str = '...'
    pattern = re.compile(r"^revision\s*(?::\s*str)?\s*=\s*['\"]([^'\"]+)['\"]")

    for p in versions_dir.glob("*.py"):
        try:
            with open(p, "r", encoding="utf-8") as f:
                for line in f:
                    match = pattern.match(line.strip())
                    if match:
                        revisions.add(match.group(1))
                        break
        except Exception as e:
            print(f"Warning: Could not read {p.name}: {e}")

    return revisions

def main():
    """Find and heal orphaned database migrations dynamically."""
    from sqlalchemy import create_engine, text
    from app.core.config import settings

    # Resolve database URL
    database_url = str(settings.SQLALCHEMY_DATABASE_URI)

    print("="*60)
    print("Self-Healing Safe Alembic State Tool")
    print("="*60)

    try:
        # Get active revisions from codebase
        codebase_revs = get_codebase_revisions()
        print(f"✓ Found {len(codebase_revs)} valid migration(s) in codebase.")

        # Connect to DB and fetch applied migrations
        engine = create_engine(database_url)
        with engine.connect() as conn:
            # Check if alembic_version table exists
            table_check = conn.execute(text(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'alembic_version')"
            )).scalar()

            if not table_check:
                print("✓ No 'alembic_version' table found. A new one will be created.")
                # Run standard upgrade
                run_upgrade()
                return

            # Fetch currently applied migrations
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            db_revs = [row[0] for row in result]
            print(f"✓ Found {len(db_revs)} applied migration(s) in database: {db_revs}")

            # Identify orphans (present in DB but missing from code)
            orphans = [rev for rev in db_revs if rev not in codebase_revs]

            if not orphans:
                print("✓ No orphaned migrations detected in database.")
            else:
                print(f"⚠️  Detected {len(orphans)} orphaned migration(s): {orphans}")
                print("🔧 Healing database version tracking table...")
                for orphan in orphans:
                    conn.execute(
                        text("DELETE FROM alembic_version WHERE version_num = :val"),
                        {"val": orphan}
                    )
                    print(f"   Deleted orphaned revision entry: {orphan}")
                conn.commit()
                print("✅ Database version state successfully healed!")

        # Execute the upgrade
        run_upgrade()

    except Exception as e:
        print(f"\n❌ Error resolving Alembic state: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

def run_upgrade():
    """Execute alembic upgrade head using python module."""
    print("\n⬆️  Upgrading database to latest head...")
    result = subprocess.run(
        ["python3", "-m", "alembic", "upgrade", "head"],
        capture_output=True,
        text=True
    )

    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)

    if result.returncode == 0:
        print("\n✅ Migration completed successfully!")
    else:
        print("\n❌ Migration failed.")
        sys.exit(result.returncode)

if __name__ == "__main__":
    main()
