
import sys
import os
import uuid
import logging
from sqlmodel import Session, select

# Add parent directory to path to import app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Configure logging to see email errors
logging.basicConfig(level=logging.INFO)

from app.core.db import engine
from app.models import User, Organization, OrganizationMember
from app.services.organization_service import invite_member_to_organization, remove_organization_member
from app.api.deps import CurrentUser

def test_email_and_delete():
    print("Starting Email and Delete Test...")
    with Session(engine) as session:
        try:
            # 1. Setup Test Data
            print("Setting up test data...")
            
            # Create Admin User
            admin_email = f"admin_{uuid.uuid4()}@test.com"
            admin_user = User(
                email=admin_email, 
                hashed_password="hash", 
                full_name="Admin User",
                account_type="organization"
            )
            session.add(admin_user)
            session.commit()
            session.refresh(admin_user)
            print(f"Created Admin: {admin_user.email}")

            # Create Org
            org = Organization(name=f"Test Org {uuid.uuid4()}", owner_id=admin_user.id, is_active=True)
            session.add(org)
            session.commit()
            session.refresh(org)
            print(f"Created Org: {org.id}")
            
            # Add Admin to Org
            admin_mem = OrganizationMember(organization_id=org.id, user_id=admin_user.id, role="org_super_admin")
            session.add(admin_mem)
            session.commit()

            # 2. Test Invitation (Email)
            target_email = "jamesoyanna@gmail.com" # Use a likely real email format, or a disposable one
            print(f"\nInviting {target_email}...")
            try:
                invite_member_to_organization(
                    session=session,
                    organization_id=org.id,
                    email=target_email,
                    role="member",
                    inviter=admin_user
                )
                print("Invitation function returned successfully (Frontend would show success).")
            except Exception as e:
                print(f"Invitation function FAILED: {e}")

            # Verify member exists
            invited_user = session.exec(select(User).where(User.email == target_email)).first()
            if invited_user:
                print(f"Invited user create: {invited_user.id}")
                member = session.exec(select(OrganizationMember).where(OrganizationMember.user_id == invited_user.id)).first()
                if member:
                    print(f"Member created with status: {member.status}")
                    
                    # 3. Test Removal (Delete)
                    print(f"\nRemoving member {member.id}...")
                    try:
                        remove_organization_member(
                            session=session,
                            organization_id=org.id,
                            member_id=member.id
                        )
                        print("Removal function returned successfully.")
                    except Exception as e:
                        print(f"Removal function FAILED: {e}")
                        
                        # Inspect the exception for status code
                        if hasattr(e, 'status_code'):
                             print(f"Status Code: {e.status_code}")
                        if hasattr(e, 'detail'):
                             print(f"Detail: {e.detail}")

        except Exception as e:
            print(f"An error occurred: {e}")
        finally:
            # Cleanup
            print("\nCleaning up...")
            # (Cleanup logic omitted for brevity in reproduction script, letting DB roll back or persist for inspection)
            # Actually we should cleanup to avoid clutter
            # session.delete(org) ... 

if __name__ == "__main__":
    test_email_and_delete()
