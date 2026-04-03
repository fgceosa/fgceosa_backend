import logging
from sqlmodel import Session, select
from app.core.db import engine
from app.models import Workspace, Organization

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_workspace_org():
    logger.info("Checking workspace organization relationship...")

    with Session(engine) as session:
        # Get workspace
        workspace = session.exec(select(Workspace)).first()
        
        if not workspace:
            logger.error("No workspace found!")
            return
        
        logger.info(f"Workspace: {workspace.name} ({workspace.id})")
        logger.info(f"Organization ID: {workspace.organization_id}")
        logger.info(f"Owner ID: {workspace.owner_id}")
        logger.info(f"Credits: {workspace.credits_balance}")
        logger.info(f"Status: {workspace.status}")
        
        if workspace.organization_id:
            org = session.get(Organization, workspace.organization_id)
            if org:
                logger.info(f"Organization: {org.name} ({org.id})")
            else:
                logger.warning("Organization ID set but organization not found!")
        else:
            logger.warning("Workspace has no organization_id!")

if __name__ == "__main__":
    check_workspace_org()
