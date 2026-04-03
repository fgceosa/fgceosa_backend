"""
Reset Test Wallet Balances

This script resets all test wallet balances to zero by deleting test credit transactions.
Use this to clean up test data before going to production.

Usage:
    python reset_test_balances.py
"""
import sys
from sqlmodel import Session, select
from app.core.db import engine
from app.models import CreditTransaction, User
from app.core.config import settings


def reset_all_balances():
    """Reset all user balances to zero by deleting all credit transactions."""
    with Session(engine) as session:
        # Get count of transactions to delete
        statement = select(CreditTransaction)
        transactions = session.exec(statement).all()

        count = len(transactions)

        if count == 0:
            print("✅ No transactions found. Balances are already at zero.")
            return

        print(f"⚠️  Found {count} credit transactions")
        print(f"⚠️  This will reset ALL user balances to zero!")

        # Confirm
        response = input("\nAre you sure you want to delete ALL transactions? (yes/no): ")

        if response.lower() != "yes":
            print("❌ Cancelled. No changes made.")
            return

        # Delete all transactions
        for transaction in transactions:
            session.delete(transaction)

        session.commit()

        print(f"✅ Successfully deleted {count} transactions")
        print("✅ All user balances are now zero")


def reset_user_balance(user_id: str):
    """Reset a specific user's balance to zero."""
    import uuid

    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        print(f"❌ Invalid user ID format: {user_id}")
        return

    with Session(engine) as session:
        # Check if user exists
        user = session.get(User, user_uuid)
        if not user:
            print(f"❌ User not found: {user_id}")
            return

        # Get user's transactions
        statement = select(CreditTransaction).where(CreditTransaction.user_id == user_uuid)
        transactions = session.exec(statement).all()

        count = len(transactions)

        if count == 0:
            print(f"✅ No transactions found for {user.email}. Balance is already zero.")
            return

        print(f"⚠️  Found {count} credit transactions for {user.email}")

        # Confirm
        response = input(f"\nAre you sure you want to reset balance for {user.email}? (yes/no): ")

        if response.lower() != "yes":
            print("❌ Cancelled. No changes made.")
            return

        # Delete user's transactions
        for transaction in transactions:
            session.delete(transaction)

        session.commit()

        print(f"✅ Successfully deleted {count} transactions for {user.email}")
        print(f"✅ Balance for {user.email} is now zero")


def list_balances():
    """List all user balances."""
    with Session(engine) as session:
        # Get all users
        users = session.exec(select(User)).all()

        if not users:
            print("❌ No users found in database")
            return

        print("\n" + "="*80)
        print(f"{'Email':<40} {'Balance (Credits)':<20} {'Naira Equivalent'}")
        print("="*80)

        for user in users:
            # Get latest balance
            statement = (
                select(CreditTransaction.balance_after)
                .where(CreditTransaction.user_id == user.id)
                .order_by(CreditTransaction.created_at.desc())
                .limit(1)
            )
            balance = session.exec(statement).first()

            if balance is None:
                balance = 0.0

            naira = float(balance) * settings.NAIRA_TO_CREDIT_RATE

            print(f"{user.email:<40} {balance:<20.2f} ₦{naira:,.2f}")

        print("="*80 + "\n")


def main():
    """Main function."""
    print("\n" + "="*80)
    print("QOREBIT - Reset Test Wallet Balances")
    print("="*80)
    print(f"Environment: {settings.ENVIRONMENT}")
    print(f"Database: {settings.POSTGRES_DB}")
    print("="*80 + "\n")

    # Safety check for production
    if settings.ENVIRONMENT == "production":
        print("❌ ERROR: This script cannot be run in PRODUCTION environment!")
        print("❌ Change ENVIRONMENT to 'local' or 'staging' in your .env file")
        sys.exit(1)

    while True:
        print("\nOptions:")
        print("1. List all balances")
        print("2. Reset ALL balances to zero")
        print("3. Reset specific user balance")
        print("4. Exit")

        choice = input("\nSelect option (1-4): ").strip()

        if choice == "1":
            list_balances()
        elif choice == "2":
            reset_all_balances()
        elif choice == "3":
            list_balances()
            user_id = input("\nEnter user ID (UUID): ").strip()
            reset_user_balance(user_id)
        elif choice == "4":
            print("\n✅ Exiting...")
            break
        else:
            print("❌ Invalid option. Please try again.")


if __name__ == "__main__":
    main()
