
from sqlmodel import Session, create_engine, select
from app.models import OrganizationCreditTransaction, Organization
from app.core.config import settings

def check_recent_transactions():
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    with Session(engine) as session:
        stmt = select(OrganizationCreditTransaction).order_by(OrganizationCreditTransaction.created_at.desc()).limit(10)
        txs = session.exec(stmt).all()
        for tx in txs:
            org = session.get(Organization, tx.organization_id)
            org_name = org.name if org else "Unknown"
            print(f"TX: {tx.created_at}, Org: {org_name}, Amount: {tx.amount}, Type: {tx.transaction_type}, Desc: {tx.description}")

if __name__ == "__main__":
    check_recent_transactions()
