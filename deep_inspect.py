import sys
import traceback
from sqlmodel import Session, create_engine, select, func
from app.models import Organization, OrganizationCreditTransaction, User, AuditLog, WalletTransaction

try:
    from app.core.config import settings
except ImportError:
    sys.exit(1)

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

def check():
    with Session(engine) as session:
        # 1. Search for users with tags similar to qorkdke4c
        print("--- User Tag Search ---")
        users = session.exec(select(User)).all()
        found_user = None
        for u in users:
            if u.tag_number and ("qork" in u.tag_number.lower() or "dke" in u.tag_number.lower()):
                print(f"User: {u.email} | Tag: {u.tag_number} | ID: {u.id}")
                found_user = u
        
        # 2. Check Audit Logs for last 30 mins
        print("\n--- Recent Audit Logs (last hour) ---")
        from datetime import datetime, timedelta, timezone
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        logs = session.exec(
            select(AuditLog)
            .where(AuditLog.timestamp >= one_hour_ago)
            .order_by(AuditLog.timestamp.desc())
        ).all()
        for log in logs:
            print(f"{log.timestamp} | {log.action} | {log.target_type} | {log.meta_data}")

        # 3. Check Wallet Transactions (Ledger) for last hour
        print("\n--- Recent Wallet Transactions (Ledger) ---")
        ledger = session.exec(
            select(WalletTransaction)
            .where(WalletTransaction.created_at >= one_hour_ago)
            .order_by(WalletTransaction.created_at.desc())
        ).all()
        for tx in ledger:
            print(f"{tx.created_at} | Wallet: {tx.wallet_id} | Type: {tx.transaction_type} | Amt: {tx.amount} | Desc: {tx.description}")

        # 4. Check for Organization 'ShopNow' (any casing)
        print("\n--- shopNow Detail ---")
        org = session.exec(select(Organization).where(Organization.name.ilike("shopNow"))).first()
        if org:
            print(f"Org: {org.name} | ID: {org.id} | Balance: {org.credits_balance}")
            # Check if there are ANY transactions created today
            today_txs = session.exec(
                select(OrganizationCreditTransaction)
                .where(OrganizationCreditTransaction.organization_id == org.id)
                .where(OrganizationCreditTransaction.created_at >= one_hour_ago)
            ).all()
            print(f"Today's Org Transactions: {len(today_txs)}")
        else:
            print("Org 'shopNow' not found.")

if __name__ == "__main__":
    check()
