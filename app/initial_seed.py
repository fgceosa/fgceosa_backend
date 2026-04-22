import logging
from sqlmodel import Session
from app.core.db import engine, init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main() -> None:
    logger.info("Initializing database with roles and superuser...")
    with Session(engine) as session:
        init_db(session)
    logger.info("Database initialization complete.")

if __name__ == "__main__":
    main()
