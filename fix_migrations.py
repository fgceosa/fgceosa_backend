#!/usr/bin/env python3
"""
Migration troubleshooting and fix script for Alembic multiple heads issue.

This script helps diagnose and resolve migration branching issues.
"""

import subprocess
import sys
from datetime import datetime


def run_command(cmd, description=""):
    """Run a shell command and return output."""
    print(f"\n{'='*60}")
    if description:
        print(f"Running: {description}")
    print(f"Command: {cmd}")
    print('='*60)

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            check=False
        )

        print("STDOUT:")
        print(result.stdout or "(empty)")

        if result.stderr:
            print("\nSTDERR:")
            print(result.stderr)

        print(f"\nExit code: {result.returncode}")
        return result
    except Exception as e:
        print(f"Error running command: {e}")
        return None


def main():
    print("""
╔══════════════════════════════════════════════════════════════╗
║         Alembic Migration Troubleshooting Script             ║
╚══════════════════════════════════════════════════════════════╝

This script will help you:
1. Identify current migration heads
2. Understand the migration tree structure
3. Generate a merge migration if needed
""")

    # Check current heads
    print("\n📋 Step 1: Checking current migration heads...")
    result = run_command("alembic heads", "Check migration heads")

    if result and result.returncode == 0:
        heads_output = result.stdout
        # Count heads
        head_lines = [line for line in heads_output.split('\n') if line.strip()]
        num_heads = len(head_lines)

        print(f"\n✓ Found {num_heads} head(s)")

        if num_heads > 1:
            print("\n⚠️  ISSUE: Multiple heads detected!")
            print("This is why 'alembic upgrade head' fails.")
            print("\nCurrent heads:")
            for line in head_lines:
                print(f"  • {line}")
        else:
            print("\n✓ Only one head found - migrations look good!")
            return
    else:
        print("\n❌ Failed to check heads. Make sure you're in the right directory.")
        return

    # Show migration tree
    print("\n\n📊 Step 2: Showing migration tree structure...")
    run_command("alembic history --verbose", "Show migration history")

    # Check branches
    print("\n\n🌳 Step 3: Checking for branches...")
    result = run_command("alembic branches", "Check migration branches")

    # Generate merge migration
    if num_heads > 1:
        print("\n\n🔧 Step 4: Ready to create merge migration")
        print("\nTo fix this, you need to create a merge migration.")
        print("\nRun this command:")
        print(f'\n    alembic merge -m "merge multiple heads" heads')
        print("\nThis will:")
        print("  1. Create a new migration file that merges all current heads")
        print("  2. Make all heads converge into a single migration path")
        print("  3. Allow 'alembic upgrade head' to work again")

        response = input("\n\nWould you like me to create the merge migration now? (y/N): ")
        if response.lower() == 'y':
            print("\n🔨 Creating merge migration...")
            result = run_command(
                'alembic merge -m "merge multiple heads" heads',
                "Create merge migration"
            )

            if result and result.returncode == 0:
                print("\n✅ Merge migration created successfully!")
                print("\n📝 Next steps:")
                print("  1. Review the generated migration file")
                print("  2. Commit it to your repository")
                print("  3. Deploy to Render")
                print("  4. The pre-deploy will now work with 'alembic upgrade head'")
            else:
                print("\n❌ Failed to create merge migration.")
                print("You may need to create it manually.")
        else:
            print("\n⏭️  Skipped merge migration creation.")
            print("\nYou can create it manually later with:")
            print('    alembic merge -m "merge multiple heads" heads')

    print("\n\n" + "="*60)
    print("Script completed!")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
