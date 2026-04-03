import sys
from sqlmodel import Session, create_engine, select
from app.models import OrganizationCreditTransaction, Organization

try:
    from app.core.config import settings
except ImportError:
    sys.exit(1)

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

def check():
    with Session(engine) as session:
        txs = session.exec(
            select(OrganizationCreditTransaction, Organization.name)
            .join(Organization)
            .order_by(OrganizationCreditTransaction.created_at.desc())
            .limit(10)
        ).all()
        
        print(f"Latest 10 Org Transactions:")
        for tx, org_name in txs:
            print(f"  {tx.created_at} | Org: {org_name} | {tx.transaction_type} | {tx.amount} | {tx.description}")

if __name__ == "__main__":
    check()
