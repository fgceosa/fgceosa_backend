"""
Seed Shared Credits Sample Data

This script creates sample users with credits and generates
sample credit transactions for testing the shared credits feature.

Usage:
    python -m scripts.seed_shared_credits
"""
import uuid
import random
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select

from app.core.db import engine
from app.core.security import get_password_hash
from app.models import (
    User,
    UserRole,
    Role,
    CreditTransaction,
    TransactionStatus,
)


def seed_shared_credits_data():
    """Seed the database with sample users and credit transactions"""

    with Session(engine) as session:
        print("Starting shared credits data seeding...")

        # Get or create the 'user' role
        user_role = session.exec(select(Role).where(Role.name == "user")).first()
        if not user_role:
            print("Error: 'user' role not found. Please run seed_rbac_data.py first.")
            return

        # Sample user data
        sample_users = [
            {
                "email": "alice@example.com",
                "full_name": "Alice Johnson",
                "credits": 5000,
            },
            {
                "email": "bob@example.com",
                "full_name": "Bob Smith",
                "credits": 3500,
            },
            {
                "email": "charlie@example.com",
                "full_name": "Charlie Brown",
                "credits": 7200,
            },
            {
                "email": "diana@example.com",
                "full_name": "Diana Prince",
                "credits": 4800,
            },
            {
                "email": "evan@example.com",
                "full_name": "Evan Williams",
                "credits": 6100,
            },
            {
                "email": "fiona@example.com",
                "full_name": "Fiona Davis",
                "credits": 2900,
            },
            {
                "email": "george@example.com",
                "full_name": "George Miller",
                "credits": 8500,
            },
            {
                "email": "hannah@example.com",
                "full_name": "Hannah Wilson",
                "credits": 4200,
            },
        ]

        # Create users if they don't exist
        created_users = []
        default_password = get_password_hash("password123")  # Default password for testing

        for user_data in sample_users:
            existing_user = session.exec(
                select(User).where(User.email == user_data["email"])
            ).first()

            if not existing_user:
                user = User(
                    email=user_data["email"],
                    full_name=user_data["full_name"],
                    credits=user_data["credits"],
                    hashed_password=default_password,
                    is_active=True,
                    is_superuser=False,
                )
                session.add(user)
                session.commit()
                session.refresh(user)

                # Assign user role
                user_role_assignment = UserRole(
                    user_id=user.id,
                    role_id=user_role.id,
                )
                session.add(user_role_assignment)
                session.commit()

                created_users.append(user)
                print(f"  ✓ Created user: {user.email} with {user.credits} credits")
            else:
                # Update credits for existing user
                existing_user.credits = user_data["credits"]
                session.add(existing_user)
                session.commit()
                created_users.append(existing_user)
                print(f"  ✓ Updated user: {existing_user.email} with {user_data['credits']} credits")

        print(f"\n✓ {len(created_users)} users processed")

        # Generate sample transactions
        if len(created_users) >= 2:
            print("\nGenerating sample credit transactions...")

            # Sample transaction scenarios
            transactions_data = [
                # Alice sends to Bob
                {
                    "sender": created_users[0],
                    "recipient": created_users[1],
                    "amount": 500,
                    "message": "Thanks for the help with the project!",
                    "status": TransactionStatus.COMPLETED,
                    "days_ago": 5,
                },
                # Bob sends to Charlie
                {
                    "sender": created_users[1],
                    "recipient": created_users[2],
                    "amount": 300,
                    "message": "Payment for consulting services",
                    "status": TransactionStatus.COMPLETED,
                    "days_ago": 4,
                },
                # Charlie sends to Diana
                {
                    "sender": created_users[2],
                    "recipient": created_users[3],
                    "amount": 750,
                    "message": "Advance payment",
                    "status": TransactionStatus.COMPLETED,
                    "days_ago": 3,
                },
                # Diana sends to Evan
                {
                    "sender": created_users[3],
                    "recipient": created_users[4],
                    "amount": 200,
                    "message": "Coffee meetup reimbursement",
                    "status": TransactionStatus.COMPLETED,
                    "days_ago": 2,
                },
                # Evan sends to Fiona
                {
                    "sender": created_users[4],
                    "recipient": created_users[5],
                    "amount": 1000,
                    "message": "Project bonus",
                    "status": TransactionStatus.COMPLETED,
                    "days_ago": 1,
                },
                # Fiona sends to George
                {
                    "sender": created_users[5],
                    "recipient": created_users[6],
                    "amount": 400,
                    "message": "Collaboration reward",
                    "status": TransactionStatus.COMPLETED,
                    "days_ago": 1,
                },
                # George sends to Hannah
                {
                    "sender": created_users[6],
                    "recipient": created_users[7],
                    "amount": 600,
                    "message": "Training session payment",
                    "status": TransactionStatus.COMPLETED,
                    "days_ago": 0,
                },
                # Hannah sends to Alice (completes the circle)
                {
                    "sender": created_users[7],
                    "recipient": created_users[0],
                    "amount": 350,
                    "message": "Thank you for mentoring!",
                    "status": TransactionStatus.COMPLETED,
                    "days_ago": 0,
                },
                # Some pending transactions
                {
                    "sender": created_users[0],
                    "recipient": created_users[3],
                    "amount": 250,
                    "message": "Processing...",
                    "status": TransactionStatus.PENDING,
                    "days_ago": 0,
                },
                # A failed transaction
                {
                    "sender": created_users[2],
                    "recipient": created_users[5],
                    "amount": 100,
                    "message": "Payment failed due to insufficient credits",
                    "status": TransactionStatus.FAILED,
                    "days_ago": 1,
                },
            ]

            transaction_count = 0
            for trans_data in transactions_data:
                # Calculate timestamp
                created_at = datetime.now(timezone.utc) - timedelta(days=trans_data["days_ago"])

                # Create transaction
                transaction = CreditTransaction(
                    sender_id=trans_data["sender"].id,
                    recipient_id=trans_data["recipient"].id,
                    amount=trans_data["amount"],
                    message=trans_data["message"],
                    status=trans_data["status"],
                    created_at=created_at,
                    updated_at=created_at,
                )
                session.add(transaction)
                transaction_count += 1

                print(
                    f"  ✓ {trans_data['sender'].full_name} → {trans_data['recipient'].full_name}: "
                    f"{trans_data['amount']} credits ({trans_data['status']})"
                )

            session.commit()
            print(f"\n✓ Created {transaction_count} sample transactions")

        print("\n✅ Shared credits data seeding completed successfully!")
        print("\nTest users created with default password: 'password123'")
        print("You can now login with any of the following emails:")
        for user in created_users[:3]:  # Show first 3 users
            print(f"  - {user.email}")


if __name__ == "__main__":
    seed_shared_credits_data()
