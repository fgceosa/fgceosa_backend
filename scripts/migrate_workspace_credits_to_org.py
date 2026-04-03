
import sys
import os
import uuid
from decimal import Decimal
from sqlmodel import Session, select
import logging

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.db import engine
from app.models import Organization, Workspace, OrganizationCreditTransaction

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_credits():
    with Session(engine) as session:
        # Get all organizations
        orgs = session.exec(select(Organization)).all()
        
        logger.info(f"Found {len(orgs)} organizations.")
        
        for org in orgs:
            workspaces = session.exec(select(Workspace).where(Workspace.organization_id == org.id)).all()
            total_transfer = Decimal(0)
            
            logger.info(f"Processing Org: {org.name} ({org.id})")
            
            for ws in workspaces:
                if ws.credits_balance > 0:
                    amount = ws.credits_balance
                    logger.info(f"  - Workspace {ws.name}: Migrating {amount} credits")
                    total_transfer += amount
                    
                    # Zero out workspace balance to prevent re-migration
                    ws.credits_balance = Decimal(0)
                    session.add(ws)
            
            if total_transfer > 0:
                # Update Org Balance
                org.credits_balance += total_transfer
                session.add(org)
                
                # Create Transaction Record
                tx = OrganizationCreditTransaction(
                    organization_id=org.id,
                    amount=total_transfer,
                    balance_after=org.credits_balance,
                    transaction_type="migration",
                    description=f"Migrated credits from {len(workspaces)} workspaces",
                    performed_by=None # System
                )
                session.add(tx)
                logger.info(f"  => Transferred Total: {total_transfer} to Org Wallet. New Balance: {org.credits_balance}")
            else:
                logger.info("  => No credits to migrate.")
                
        session.commit()
        logger.info("Migration complete!")

if __name__ == "__main__":
    migrate_credits()
