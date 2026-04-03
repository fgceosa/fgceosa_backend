
import sys
from sqlalchemy import text
from sqlmodel import Session, create_engine
from app.core.config import settings

def find_string_in_db(search_str):
    uri = str(settings.SQLALCHEMY_DATABASE_URI)
    engine = create_engine(uri)
    with Session(engine) as session:
        # Get all tables
        result = session.execute(text("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname = 'public'"))
        tables = [row[0] for row in result]
        
        for table in tables:
            # Get all columns for the table
            result = session.execute(text(f"SELECT column_name FROM information_schema.columns WHERE table_name = '{table}' AND data_type IN ('character varying', 'text', 'json', 'jsonb')"))
            columns = [row[0] for row in result]
            
            if not columns:
                continue
                
            where_clause = " OR ".join([f"CAST(\"{col}\" AS TEXT) ILIKE '%{search_str}%'" for col in columns])
            try:
                query = f"SELECT * FROM \"{table}\" WHERE {where_clause}"
                result = session.execute(text(query))
                rows = result.fetchall()
                if rows:
                    print(f"Found in table '{table}':")
                    for row in rows:
                        print(f"  {row}")
            except Exception as e:
                # print(f"Error querying table {table}: {e}")
                pass

if __name__ == "__main__":
    search_str = sys.argv[1] if len(sys.argv) > 1 else "shopNow"
    find_string_in_db(search_str)
