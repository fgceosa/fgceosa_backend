import uuid
import logging
from sqlmodel import Session, select, delete
from app.core.db import engine, copilot_engine
from app.models import User, Organization
from app.copilot.models import Copilot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("test_cleanup")

def cleanup_test_data():
    """Purge copilots and data created during load/e2e testing"""
    
    # Names to look for
    TEST_MARKERS = ["Load Test Copilot", "E2E Test Copilot"]
    
    # 1. Cleanup Copilot Hub (pgvector DB)
    with Session(copilot_engine) as session:
        for marker in TEST_MARKERS:
            statement = select(Copilot).where(Copilot.name == marker)
            results = session.exec(statement).all()
            
            if results:
                logger.info(f"Found {len(results)} test copilots with marker '{marker}'. Purging...")
                for item in results:
                    # Note: Cascade delete should handle conversations/messages 
                    # if configured in the model, else we do it manually.
                    session.delete(item)
                session.commit()
                logger.info(f"Successfully deleted copilots for '{marker}'.")
            else:
                logger.info(f"No test copilots found with marker '{marker}'.")

    # 2. Cleanup Main DB (if we created test users or orgs)
    # In this run, we used admin@gmail.com, so we don't delete that.
    # But if we had created random orgs, we'd do it here.
    logger.info("Cleanup complete.")

if __name__ == "__main__":
    cleanup_test_data()
