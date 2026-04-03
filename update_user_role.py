#!/usr/bin/env python3
"""
Update user role to org_super_admin.

Usage:
    python update_user_role.py <user_email> <role_name>
"""

import sys
import logging
from datetime import datetime, timezone
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Organization, OrganizationMember, Role, UserRole

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def update_user_role(email: str, role_name: str):
    with Session(engine) as session:
        # 1. Find User
        user = session.exec(select(User).where(User.email == email)).first()
        if not user:
            logger.error(f"User not found: {email}")
            return

        logger.info(f"Found User: {user.email} ({user.id})")

        # 2. Find User's Organization Membership
        org_member = session.exec(
            select(OrganizationMember).where(
                OrganizationMember.user_id == user.id
            )
        ).first()

        if org_member:
            logger.info(f"User is member of Organization ID: {org_member.organization_id}")
            logger.info(f"Current Org Role: {org_member.role}")
            
            if org_member.role != role_name:
                org_member.role = role_name
                session.add(org_member)
                session.commit()
                logger.info(f"Updated Org Role to: {role_name}")
            else:
                 logger.info(f"Org Role is already: {role_name}")
        else:
            logger.warning("User is not a member of ANY organization. Skipping OrganizationMember update.")

        # 4. Update RBAC UserRole
        # Find the Role ID for the requested role_name
        target_role = session.exec(select(Role).where(Role.name == role_name)).first()
        if not target_role:
             logger.error(f"RBAC Role '{role_name}' not found in Role table.")
             return

        # Check existing roles
        user_roles = session.exec(select(UserRole).where(UserRole.user_id == user.id)).all()
        
        # Check if user already has this role
        has_role = False
        for ur in user_roles:
            if ur.role_id == target_role.id:
                has_role = True
                break
        
        if not has_role:
            logger.info(f"Assigning RBAC Role: {role_name}")
            new_user_role = UserRole(
                user_id=user.id,
                role_id=target_role.id
            )
            session.add(new_user_role)
            session.commit()
            logger.info("RBAC role assigned.")
        else:
            logger.info(f"User already has RBAC Role: {role_name}")
        
        # Verify
        session.refresh(user)
        logger.info("✅ User role update complete.")


def main():
    if len(sys.argv) < 3:
        # Default for this task
        email = "org@gmail.com"
        role = "org_super_admin"
        print(f"Usage: python update_user_role.py <email> <role>")
        print(f"Running default: {email} -> {role}")
        update_user_role(email, role)
    else:
        email = sys.argv[1]
        role = sys.argv[2]
        update_user_role(email, role)

if __name__ == "__main__":
    main()
