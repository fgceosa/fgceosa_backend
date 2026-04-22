from sqlalchemy import create_engine, text
import os

# Manual DB URI for local testing if env is not loaded
db_uri = "postgresql://fgceosa_admin:fgceosa_secure_pass_2026@localhost:8081/fgceosa_db"

engine = create_engine(db_uri)

def migrate():
    columns = [
        ("category", "VARCHAR(100) DEFAULT 'General'"),
        ("status", "VARCHAR(50) DEFAULT 'Sent'"),
        ("priority", "VARCHAR(50) DEFAULT 'Normal'"),
        ("views", "INTEGER DEFAULT 0"),
        ("engagement", "INTEGER DEFAULT 0"),
        ("image", "TEXT"),
        ("is_important", "BOOLEAN DEFAULT FALSE"),
        ("is_pinned", "BOOLEAN DEFAULT FALSE"),
        ("scheduled_at", "TIMESTAMP")
    ]
    
    with engine.connect() as conn:
        for name, type_def in columns:
            try:
                conn.execute(text(f"ALTER TABLE announcement ADD COLUMN {name} {type_def}"))
                print(f"Added column: {name}")
            except Exception as e:
                print(f"Error adding {name}: {e}")
        conn.commit()

if __name__ == "__main__":
    migrate()
