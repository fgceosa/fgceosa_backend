
from sqlmodel import Session, create_engine, select
from app.models import Organization
from app.core.config import settings

def list_orgs():
    engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
    with Session(engine) as session:
        stmt = select(Organization)
        orgs = session.exec(stmt).all()
        for org in orgs:
            print(f"ID: {org.id}, Name: {org.name}, Balance: {org.credits_balance}")

if __name__ == "__main__":
    list_orgs()
