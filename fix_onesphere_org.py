import sys
import os
sys.path.append(os.getcwd())
from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Organization, OrganizationMember, WalletOwnerType
from app.services.wallet_service import WalletService

def update_org():
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == 'onesphereng@gmail.com')).first()
        if not user:
            print("User not found")
            return
        
        member = session.exec(select(OrganizationMember).where(OrganizationMember.user_id == user.id)).first()
        if not member:
            print("User not in any organization")
            return
            
        org = session.get(Organization, member.organization_id)
        if not org:
            print("Organization not found")
            return
            
        print(f"Current Org Name: {org.name}")
        org.name = "Addax Petroleum"
        session.add(org)
        
        # Ensure wallet exists and check balance
        wallet = WalletService.get_or_create_wallet(session, org.id, WalletOwnerType.ORGANIZATION)
        balance = WalletService.get_balance(session, wallet.id)
        
        # Force sync cached balance just in case
        org.credits_balance = balance
        session.add(org)
        
        session.commit()
        session.refresh(org)
        
        print(f"Updated Org Name: {org.name}")
        print(f"Wallet Balance: {balance}")
        print(f"Cached Credit Balance: {org.credits_balance}")

if __name__ == "__main__":
    update_org()
