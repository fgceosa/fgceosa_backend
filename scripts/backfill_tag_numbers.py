"""
Backfill script to generate tag numbers for existing users.

This script will:
1. Find all users with NULL tag_number
2. Generate unique tag numbers for each user
3. Update the database with the generated tags
4. Provide progress output and summary

Usage:
    python scripts/backfill_tag_numbers.py

Options:
    --dry-run: Show what would be done without making changes
    --batch-size: Number of users to process at a time (default: 100)
"""

import sys
from pathlib import Path
from typing import List

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from app.core.db import engine
from app.models import User
from app.utils.tag_generator import assign_tag_number


def get_users_without_tags(session: Session, batch_size: int = 100) -> List[User]:
    """
    Get all users without tag numbers.

    Args:
        session: Database session
        batch_size: Number of users to fetch at a time

    Returns:
        List of users without tag numbers
    """
    statement = select(User).where(
        (User.tag_number == None) | (User.tag_number == "")
    ).limit(batch_size)
    users = session.exec(statement).all()
    return list(users)


def backfill_tag_numbers(dry_run: bool = False, batch_size: int = 100) -> dict:
    """
    Backfill tag numbers for all users without them.

    Args:
        dry_run: If True, only show what would be done without making changes
        batch_size: Number of users to process at a time

    Returns:
        Dictionary with statistics about the operation
    """
    stats = {
        "total_processed": 0,
        "successful": 0,
        "failed": 0,
        "errors": []
    }

    with Session(engine) as session:
        # Get all users without tags
        users = get_users_without_tags(session, batch_size=batch_size)
        total_users = len(users)

        if total_users == 0:
            print("✅ No users found without tag numbers. All users already have tags!")
            return stats

        print(f"Found {total_users} user(s) without tag numbers")
        print()

        if dry_run:
            print("🔍 DRY RUN MODE - No changes will be made")
            print()

        # Process each user
        for i, user in enumerate(users, 1):
            stats["total_processed"] += 1

            try:
                if dry_run:
                    # In dry run, just show what would happen
                    print(f"[{i}/{total_users}] Would assign tag to user: {user.email} (ID: {user.id})")
                else:
                    # Generate and assign tag number
                    tag = assign_tag_number(session=session, user=user, commit=True)
                    stats["successful"] += 1
                    print(f"[{i}/{total_users}] ✅ Assigned tag {tag} to user: {user.email}")

            except Exception as e:
                stats["failed"] += 1
                error_msg = f"User {user.email} (ID: {user.id}): {str(e)}"
                stats["errors"].append(error_msg)
                print(f"[{i}/{total_users}] ❌ Failed to assign tag to user: {user.email}")
                print(f"   Error: {str(e)}")

        print()

    return stats


def print_summary(stats: dict, dry_run: bool = False):
    """Print summary of the backfill operation."""
    print("=" * 60)
    if dry_run:
        print("DRY RUN SUMMARY")
    else:
        print("BACKFILL SUMMARY")
    print("=" * 60)
    print(f"Total users processed: {stats['total_processed']}")

    if not dry_run:
        print(f"✅ Successfully assigned: {stats['successful']}")
        print(f"❌ Failed: {stats['failed']}")

        if stats['errors']:
            print()
            print("Errors:")
            for error in stats['errors']:
                print(f"  - {error}")

    print("=" * 60)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Backfill tag numbers for existing users")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of users to process at a time (default: 100)"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Qorebit Tag Number Backfill Script")
    print("=" * 60)
    print()

    if args.dry_run:
        print("🔍 Running in DRY RUN mode - no changes will be made")
        print()

    # Run backfill
    try:
        stats = backfill_tag_numbers(dry_run=args.dry_run, batch_size=args.batch_size)
        print()
        print_summary(stats, dry_run=args.dry_run)

        # Exit with appropriate code
        if stats['failed'] > 0:
            sys.exit(1)
        else:
            sys.exit(0)

    except Exception as e:
        print()
        print("=" * 60)
        print(f"❌ Backfill failed with error: {str(e)}")
        print("=" * 60)
        sys.exit(1)
