import sys
import os
import uuid
from decimal import Decimal

# Import necessary modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from app.api.deps import get_db
from app.models import User, Organization, WalletOwnerType
from app.services.wallet_service import WalletService
from app.services.organization_credit_service import OrganizationCreditService

def run_test():
    gen = get_db()
    session = next(gen)

    # 1. Setup Data
    print("Setting up test data...")
    # Create test user
    admin_user = User(
        email=f"admin_test_{uuid.uuid4()}@test.com",
        full_name="Admin Test",
        hashed_password="hashed_password",
        is_active=True
    )
    session.add(admin_user)
    
    recipient_user = User(
        email=f"recipient_test_{uuid.uuid4()}@test.com",
        full_name="Recipient Test",
        hashed_password="hashed_password",
        is_active=True
    )
    session.add(recipient_user)
    session.commit()
    session.refresh(admin_user)
    session.refresh(recipient_user)

    # Create test organization
    org = Organization(
        name=f"Test Org {uuid.uuid4()}",
    )
    session.add(org)
    session.commit()
    session.refresh(org)

    print(f"Admin User ID: {admin_user.id}")
    print(f"Recipient User ID: {recipient_user.id}")
    print(f"Source Organization ID: {org.id}")

    # 2. Add some credits to the organization
    org_wallet = WalletService.get_or_create_wallet(session, org.id, WalletOwnerType.ORGANIZATION)
    WalletService.top_up_org(
        session=session,
        org_id=org.id,
        amount=Decimal("100.0000"),
        admin_id=admin_user.id,
        reference_id="TEST_TOPUP",
        commit=True
    )
    org_balance_before = WalletService.get_balance(session, org_wallet.id)
    print(f"Organization balance before share: {org_balance_before}")

    recipient_wallet = WalletService.get_or_create_wallet(session, recipient_user.id, WalletOwnerType.USER)
    recipient_balance_before = WalletService.get_balance(session, recipient_wallet.id)
    print(f"Recipient balance before share: {recipient_balance_before}")

    # 3. Share Credits
    share_amount = Decimal("25.0000")
    print(f"Sharing {share_amount} credits from org to recipient...")
    
    OrganizationCreditService.share_credits(
        session=session,
        org_id=org.id,
        member_id=recipient_user.id,
        amount=share_amount,
        admin_id=admin_user.id,
        commit=True
    )

    # 4. Verify Balances
    org_balance_after = WalletService.get_balance(session, org_wallet.id)
    recipient_balance_after = WalletService.get_balance(session, recipient_wallet.id)

    print(f"Organization balance after share: {org_balance_after}")
    print(f"Recipient balance after share: {recipient_balance_after}")

    assert org_balance_after == org_balance_before - share_amount, "Organization balance did not decrease correctly"
    assert recipient_balance_after == recipient_balance_before + share_amount, "Recipient balance did not increase correctly"

    print("Success: Balances updated correctly.")

if __name__ == "__main__":
    run_test()
