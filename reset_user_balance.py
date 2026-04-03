#!/usr/bin/env python3
"""
Reset credit balance for a specific user.

Usage:
    python reset_user_balance.py <user_email>
    python reset_user_balance.py <user_id>
"""

import sys
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, CreditTransaction, TopUp
from app.core.config import settings


def reset_user_balance(user_identifier: str):
    """Reset credit balance for a specific user to 0."""

    # Safety check
    if settings.ENVIRONMENT == "production":
        print("❌ ERROR: Cannot run this script in PRODUCTION environment!")
        print("This script is for development/testing only.")
        sys.exit(1)

    with Session(engine) as session:
        # Find user by email or ID
        if "@" in user_identifier:
            # Search by email
            statement = select(User).where(User.email == user_identifier)
            user = session.exec(statement).first()
        else:
            # Search by ID
            statement = select(User).where(User.id == user_identifier)
            user = session.exec(statement).first()

        if not user:
            print(f"❌ User not found: {user_identifier}")
            sys.exit(1)

        print(f"\n📋 User Details:")
        print(f"   ID: {user.id}")
        print(f"   Email: {user.email}")
        print(f"   Name: {user.full_name}")

        # Get all credit transactions for this user
        credit_statement = select(CreditTransaction).where(
            CreditTransaction.user_id == user.id
        )
        credit_transactions = session.exec(credit_statement).all()

        # Get all top-ups for this user
        topup_statement = select(TopUp).where(TopUp.user_id == user.id)
        topups = session.exec(topup_statement).all()

        print(f"\n📊 Current State:")
        print(f"   Credit Transactions: {len(credit_transactions)}")
        print(f"   Top-ups: {len(topups)}")

        if len(credit_transactions) == 0 and len(topups) == 0:
            print("\n✅ User already has no transactions. Balance is already 0.")
            return

        # Confirm deletion
        print(f"\n⚠️  This will DELETE:")
        print(f"   - {len(credit_transactions)} credit transaction(s)")
        print(f"   - {len(topups)} top-up record(s)")
        print(f"\n⚠️  User balance will be reset to 0 AI credits.")

        response = input("\nAre you sure you want to continue? (yes/no): ")
        if response.lower() != "yes":
            print("\n❌ Operation cancelled.")
            return

        # Delete all credit transactions
        for transaction in credit_transactions:
            session.delete(transaction)

        # Delete all top-ups
        for topup in topups:
            session.delete(topup)

        session.commit()

        print(f"\n✅ Successfully reset balance for user: {user.email}")
        print(f"   Deleted {len(credit_transactions)} credit transaction(s)")
        print(f"   Deleted {len(topups)} top-up record(s)")
        print(f"   Balance is now: 0 AI credits")


def main():
    if len(sys.argv) != 2:
        print("Usage: python reset_user_balance.py <user_email_or_id>")
        print("\nExamples:")
        print("  python reset_user_balance.py kola@gmail.com")
        print("  python reset_user_balance.py 837c393f-2163-408e-99c7-6589b57d5053")
        sys.exit(1)

    user_identifier = sys.argv[1]
    reset_user_balance(user_identifier)


if __name__ == "__main__":
    main()
