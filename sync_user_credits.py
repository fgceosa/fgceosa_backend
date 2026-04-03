#!/usr/bin/env python3
"""
Sync user credits balance field from transactions sum.

Usage:
    python sync_user_credits.py <user_email>
"""

import sys
from decimal import Decimal
from sqlmodel import Session, select, func
from app.core.db import engine
from app.models import User, CreditTransaction

def sync_user_credits(user_email: str):
    with Session(engine) as session:
        # Find user
        user = session.exec(select(User).where(User.email == user_email)).first()
        if not user:
            print(f"❌ User not found: {user_email}")
            return

        # Calculate sum from transactions
        balance_statement = select(func.sum(CreditTransaction.amount)).where(
            CreditTransaction.user_id == user.id
        )
        total_credits = session.exec(balance_statement).one() or Decimal("0.00")

        print(f"User: {user.email}")
        print(f"Current User.credits field: {user.credits}")
        print(f"Sum of transactions: {total_credits}")

        if user.credits != total_credits:
            print(f"⚠️  Mismatch detected. Updating User.credits to {total_credits}...")
            user.credits = total_credits
            session.add(user)
            session.commit()
            session.refresh(user)
            print("✅ Synced successfully.")
        else:
            print("✅ Balances are already in sync.")

if __name__ == "__main__":
    if len(sys.argv) == 2:
        sync_user_credits(sys.argv[1])
    else:
        # Default
        sync_user_credits("org@gmail.com")
