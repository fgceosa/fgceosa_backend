#!/usr/bin/env python3
"""
Add credits to a specific user.
If user does not exist, it will be created.

Usage:
    python add_user_credits.py <user_email> <amount>
"""

import sys
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlmodel import Session, select, func, col
from app.core.db import engine
from app.models import User, CreditTransaction
from app.core.security import get_password_hash

def add_user_credits(user_email: str, amount: float):
    """Add credits to a user."""

    with Session(engine) as session:
        # Find user by email
        statement = select(User).where(User.email == user_email)
        user = session.exec(statement).first()

        if not user:
            print(f"⚠️  User not found: {user_email}")
            print("Creating new user...")
            
            user = User(
                email=user_email,
                hashed_password=get_password_hash("password123"), # Default password
                is_active=True,
                full_name="Org User",
                account_type="organization", # Assuming organization based on email
                status="active"
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            print(f"✅ Created user with ID: {user.id}")

        print(f"\n📋 User Details:")
        print(f"   ID: {user.id}")
        print(f"   Email: {user.email}")
        print(f"   Name: {user.full_name}")

        # Calculate current balance
        # Sum all transaction amounts
        balance_statement = select(func.sum(CreditTransaction.amount)).where(
            CreditTransaction.user_id == user.id
        )
        current_balance = session.exec(balance_statement).one() or Decimal("0.00")
        
        print(f"\n💰 Current Balance: {current_balance} credits")

        amount_decimal = Decimal(str(amount))
        new_balance = current_balance + amount_decimal

        print(f"➕ Adding: {amount_decimal} credits")
        print(f"💰 New Balance will be: {new_balance} credits")

        # Confirm
        # Skip confirmation for now to make it smoother or just auto confirm if script is robust
        # response = input("\nAre you sure you want to continue? (yes/no): ")
        # if response.lower() != "yes":
        #     print("\n❌ Operation cancelled.")
        #     return

        # Create new credit transaction
        transaction = CreditTransaction(
            user_id=user.id,
            amount=amount_decimal,
            balance_after=new_balance,
            transaction_type="manual_credit",
            description="Manual credit addition via script",
            created_at=datetime.now(timezone.utc)
        )

        session.add(transaction)
        session.commit()
        session.refresh(transaction)

        print(f"\n✅ Successfully added {amount_decimal} credits to user: {user.email}")
        print(f"   Transaction ID: {transaction.id}")
        print(f"   New Balance: {new_balance} credits")


def main():
    if len(sys.argv) == 3:
        user_email = sys.argv[1]
        try:
            amount = float(sys.argv[2])
        except ValueError:
             print("Invalid amount")
             sys.exit(1)
        add_user_credits(user_email, amount)
    else:
        print("Usage: python add_user_credits.py <user_email> <amount>")
        print("\nRunning for requested task: org@gmail.com + 20 credits")
        add_user_credits("org@gmail.com", 20)

if __name__ == "__main__":
    main()
