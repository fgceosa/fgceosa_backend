from sqlmodel import SQLModel, create_engine
from app.core.config import settings
import app.models  # Ensure models are loaded

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

print("Tables in Metadata:")
for table in SQLModel.metadata.tables.keys():
    print(f"  - {table}")

from sqlalchemy import inspect
inspector = inspect(engine)
print("\nTables in DB:")
for table_name in inspector.get_table_names():
    print(f"  - {table_name}")
    if table_name == 'user':
        print(f"    Columns: {[c['name'] for c in inspector.get_columns(table_name)]}")
