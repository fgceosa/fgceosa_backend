#!/usr/bin/env python3
"""
Pre-commit hook to check migration file format.
Ensures migration files follow proper structure.
"""

import re
import sys
from pathlib import Path


def check_migration_file(filepath):
    """Check if migration file is properly formatted."""
    content = Path(filepath).read_text()

    # Required fields
    required_patterns = [
        (r'^revision\s*=\s*["\'][\w_]+["\']', "Missing or invalid 'revision' field"),
        (r'^down_revision\s*=\s*', "Missing 'down_revision' field"),
        (r'^def upgrade\(\):', "Missing 'upgrade()' function"),
        (r'^def downgrade\(\):', "Missing 'downgrade()' function"),
    ]

    errors = []

    for pattern, error_msg in required_patterns:
        if not re.search(pattern, content, re.MULTILINE):
            errors.append(error_msg)

    # Check for common mistakes
    if 'revision = None' in content:
        errors.append("Revision ID is None - run 'alembic revision' to generate")

    if 'down_revision = None' in content and 'initialize' not in filepath.lower():
        errors.append("down_revision is None (should only be in initial migration)")

    return errors


def main():
    """Check all modified migration files."""
    import subprocess

    # Get staged migration files
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True,
        text=True
    )

    migration_files = [
        f for f in result.stdout.split('\n')
        if f.startswith('app/alembic/versions/') and f.endswith('.py')
        and not f.endswith('__init__.py')
    ]

    if not migration_files:
        # No migration files being committed
        return 0

    print(f"🔍 Checking {len(migration_files)} migration file(s)...")

    all_errors = {}

    for filepath in migration_files:
        if not Path(filepath).exists():
            continue

        errors = check_migration_file(filepath)
        if errors:
            all_errors[filepath] = errors

    if all_errors:
        print("❌ Migration file validation failed!\n")
        for filepath, errors in all_errors.items():
            print(f"File: {filepath}")
            for error in errors:
                print(f"  • {error}")
            print()
        return 1

    print("✅ Migration file validation passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
