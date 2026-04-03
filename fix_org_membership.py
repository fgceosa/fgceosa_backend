
import logging
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Organization, OrganizationMember
from app.core.config import settings
from app.core.security import get_password_hash

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def fix_memberships():
    email = settings.FIRST_SUPERUSER
    password = settings.FIRST_SUPERUSER_PASSWORD
    
    logger.info(f"Checking memberships for superuser: {email}")

    with Session(engine) as session:
        # 1. Get user
        user = session.exec(select(User).where(User.email == email)).first()
        if not user:
            logger.info("Superuser not found! Creating one...")
            user = User(
                email=email,
                hashed_password=get_password_hash(password),
                is_superuser=True,
                is_active=True,
                full_name="System Admin",
                account_type="individual",
                status="active"
            )
            session.add(user)
            session.commit()
            session.refresh(user)
            logger.info(f"Created superuser: {user.id}")
        else:
             logger.info(f"User found: {user.id}")

        # 2. Get all organizations
        orgs = session.exec(select(Organization)).all()
        logger.info(f"Found {len(orgs)} organizations.")

        if not orgs:
            # Create a default organization for testing if none exists
            logger.info("No organizations found. Creating 'Default Organization'...")
            default_org = Organization(
                name="Default Organization",
                description="Auto-created organization for testing",
                owner_id=user.id,
                is_active=True
            )
            session.add(default_org)
            session.commit()
            session.refresh(default_org)
            orgs = [default_org]

        for org in orgs:
            # 3. Check membership
            member = session.exec(
                select(OrganizationMember).where(
                    OrganizationMember.organization_id == org.id,
                    OrganizationMember.user_id == user.id
                )
            ).first()

            if not member:
                logger.info(f"Adding user to organization: {org.name} ({org.id})")
                new_member = OrganizationMember(
                    organization_id=org.id,
                    user_id=user.id,
                    role="org_super_admin" # Assign highest role
                )
                session.add(new_member)
            else:
                logger.info(f"User is already member of {org.name}. Role: {member.role}")
                if member.role != "org_super_admin":
                    logger.info(f"Updating role to org_super_admin")
                    member.role = "org_super_admin"
                    session.add(member)
        
        session.commit()
        logger.info("Done fixing memberships.")

if __name__ == "__main__":
    fix_memberships()
