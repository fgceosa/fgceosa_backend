from sqlmodel import Session, create_engine, select
from app.core.config import settings
from app.models import SecurityEvent

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

def check_security_events():
    with Session(engine) as session:
        statement = select(SecurityEvent).limit(5)
        results = session.exec(statement).all()
        print(f"Found {len(results)} security event entries.")
        for event in results:
            print(f"ID: {event.id}, Description: {event.description}")

if __name__ == "__main__":
    check_security_events()
