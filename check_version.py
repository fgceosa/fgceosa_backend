from sqlalchemy import create_engine, text
from app.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))
with engine.connect() as conn:
    res = conn.execute(text("SELECT version_num FROM alembic_version")).all()
    print(res)
