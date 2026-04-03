"""
Seed script to create dummy team members and populate usage data.

Run this after you have run migrations and have roles seeded (there is a seed_rbac_data.py in this repo).

Usage:
    python3 scripts/seed_team_data.py
"""
import sys
import os
from sqlmodel import Session, select

# allow imports from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import engine
from app import user_repository
from app.models import UserCreate, Role, User
from scripts.populate_dashboard_data import main as populate_main


def ensure_roles(session: Session):
    # ensure at least 'user' role exists
    r = session.exec(select(Role).where(Role.name == "user")).first()
    if not r:
        print("Creating default role 'user'")
        role = Role(name="user", description="Default user role")
        session.add(role)
        session.commit()


def main():
    print("Seeding team users...")
    with Session(engine) as session:
        ensure_roles(session)

        emails = [
            "alice+team1@example.com",
            "bob+team2@example.com",
            "carol+team3@example.com",
            "dave+team4@example.com",
            "eve+team5@example.com",
        ]

        for i, email in enumerate(emails):
            existing = session.exec(select(User).where(User.email == email)).first()
            if existing:
                print(f"User {email} already exists, skipping")
                continue
            password = "Password123!"
            # include example profile fields
            user_create = UserCreate(
                email=email,
                password=password,
                full_name=f"Team Member {i+1}",
                username=f"teamuser{i+1}",
                phone_number=f"+1-555-000{i+1}",
                dial_code="+1",
                address="123 Main St",
                city="Metropolis",
                country="Freedonia",
                postcode="12345",
            )
            user = user_repository.create_user(session=session, user_create=user_create)
            print(f"Created user: {user.email} (id={user.id})")

        # create a couple of pending invites
        pending_emails = ["pending1+invite@example.com", "pending2+invite@example.com"]
        from app.core.security import get_password_hash
        import secrets

        for e in pending_emails:
            existing = session.exec(select(User).where(User.email == e)).first()
            if existing:
                print(f"Invite user {e} already exists, skipping")
                continue
            pw = secrets.token_urlsafe(12)
            hashed = get_password_hash(pw)
            u = User(email=e, hashed_password=hashed, is_active=False, full_name=None)
            session.add(u)
            session.commit()
            print(f"Created pending invite: {e}")

    # Now populate dashboard data (projects, requests, credit tx) for the created users
    print("Populating dashboard data for users (this may take a while)...")
    populate_main()
    print("Seeding complete.")


if __name__ == "__main__":
    main()
