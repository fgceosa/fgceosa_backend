from sqlalchemy import text
from sqlmodel import create_engine
from app.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

def force_clear_audit_logs():
    with engine.connect() as connection:
        trans = connection.begin()
        try:
            connection.execute(text("TRUNCATE TABLE audit_log CASCADE"))
            trans.commit()
            print("Successfully truncated audit_log table.")
        except Exception as e:
            trans.rollback()
            print(f"Failed to truncate table: {e}")

if __name__ == "__main__":
    force_clear_audit_logs()
