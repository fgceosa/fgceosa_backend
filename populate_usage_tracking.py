
import uuid
from decimal import Decimal
from datetime import datetime, timezone
from sqlmodel import Session, select
from app.core.db import engine
from app.models import OrganizationCreditTransaction, WorkspaceUsageTracking

def populate_usage_tracking():
    with Session(engine) as session:
        # Get start of current month
        now = datetime.now(timezone.utc)
        start_of_month = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        
        # Next month start
        if now.month == 12:
            end_of_month = datetime(now.year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            end_of_month = datetime(now.year, now.month + 1, 1, tzinfo=timezone.utc)
            
        print(f"Populating usage tracking for period: {start_of_month} to {end_of_month}")
        
        # Find all USAGE transactions in this month
        txs = session.exec(
            select(OrganizationCreditTransaction).where(
                OrganizationCreditTransaction.transaction_type == "usage",
                OrganizationCreditTransaction.created_at >= start_of_month,
                OrganizationCreditTransaction.created_at < end_of_month
            )
        ).all()
        
        print(f"Found {len(txs)} usage transactions.")
        
        # Aggregate by workspace
        usage_by_workspace = {} # workspace_id -> {amount, org_id}
        
        for tx in txs:
            if not tx.workspace_id:
                continue
                
            amount = abs(tx.amount) # Amount is negative for usage
            
            if tx.workspace_id not in usage_by_workspace:
                usage_by_workspace[tx.workspace_id] = {
                    "amount": Decimal("0.0000"),
                    "org_id": tx.organization_id
                }
            
            usage_by_workspace[tx.workspace_id]["amount"] += amount
            
        print(f"Found {len(usage_by_workspace)} workspaces with usage.")
        
        # Update WorkspaceUsageTracking
        for ws_id, data in usage_by_workspace.items():
            tracking = session.exec(
                select(WorkspaceUsageTracking).where(
                    WorkspaceUsageTracking.workspace_id == ws_id,
                    WorkspaceUsageTracking.billing_period_start == start_of_month
                )
            ).first()
            
            if not tracking:
                print(f"Creating new tracking record for Workspace {ws_id}")
                tracking = WorkspaceUsageTracking(
                    workspace_id=ws_id,
                    organization_id=data["org_id"],
                    billing_period_start=start_of_month,
                    billing_period_end=end_of_month,
                    total_usage=Decimal("0.0000"),
                    usage_breakdown={}
                )
                session.add(tracking)
            else:
                print(f"Updating existing tracking record for Workspace {ws_id}. Old usage: {tracking.total_usage}")
                
            # Set to calculated amount (idempotent fix)
            tracking.total_usage = data["amount"]
            session.add(tracking)
            
        session.commit()
        print("Usage tracking populated successfully.")

if __name__ == "__main__":
    try:
        populate_usage_tracking()
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"Failed to populate usage tracking: {e}")
