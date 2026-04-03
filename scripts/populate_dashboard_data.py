"""
Script to populate sample dashboard data for testing

This script creates sample data for:
- Projects
- API Requests
- Credit Transactions

The data is created for *all* existing users in the database.

Run this script after running migrations to populate the database with test data.
"""
import sys
import os
from datetime import datetime, timedelta
from decimal import Decimal
import random
import uuid

# Add parent directory to path to import app modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Project, APIRequest, CreditTransaction


# Sample data
AI_MODELS = ["gpt-4", "claude-sonnet", "llama-3", "gpt-3.5-turbo", "claude-opus"]
ENDPOINTS = ["/v1/chat/completions", "/v1/completions", "/v1/embeddings", "/v1/images/generations"]
TRANSACTION_TYPES = ["purchase", "usage", "bonus"]
STATUSES = ["success", "error"]


def get_all_users(session: Session) -> list[User]:
    """Get all users from the database"""
    users = session.exec(select(User)).all()
    if not users:
        print("🛑 No users found in the database. Please create a user first.")
        sys.exit(1)
    return users


def create_projects(session: Session, user_id: uuid.UUID, count: int = 3) -> list[Project]:
    """Create sample projects"""
    projects = []
    project_names = [
        "Production API",
        "Development Environment",
        "Testing Suite",
        "Mobile App Integration",
        "Web Dashboard",
    ]
    
    # Use a subset of names to avoid IndexError if count > len(project_names)
    names_to_use = random.sample(project_names, min(count, len(project_names)))
    
    for i, name in enumerate(names_to_use):
        project = Project(
            name=name,
            description=f"Sample project {i+1} for testing dashboard functionality",
            user_id=user_id,
            is_active=True if i < count - 1 else random.choice([True, False]),
            created_at=datetime.utcnow() - timedelta(days=random.randint(30, 180)),
            updated_at=datetime.utcnow() - timedelta(days=random.randint(1, 30)),
        )
        session.add(project)
        projects.append(project)
    
    session.commit()
    for project in projects:
        session.refresh(project)
    
    return projects


def create_api_requests(session: Session, user_id: uuid.UUID, projects: list[Project], count: int = 200) -> list[APIRequest]:
    """Create sample API requests"""
    if not projects:
        return []
        
    requests = []
    
    for i in range(count):
        # Randomly distribute requests over the last 30 days
        days_ago = random.randint(0, 30)
        hours_ago = random.randint(0, 23)
        minutes_ago = random.randint(0, 59)
        created_at = datetime.utcnow() - timedelta(days=days_ago, hours=hours_ago, minutes=minutes_ago)
        
        # Random token counts
        request_tokens = random.randint(50, 500)
        response_tokens = random.randint(100, 1000)
        total_tokens = request_tokens + response_tokens
        
        # Calculate cost (example: $0.00002 per token for GPT-4)
        model = random.choice(AI_MODELS)
        cost_per_token = {
            "gpt-4": 0.00003,
            "claude-sonnet": 0.000025,
            "llama-3": 0.00001,
            "gpt-3.5-turbo": 0.000002,
            "claude-opus": 0.00004,
        }
        cost = Decimal(str(total_tokens * cost_per_token.get(model, 0.00002)))
        
        request = APIRequest(
            project_id=random.choice(projects).id,
            user_id=user_id,
            model=model,
            endpoint=random.choice(ENDPOINTS),
            request_tokens=request_tokens,
            response_tokens=response_tokens,
            total_tokens=total_tokens,
            cost=cost,
            status=random.choices(STATUSES, weights=[95, 5])[0],  # 95% success rate
            response_time_ms=random.randint(200, 5000),
            created_at=created_at,
        )
        session.add(request)
        requests.append(request)
    
    session.commit()
    return requests


def create_credit_transactions(session: Session, user_id: uuid.UUID, count: int = 50) -> list[CreditTransaction]:
    """Create sample credit transactions"""
    transactions = []
    current_balance = Decimal("5000.00")  # Starting balance
    
    # Create initial purchase
    initial_transaction = CreditTransaction(
        user_id=user_id,
        amount=Decimal("5000.00"),
        balance_after=current_balance,
        transaction_type="purchase",
        description="Initial credit purchase",
        reference_id=f"pay_{uuid.uuid4().hex[:12]}",
        created_at=datetime.utcnow() - timedelta(days=90),
    )
    session.add(initial_transaction)
    transactions.append(initial_transaction)
    
    # Create usage and occasional purchases
    for i in range(count - 1):
        days_ago = random.randint(0, 89)
        created_at = datetime.utcnow() - timedelta(days=days_ago, hours=random.randint(0, 23))
        
        # 80% usage, 15% purchase, 5% bonus
        transaction_type = random.choices(TRANSACTION_TYPES, weights=[80, 15, 5])[0]
        
        if transaction_type == "purchase":
            amount = Decimal(str(random.choice([100, 250, 500, 1000])))
            current_balance += amount
            description = f"Credit purchase - ${amount}"
            reference_id = f"pay_{uuid.uuid4().hex[:12]}"
        elif transaction_type == "bonus":
            amount = Decimal(str(random.choice([10, 25, 50, 100])))
            current_balance += amount
            description = "Promotional bonus credits"
            reference_id = f"bonus_{uuid.uuid4().hex[:12]}"
        else:  # usage
            amount = Decimal(str(-round(random.uniform(1, 50), 2)))
            current_balance += amount  # amount is already negative
            description = "API usage charges"
            reference_id = f"req_{uuid.uuid4().hex[:12]}"
        
        transaction = CreditTransaction(
            user_id=user_id,
            amount=amount,
            balance_after=current_balance,
            transaction_type=transaction_type,
            description=description,
            reference_id=reference_id,
            created_at=created_at,
        )
        session.add(transaction)
        transactions.append(transaction)
    
    session.commit()
    return transactions, current_balance


def main():
    """Main function to populate sample data for ALL users"""
    print("\n🚀 Starting dashboard data population for ALL users...")
    print("=" * 60)
    
    with Session(engine) as session:
        # Get all users
        print("\n1. Getting all users...")
        users = get_all_users(session)
        print(f"   Found {len(users)} users to populate data for.")
        
        total_projects = 0
        total_requests = 0
        total_transactions = 0
        
        # Loop through each user and create data
        for i, user in enumerate(users):
            print(f"\n--- Populating data for User {i+1}/{len(users)}: {user.email} (ID: {user.id}) ---")
            
            # 2. Create projects
            print("   a. Creating projects...")
            projects = create_projects(session, user.id, count=3)
            print(f"      ✓ Created {len(projects)} projects")
            total_projects += len(projects)
            
            # 3. Create API requests
            print("   b. Creating API requests...")
            requests = create_api_requests(session, user.id, projects, count=200)
            print(f"      ✓ Created {len(requests)} API requests")
            total_requests += len(requests)
            
            # 4. Create credit transactions
            print("   c. Creating credit transactions...")
            transactions, final_balance = create_credit_transactions(session, user.id, count=50)
            print(f"      ✓ Created {len(transactions)} credit transactions (Final balance: ${final_balance})")
            total_transactions += len(transactions)

        print("\n" + "=" * 60)
        print("✅ Dashboard data population completed successfully!")
        print("\nOverall Summary:")
        print(f"  - Total Users Populated: {len(users)}")
        print(f"  - Total Projects: {total_projects}")
        print(f"  - Total API Requests: {total_requests}")
        print(f"  - Total Credit Transactions: {total_transactions}")
        print("\nYou can now access the dashboard at the frontend.")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    main()