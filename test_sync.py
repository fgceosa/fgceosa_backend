
import asyncio
from sqlmodel import Session, create_engine
from app.core.config import settings
from app.services.requesty_sync import requesty_sync_service

# Database connection
engine = create_engine(str(settings.SQLALCHEMY_DATABASE_URI))

async def test_sync():
    with Session(engine) as session:
        print("Starting sync...")
        result = await requesty_sync_service.sync_models(session)
        print(f"Sync result: {result}")

if __name__ == "__main__":
    asyncio.run(test_sync())
