from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
with engine.connect() as conn:
    conn.execute(text("UPDATE alembic_version SET version_num = '36eb937fa518'"))
    conn.commit()
print("Stamped DB to 36eb937fa518")
