
import logging
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, OrganizationMember, WorkspaceMember, Organization, Workspace

logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def diagnose_all_users():
    print("\n" + "="*80)
    print("🔍 DIAGNOSING ALL USERS AND MEMBERSHIPS")
    print("="*80)
    
    with Session(engine) as session:
        users = session.exec(select(User)).all()
        print(f"Found {len(users)} users in total.\n")
        
        for user in users:
            print(f"👤 USER: {user.email} (ID: {user.id})")
            print(f"   Name: {user.full_name}")
            print(f"   Is Superuser: {user.is_superuser}")
            
            # Check Org Membership
            org_memberships = session.exec(select(OrganizationMember).where(OrganizationMember.user_id == user.id)).all()
            if not org_memberships:
                print("   🏢 Organization: [NONE] ❌ (This will cause /organizations/me to 404)")
            else:
                for om in org_memberships:
                    org = session.get(Organization, om.organization_id)
                    print(f"   🏢 Organization: {org.name if org else 'Unknown'} (ID: {om.organization_id})")
                    print(f"       Role: {om.role}, Status: {om.status}")
            
            # Check Workspace Membership
            ws_memberships = session.exec(select(WorkspaceMember).where(WorkspaceMember.user_id == user.id)).all()
            if not ws_memberships:
                print("   💼 Workspaces: [NONE]")
            else:
                for wm in ws_memberships:
                    ws = session.get(Workspace, wm.workspace_id)
                    print(f"   💼 Workspace: {ws.name if ws else 'Unknown'} (ID: {wm.workspace_id})")
                    print(f"       Status: {wm.status}, Credits: {wm.credits_allocated}")
            
            print("-" * 40)

if __name__ == "__main__":
    diagnose_all_users()
