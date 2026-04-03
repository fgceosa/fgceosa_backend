import logging
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Workspace, WorkspaceMember
from app.core.config import settings
from datetime import datetime, timezone
from decimal import Decimal

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def add_user_to_workspace():
    email = settings.FIRST_SUPERUSER
    
    logger.info(f"Adding superuser to workspace: {email}")

    with Session(engine) as session:
        # 1. Get user
        user = session.exec(select(User).where(User.email == email)).first()
        if not user:
            logger.error("Superuser not found!")
            return

        logger.info(f"User found: {user.id}")

        # 2. Get the workspace
        workspace = session.exec(select(Workspace)).first()
        
        if not workspace:
            logger.error("No workspace found!")
            return
        
        logger.info(f"Workspace found: {workspace.name} ({workspace.id})")

        # 3. Check if user is already a member
        existing_member = session.exec(
            select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id,
                WorkspaceMember.user_id == user.id
            )
        ).first()

        if existing_member:
            logger.info(f"User is already a member of workspace. Status: {existing_member.status}")
            # Update to active if not already
            if existing_member.status != "active":
                existing_member.status = "active"
                session.add(existing_member)
                session.commit()
                logger.info("Updated member status to active")
            return

        # 4. Add user as workspace member
        member = WorkspaceMember(
            workspace_id=workspace.id,
            user_id=user.id,
            invited_email=None,  # User already exists
            credits_allocated=Decimal("500.0000"),
            status="active",  # Active immediately since user is owner
            joined_at=datetime.now(timezone.utc),
            last_active=datetime.now(timezone.utc)
        )
        session.add(member)
        session.commit()
        session.refresh(member)
        
        logger.info(f"Added user as workspace member: {member.id}")
        logger.info(f"Member has {member.credits_allocated} allocated credits")

if __name__ == "__main__":
    add_user_to_workspace()
