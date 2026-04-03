
import uuid
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from sqlmodel import Session, select
from app.core.db import engine
from app.services.organization_credit_service import OrganizationCreditService
from app.models import Organization

def test_usage_summary():
    with Session(engine) as session:
        # Get first organization
        org = session.exec(select(Organization)).first()
        if not org:
            print("No organization found")
            return
        
        print(f"Testing for org: {org.name} ({org.id})")
        
        end_date = datetime.now(timezone.utc)
        start_date = end_date - timedelta(days=30)
        
        try:
            summary = OrganizationCreditService.get_usage_summary(session, org.id, start_date, end_date)
            print("Successfully generated summary")
            print(f"Total Usage: {summary.total_usage}")
            print(f"Workspaces Count: {len(summary.workspaces_usage)}")
            for ws in summary.workspaces_usage:
                print(f"  - {ws.workspace_name}: {ws.total_usage} ({ws.usage_percentage}%)")
        except Exception as e:
            print(f"FAILED with error: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    test_usage_summary()
