from sqlmodel import Session, create_engine, select
from app.core.config import settings
from app.models import AuditLog

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

def check_audit_logs():
    with Session(engine) as session:
        statement = select(AuditLog).limit(5)
        results = session.exec(statement).all()
        print(f"Found {len(results)} audit log entries.")
        for log in results:
            print(f"ID: {log.id}, Action: {log.action}, Actor: {log.actor_name}")

if __name__ == "__main__":
    check_audit_logs()
