import logging
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Organization, OrganizationMember, Workspace, WorkspaceMember, Role, UserRole
from app.core.security import get_password_hash
from datetime import datetime, timezone
from decimal import Decimal

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def setup_org_admin():
    """Setup hello@devscourtai.com as org_super_admin"""
    email = "hello@devscourtai.com"
    password = "org_super_admin"  # You can change this
    
    logger.info(f"Setting up org admin: {email}")

    with Session(engine) as session:
        # 1. Check if user exists
        user = session.exec(select(User).where(User.email == email)).first()
        
        if not user:
            logger.info("User not found. Creating...")
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                is_superuser=False,  # NOT a platform admin
                is_active=True,
                full_name="Organization Admin",
                account_type="organization",
                status="active"
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info(f"Created user: {user.id}")
        else:
            logger.info(f"User exists: {user.id}")
            # Update password if needed
            user.hashed_password = get_password_hash(password)
            user.is_active = True
            user.status = "active"
            session.add(user)
            session.commit()

        # 2. Get or create organization
        org = session.exec(select(Organization)).first()
        
        if not org:
            logger.info("Creating organization...")
            org = Organization(
                name="DevsCourt AI",
                description="Main organization",
                owner_id=user.id,
                is_active=True,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(org)
            session.commit()
            session.refresh(org)
            logger.info(f"Created organization: {org.id}")
        else:
            logger.info(f"Organization exists: {org.name} ({org.id})")

        # 3. Add user to organization as org_super_admin
        org_member = session.exec(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == org.id,
                OrganizationMember.user_id == user.id
            )
        ).first()

        if not org_member:
            logger.info("Adding user to organization as org_super_admin...")
            org_member = OrganizationMember(
                organization_id=org.id,
                user_id=user.id,
                role="org_super_admin",
                joined_at=datetime.now(timezone.utc)
            )
            session.add(org_member)
            session.commit()
            logger.info("User added to organization")
        else:
            logger.info(f"User already in organization. Role: {org_member.role}")
            if org_member.role != "org_super_admin":
                org_member.role = "org_super_admin"
                session.add(org_member)
                session.commit()
                logger.info("Updated role to org_super_admin")

        # 4. Assign org_super_admin RBAC role
        org_super_admin_role = session.exec(
            select(Role).where(Role.name == "org_super_admin")
        ).first()

        if org_super_admin_role:
            # Check if user already has this role
            existing_user_role = session.exec(
                select(UserRole).where(
                    UserRole.user_id == user.id,
                    UserRole.role_id == org_super_admin_role.id
                )
            ).first()

            if not existing_user_role:
                logger.info("Assigning org_super_admin RBAC role...")
                user_role = UserRole(
                    user_id=user.id,
                    role_id=org_super_admin_role.id
                )
                session.add(user_role)
                session.commit()
                logger.info("RBAC role assigned")
            else:
                logger.info("User already has org_super_admin RBAC role")
        else:
            logger.warning("org_super_admin role not found in RBAC system")

        # 5. Get or create workspace
        workspace = session.exec(
            select(Workspace).where(Workspace.organization_id == org.id)
        ).first()

        if not workspace:
            logger.info("Creating workspace...")
            workspace = Workspace(
                name=f"{org.name} - Main Workspace",
                description="Main workspace",
                organization_id=org.id,
                owner_id=user.id,
                credits_balance=Decimal("1000.0000"),
                status="active",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )
            session.add(workspace)
            session.commit()
            session.refresh(workspace)
            logger.info(f"Created workspace: {workspace.id}")
        else:
            logger.info(f"Workspace exists: {workspace.name} ({workspace.id})")

        # 6. Add user to workspace
        ws_member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == user.id
            )
        ).first()

        if not ws_member:
            logger.info("Adding user to workspace...")
            ws_member = WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                invited_email=None,
                credits_allocated=Decimal("500.0000"),
                status="active",
                joined_at=datetime.now(timezone.utc),
                last_active=datetime.now(timezone.utc)
            )
            session.add(ws_member)
            session.commit()
            logger.info("User added to workspace")
        else:
            logger.info(f"User already in workspace. Status: {ws_member.status}")
            if ws_member.status != "active":
                ws_member.status = "active"
                session.add(ws_member)
                session.commit()

        logger.info("\n" + "="*60)
        logger.info("SETUP COMPLETE!")
        logger.info("="*60)
        logger.info(f"Email: {email}")
        logger.info(f"Password: {password}")
        logger.info(f"Role: org_super_admin")
        logger.info(f"Organization: {org.name}")
        logger.info(f"Workspace: {workspace.name}")
        logger.info("="*60)

if __name__ == "__main__":
    setup_org_admin()
