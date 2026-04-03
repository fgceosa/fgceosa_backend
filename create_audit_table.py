from sqlmodel import SQLModel, create_engine
from app.core.config import settings
from app.models import AuditLog # This ensures AuditLog is registered

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

def create_tables():
    print("Creating tables...")
    SQLModel.metadata.create_all(engine)
    print("Done.")

if __name__ == "__main__":
    create_tables()
