from sqlmodel import Session, create_engine
from sqlalchemy import text
from app.core.config import settings

engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

with engine.connect() as conn:
    trans = conn.begin()
    try:
        conn.execute(text('TRUNCATE TABLE audit_log CASCADE'))
        conn.execute(text('TRUNCATE TABLE notification CASCADE'))
        conn.execute(text('TRUNCATE TABLE security_event CASCADE'))
        trans.commit()
        print('✅ Docker database cleaned!')
    except Exception as e:
        trans.rollback()
        print(f'❌ Error: {e}')
