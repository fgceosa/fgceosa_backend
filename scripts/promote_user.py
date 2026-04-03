import sys
import os

# Add the parent directory to sys.path to allow imports from app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Role, UserRole

def promote_user(email: str):
    print(f"Attempting to promote user: {email}")
    
    with Session(engine) as session:
        # 1. Find User
        user = session.exec(select(User).where(User.email == email)).first()
        if not user:
            print(f"❌ Error: User with email '{email}' not found.")
            return

        # 2. Find Platform Super Admin Role
        role_name = "platform_super_admin"
        role = session.exec(select(Role).where(Role.name == role_name)).first()
        if not role:
            print(f"❌ Error: Role '{role_name}' not found.")
            print("   Please run 'python scripts/seed_hq_rbac.py' first.")
            return

        # 3. Update User relationship (UserRole)
        # Check if user already has this role
        existing_user_role = session.exec(
            select(UserRole)
            .where(UserRole.user_id == user.id)
            .where(UserRole.role_id == role.id)
        ).first()

        if not existing_user_role:
             # Add new role mapping
             user_role = UserRole(user_id=user.id, role_id=role.id)
             session.add(user_role)
             print(f"✓ Added '{role_name}' to user roles (UserRole table).")
        else:
             print(f"ℹ User already has '{role_name}' role mapping.")

        # 4. Update legacy superuser flag just in case
        if not user.is_superuser:
            user.is_superuser = True
            session.add(user)
            print("✓ Set is_superuser=True (legacy flag).")
        
        session.commit()
        print(f"\n✅ Successfully promoted {email} to {role_name}.")
        print("   The user effectively has all permissions now.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        target_email = sys.argv[1]
    else:
        print("Enter the email of the user you want to promote to Platform Super Admin.")
        target_email = input("User Email: ").strip()
    
    if target_email:
        promote_user(target_email)
    else:
        print("No email provided. Exiting.")
