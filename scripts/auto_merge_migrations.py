#!/usr/bin/env python3
"""
Automatically detect and merge migration branches.

This script prevents the "multiple heads" issue by automatically creating
merge migrations when branches are detected.
"""

import subprocess
import sys
from datetime import datetime
from pathlib import Path


def run_command(cmd, capture=True):
    """Run a command and return output."""
    try:
        if capture:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                check=False
            )
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        else:
            return subprocess.run(cmd, shell=True, check=False).returncode, "", ""
    except Exception as e:
        return 1, "", str(e)


def get_heads():
    """Get all current migration heads."""
    code, stdout, stderr = run_command("alembic heads")

    if code != 0:
        print(f"❌ Error getting heads: {stderr}")
        return []

    # Parse heads from output
    heads = []
    for line in stdout.split('\n'):
        if line.strip():
            # Extract revision ID (first part before space or arrow)
            parts = line.split()
            if parts:
                revision = parts[0]
                if revision and revision != "Rev:":
                    heads.append(revision)

    return heads


def check_for_orphaned_migrations():
    """Check if there are any migrations in code not in database."""
    print("\n📋 Checking for migration consistency...")

    code, stdout, stderr = run_command("alembic current")

    if code != 0 and "Can't locate revision" in stderr:
        print("⚠️  Warning: Database has orphaned migrations")
        print("Run 'python scripts/fix_alembic_state.py' to fix this")
        return False

    return True


def create_merge_migration(heads):
    """Create a merge migration for all heads."""
    print(f"\n🔨 Creating merge migration for {len(heads)} heads...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    message = f"auto_merge_heads_{timestamp}"

    # Create merge migration
    cmd = f'alembic merge -m "{message}" heads'
    code, stdout, stderr = run_command(cmd)

    if code == 0:
        print("✅ Merge migration created successfully!")
        print(stdout)
        return True
    else:
        print(f"❌ Failed to create merge migration: {stderr}")
        return False


def main():
    """Main function."""
    print("="*60)
    print("Automatic Migration Merge Tool")
    print("="*60)

    # Check if we're in the right directory
    if not Path("alembic.ini").exists():
        print("❌ Error: alembic.ini not found. Run from project root.")
        sys.exit(1)

    # Check for orphaned migrations first
    if not check_for_orphaned_migrations():
        print("\n⚠️  Fix orphaned migrations before proceeding")
        sys.exit(1)

    # Get current heads
    print("\n📋 Checking for migration heads...")
    heads = get_heads()

    if not heads:
        print("⚠️  No heads found or error occurred")
        sys.exit(1)

    print(f"Found {len(heads)} head(s):")
    for head in heads:
        print(f"  • {head}")

    if len(heads) == 1:
        print("\n✅ Only one head found - no merge needed!")
        print("You can safely create new migrations.")
        return

    # Multiple heads detected
    print(f"\n⚠️  Multiple heads detected ({len(heads)} heads)")
    print("This will cause 'alembic upgrade head' to fail.")

    # Auto-create merge migration
    response = input("\nCreate merge migration automatically? (Y/n): ")

    if response.lower() in ['', 'y', 'yes']:
        if create_merge_migration(heads):
            print("\n✅ Success! Migration heads have been merged.")
            print("\n📝 Next steps:")
            print("  1. Review the generated merge migration file")
            print("  2. Commit it: git add app/alembic/versions/")
            print("  3. Push it: git push")
        else:
            print("\n❌ Failed to create merge migration")
            sys.exit(1)
    else:
        print("\n⏭️  Skipped automatic merge")
        print("\nTo merge manually, run:")
        print('  alembic merge -m "merge heads" heads')


if __name__ == "__main__":
    main()
