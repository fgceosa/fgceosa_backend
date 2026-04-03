import sys
import os
import traceback
from sqlmodel import Session, create_engine, select, func
from app.models import Organization, OrganizationCreditTransaction, User

try:
    from app.core.config import settings
except ImportError:
    print("Could not import settings.")
    sys.exit(1)

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

def check():
    with Session(engine) as session:
        # Check shopNow (case insensitive or exact match as found)
        shopnow = session.exec(select(Organization).where(Organization.name.ilike("shopNow"))).first()
        if shopnow:
            print(f"Found Organization: {shopnow.name} (ID: {shopnow.id})")
            shop_txs = session.exec(
                select(OrganizationCreditTransaction)
                .where(OrganizationCreditTransaction.organization_id == shopnow.id)
                .order_by(OrganizationCreditTransaction.created_at.desc())
            ).all()
            print(f"Transactions for {shopnow.name} ({len(shop_txs)}):")
            for tx in shop_txs:
                print(f"  {tx.created_at}: {tx.transaction_type} | {tx.amount} | {tx.description}")
        else:
            print("shopNow not found even with ILIKE")

        # Check user by tag
        tag = "qorkdke4c"
        user = session.exec(select(User).where(User.tag_number == tag)).first()
        if user:
            print(f"Found User for tag @{tag}: {user.email} (ID: {user.id})")
        else:
            print(f"User for tag @{tag} NOT found")

if __name__ == "__main__":
    check()
