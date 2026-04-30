
import sys
import os
sys.path.append(os.getcwd())

from app.core.db import engine
from sqlalchemy import text, inspect

def add_column():
    inspector = inspect(engine)
    columns = [c['name'] for c in inspector.get_columns('event_registration')]
    
    if 'attendees_count' not in columns:
        print("Column attendees_count missing. Adding it...")
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE event_registration ADD COLUMN attendees_count INTEGER DEFAULT 1"))
        print("Column attendees_count added successfully.")
    else:
        print("Column attendees_count already exists.")

if __name__ == "__main__":
    add_column()
