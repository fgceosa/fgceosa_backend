import psycopg
from sqlalchemy import create_engine, text
from app.core.config import settings

def fix_db():
    # Use the same URI that the app uses, but fallback if needed
    db_uri = str(settings.SQLALCHEMY_DATABASE_URI)
    print(f"Connecting to: {db_uri}")
    
    try:
        engine = create_engine(db_uri)
        with engine.connect() as conn:
            print("Checking/Adding columns to system_settings...")
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS bank_name TEXT;"))
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS account_number TEXT;"))
            conn.execute(text("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS account_name TEXT;"))
            conn.commit()
            print("Columns verified/added successfully!")
    except Exception as e:
        print(f"Error using engine: {e}")
        
        # Try raw psycopg as fallback
        try:
            print("Attempting raw psycopg connection...")
            conn = psycopg.connect(
                host=settings.POSTGRES_SERVER,
                port=settings.POSTGRES_PORT,
                dbname=settings.POSTGRES_DB,
                user=settings.POSTGRES_USER,
                password=settings.POSTGRES_PASSWORD,
                connect_timeout=5
            )
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS bank_name VARCHAR(255);")
                cur.execute("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS account_number VARCHAR(50);")
                cur.execute("ALTER TABLE system_settings ADD COLUMN IF NOT EXISTS account_name VARCHAR(255);")
                print("Columns added successfully via raw psycopg!")
            conn.close()
        except Exception as e2:
            print(f"Fatal Error: {e2}")

if __name__ == "__main__":
    fix_db()
