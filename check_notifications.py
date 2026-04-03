from sqlmodel import Session, create_engine, select
from app.core.config import settings
from app.models import Notification

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

def check_notifications():
    with Session(engine) as session:
        statement = select(Notification).limit(5)
        results = session.exec(statement).all()
        print(f"Found {len(results)} notification records.")
        for n in results:
            print(f"ID: {n.id}, Title: {n.title}, Type: {n.type}")

if __name__ == "__main__":
    check_notifications()
