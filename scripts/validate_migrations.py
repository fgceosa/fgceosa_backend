#!/usr/bin/env python3
"""
Pre-commit hook to validate migration state.
Prevents commits when there are multiple migration heads.
"""

import subprocess
import sys


def run_command(cmd):
    """Run a command and return output."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except Exception as e:
        return 1, "", str(e)


def main():
    """Check for multiple migration heads."""
    print("🔍 Validating migration state...")

    # Get heads
    code, stdout, stderr = run_command("alembic heads 2>&1")

    if code != 0:
        if "Can't locate revision" in stderr:
            print("⚠️  Warning: Orphaned migration detected")
            print("Run: python3 scripts/fix_alembic_state.py")
            return 1
        print(f"⚠️  Warning: Could not check heads: {stderr}")
        # Don't fail the commit if we can't check
        return 0

    # Count heads
    heads = [line.strip() for line in stdout.split('\n') if line.strip()]
    head_count = len(heads)

    if head_count > 1:
        print(f"❌ Multiple migration heads detected ({head_count} heads)!")
        print("\nCurrent heads:")
        for head in heads:
            print(f"  • {head}")
        print("\n⚠️  This will cause deployment failures!")
        print("\nTo fix, run:")
        print("  python3 scripts/auto_merge_migrations.py")
        print("\nThen commit the generated merge migration.")
        return 1

    print(f"✅ Migration validation passed ({head_count} head)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
