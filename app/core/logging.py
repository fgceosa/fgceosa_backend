import logging
import sys
import structlog
from app.core.config import settings

def setup_logging():
    """Configure structured logging for the application"""
    
    # Standard Python logging configuration
    logging_level = logging.INFO
    
    processors = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    # In production/staging, we want JSON output for easier parsing
    if settings.ENVIRONMENT != "local":
        processors.append(structlog.processors.JSONRenderer())
    else:
        # Locally, pretty-print for humans
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Root logger
    handler = logging.StreamHandler(sys.stdout)
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging_level)

    # Disable other loggers to avoid duplication if needed
    # logging.getLogger("uvicorn.access").propagate = False
