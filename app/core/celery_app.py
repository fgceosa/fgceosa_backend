"""
Celery Application Configuration
For async task execution (agent jobs, document processing, etc.)
"""
import ssl
from celery import Celery

from app.core.config import settings

# Create Celery app
# Create Celery app
celery_app = Celery(
    "qorebit",
    broker=settings.CELERY_BROKER_URL,
    backend=None,  # Explicitly disable to prevent auto-pickup of env vars
    include=[
        "app.copilot.tasks",
    ],
)

# Configure Redis SSL if using rediss:// (common for managed Redis)
if settings.CELERY_BROKER_URL.startswith("rediss://"):
    celery_app.conf.update(
        broker_use_ssl={"ssl_cert_reqs": ssl.CERT_NONE},
    )

# Celery configuration
celery_app.conf.update(
    result_backend=None,  # Double-ensure no backend is used
    broker_connection_retry_on_startup=True,
    broker_pool_limit=10,
    broker_transport_options={
        "visibility_timeout": 3600,
        "max_retries": 10,
        "interval_start": 0,
        "interval_step": 0.5,
        "interval_max": 3,
    },
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_ignore_result=True,  # Don't store task results in Redis by default

    # Task execution settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_time_limit=600,  # 10 minutes max per task
    task_soft_time_limit=540,  # 9 minutes soft limit

    # Worker settings
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,

    # Result settings
    result_expires=3600,  # Results expire after 1 hour

    # Rate limiting
    task_default_rate_limit="100/m",

    # Retry settings
    task_default_retry_delay=60,
    task_max_retries=3,
)

# Optional: Configure task routes for different queues
celery_app.conf.task_routes = {
    "app.copilot.tasks.execute_agent_task": {"queue": "agents"},
    "app.copilot.tasks.process_document_task": {"queue": "documents"},
    "app.copilot.tasks.generate_embeddings_task": {"queue": "embeddings"},
}
