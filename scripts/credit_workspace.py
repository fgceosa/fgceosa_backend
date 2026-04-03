"""
Script to manually credit a workspace with AI credits.

Usage:
    python scripts/credit_workspace.py --workspace-name "Devscourt AI" --amount 50

This script will:
1. Find the workspace by name
2. Add the specified amount to workspace credits_balance
3. Create a transaction record for the credit addition
"""

import asyncio
import sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlmodel import Session, select
from app.core.db import engine
from app.models import Workspace, WorkspaceCreditTransaction


def credit_workspace(workspace_name: str, amount: float, description: str = None) -> bool:
    """
    Credit a workspace with the specified amount.

    Args:
        workspace_name: Name of the workspace to credit
        amount: Amount of credits to add
        description: Optional description for the transaction

    Returns:
        True if successful, False otherwise
    """
    with Session(engine) as session:
        # Find workspace by name
        statement = select(Workspace).where(Workspace.name == workspace_name)
        workspace = session.exec(statement).first()

        if not workspace:
            print(f"❌ Error: Workspace '{workspace_name}' not found")
            return False

        print(f"✅ Found workspace: {workspace.name} (ID: {workspace.id})")
        print(f"   Current balance: {workspace.credits_balance} credits")

        # Store old balance
        old_balance = workspace.credits_balance

        # Add credits to workspace
        workspace.credits_balance += Decimal(str(amount))

        # Create transaction record
        transaction = WorkspaceCreditTransaction(
            workspace_id=workspace.id,
            type="purchase",
            amount=Decimal(str(amount)),
            balance=workspace.credits_balance,
            description=description or f"Manual credit addition: {amount} credits",
            status="completed",
            created_at=datetime.now(timezone.utc)
        )

        # Save changes
        session.add(workspace)
        session.add(transaction)
        session.commit()
        session.refresh(workspace)
        session.refresh(transaction)

        print(f"✅ Successfully credited {amount} credits")
        print(f"   Old balance: {old_balance} credits")
        print(f"   New balance: {workspace.credits_balance} credits")
        print(f"   Transaction ID: {transaction.id}")

        return True


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Credit a workspace with AI credits")
    parser.add_argument(
        "--workspace-name",
        type=str,
        required=True,
        help="Name of the workspace to credit"
    )
    parser.add_argument(
        "--amount",
        type=float,
        required=True,
        help="Amount of credits to add"
    )
    parser.add_argument(
        "--description",
        type=str,
        default=None,
        help="Optional description for the transaction"
    )

    args = parser.parse_args()

    print("=" * 60)
    print("Manual Workspace Credit Addition")
    print("=" * 60)
    print(f"Workspace: {args.workspace_name}")
    print(f"Amount: {args.amount} credits")
    if args.description:
        print(f"Description: {args.description}")
    print("=" * 60)
    print()

    # Validate amount
    if args.amount <= 0:
        print("❌ Error: Amount must be greater than 0")
        sys.exit(1)

    # Execute credit operation
    success = credit_workspace(
        workspace_name=args.workspace_name,
        amount=args.amount,
        description=args.description
    )

    if success:
        print()
        print("=" * 60)
        print("✅ Operation completed successfully!")
        print("=" * 60)
        sys.exit(0)
    else:
        print()
        print("=" * 60)
        print("❌ Operation failed!")
        print("=" * 60)
        sys.exit(1)
