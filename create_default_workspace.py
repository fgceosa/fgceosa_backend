import logging
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Organization, OrganizationMember, Workspace
from app.core.config import settings
from datetime import datetime, timezone
from decimal import Decimal

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_default_workspace():
    email = settings.FIRST_SUPERUSER
    
    logger.info(f"Creating default workspace for superuser: {email}")

    with Session(engine) as session:
        # 1. Get user
        user = session.exec(select(User).where(User.email == email)).first()
        if not user:
            logger.error("Superuser not found!")
            return

        logger.info(f"User found: {user.id}")

        # 2. Get the organization
        org_member = session.exec(
            select(OrganizationMember).where(OrganizationMember.user_id == user.id)
        ).first()
        
        if not org_member:
            logger.error("User is not a member of any organization!")
            return
        
        org = session.get(Organization, org_member.organization_id)
        if not org:
            logger.error("Organization not found!")
            return
        
        logger.info(f"Organization found: {org.name} ({org.id})")

        # 3. Check if workspace already exists
        existing_workspace = session.exec(
            select(Workspace).where(Workspace.organization_id == org.id)
        ).first()

        if existing_workspace:
            logger.info(f"Workspace already exists: {existing_workspace.name} ({existing_workspace.id})")
            return

        # 4. Create default workspace
        workspace = Workspace(
            name=f"{org.name} - Main Workspace",
            description="Default workspace for your organization",
            organization_id=org.id,
            owner_id=user.id,
            credits_balance=Decimal("1000.0000"),  # Give some initial credits
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )
        session.add(workspace)
        session.commit()
        session.refresh(workspace)
        
        logger.info(f"Created default workspace: {workspace.name} ({workspace.id})")
        logger.info(f"Workspace has {workspace.credits_balance} credits")

if __name__ == "__main__":
    create_default_workspace()
