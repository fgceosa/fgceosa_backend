import sentry_sdk
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.api.main import api_router
from app.core.config import settings
from app.core.logging import setup_logging
import logging

# Initialize structured logging
setup_logging()
logger = logging.getLogger(__name__)

# Filter out health check logs to reduce terminal noise
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        # FastAPI/Uvicorn access logs have the path in record.args[2] or as part of the message
        # We check both to be safe
        args = record.args
        if args and len(args) >= 3:
            path = str(args[2])
            if "/health-check" in path:
                return False
        return True

# Apply the filter to uvicorn access logger
logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())


def custom_generate_unique_id(route: APIRoute) -> str:
    if route.tags:
        return f"{route.tags[0]}-{route.name}"
    else:
        return f"untagged-{route.name}"


if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=str(settings.SENTRY_DSN),
        enable_tracing=True,
        traces_sample_rate=1.0,
        send_default_pii=True,
    )

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
)

# Set all CORS enabled origins
if settings.all_cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.all_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.add_middleware(GZipMiddleware, minimum_size=500)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/sentry-debug")
async def trigger_error():
    division_by_zero = 1 / 0
    return {"message": "If you see this, the error was caught"}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    import logging
    import sentry_sdk
    logger = logging.getLogger(__name__)
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    sentry_sdk.capture_exception(exc)  # Explicitly send to Sentry
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error"}
    )

@app.on_event("startup")
async def startup_event():
    """Initialize FGCEOSA Database and Roles on startup"""
    import logging
    logger = logging.getLogger(__name__)

    try:
        from app.core.db import engine, init_db
        from sqlmodel import Session
        from sqlalchemy import text
        
        # Ensure critical columns exist (handles cases where Alembic migrations fail)
        logger.info("Ensuring payment table columns exist...")
        try:
            with engine.connect() as conn:
                # Check if the payment table exists in the database
                table_exists = conn.execute(text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'payment')"
                )).scalar()
                if table_exists:
                    conn.execute(text("ALTER TABLE payment ADD COLUMN IF NOT EXISTS receipt_url VARCHAR(1000)"))
                    conn.execute(text("ALTER TABLE payment ADD COLUMN IF NOT EXISTS rejection_reason TEXT"))
                    conn.commit()
                    logger.info("Payment table columns verified.")
                else:
                    logger.warning("Payment table does not exist yet. Skipping database alteration checks.")
        except Exception as e:
            logger.warning(f"Could not verify or alter payment columns on startup: {e}")

        # Initialize Main DB (Create roles and first superuser if missing)
        logger.info("Initializing Main database (roles and superuser)...")
        with Session(engine) as session:
            init_db(session)
            
            # EMERGENCY FIX: Re-enable admin@fgceosa.org
            from app.models import User
            from sqlmodel import select
            admin = session.exec(select(User).where(User.email == "admin@fgceosa.org")).first()
            if admin and not admin.is_active:
                admin.is_active = True
                admin.status = "active"
                session.add(admin)
                session.commit()
                logger.info("Admin account successfully re-enabled!")

        logger.info("Main database initialization complete.")

    except Exception as e:
        logger.error(f"Critical error during startup initialization: {e}")


# Mount static files for uploads (avatars, etc.)
uploads_dir = Path("uploads")
uploads_dir.mkdir(exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
