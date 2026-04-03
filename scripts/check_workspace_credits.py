"""
Script to check workspace credits and find workspace by user email.

Usage:
    python scripts/check_workspace_credits.py --email "hello@devscourtai.com"
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from app.core.db import engine
from app.models import Workspace, User, WorkspaceMember


def check_workspace_by_email(email: str):
    """
    Find all workspaces associated with a user email and show their credits.
    """
    with Session(engine) as session:
        # Find user by email
        user_statement = select(User).where(User.email == email)
        user = session.exec(user_statement).first()

        if not user:
            print(f"❌ Error: User with email '{email}' not found")
            return

        print(f"✅ Found user: {user.email}")
        print(f"   User ID: {user.id}")
        print(f"   Name: {user.first_name} {user.last_name}")
        print()

        # Find all workspace memberships for this user
        member_statement = select(WorkspaceMember).where(
            WorkspaceMember.user_id == user.id
        )
        memberships = session.exec(member_statement).all()

        if not memberships:
            print(f"❌ User is not a member of any workspace")
            return

        print(f"Found {len(memberships)} workspace(s):")
        print("=" * 80)

        for membership in memberships:
            # Get workspace details
            workspace = session.get(Workspace, membership.workspace_id)

            if workspace:
                print(f"\n📊 Workspace: {workspace.name}")
                print(f"   ID: {workspace.id}")
                print(f"   Owner ID: {workspace.owner_id}")
                print(f"   💰 Credits Balance: {workspace.credits_balance}")
                print(f"   Status: {workspace.status}")
                print(f"   Role in workspace: {membership.role}")
                print(f"   Member credits allocated: {membership.credits_allocated}")
                print(f"   Created: {workspace.created_at}")
                print("-" * 80)


def check_workspace_by_name(workspace_name: str):
    """
    Find workspace by name and show its credits.
    """
    with Session(engine) as session:
        statement = select(Workspace).where(Workspace.name == workspace_name)
        workspace = session.exec(statement).first()

        if not workspace:
            print(f"❌ Error: Workspace '{workspace_name}' not found")
            return

        print(f"✅ Found workspace: {workspace.name}")
        print(f"   ID: {workspace.id}")
        print(f"   💰 Credits Balance: {workspace.credits_balance}")
        print(f"   Owner ID: {workspace.owner_id}")
        print(f"   Status: {workspace.status}")
        print(f"   Created: {workspace.created_at}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Check workspace credits")
    parser.add_argument(
        "--email",
        type=str,
        help="User email to check workspaces for"
    )
    parser.add_argument(
        "--workspace-name",
        type=str,
        help="Workspace name to check"
    )

    args = parser.parse_args()

    print("=" * 80)
    print("Workspace Credits Checker")
    print("=" * 80)
    print()

    if args.email:
        check_workspace_by_email(args.email)
    elif args.workspace_name:
        check_workspace_by_name(args.workspace_name)
    else:
        print("Please provide either --email or --workspace-name")
        parser.print_help()
        sys.exit(1)
