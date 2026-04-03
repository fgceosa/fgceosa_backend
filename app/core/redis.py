import redis.asyncio as redis
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class RedisEngine:
    """
    Centralized Redis client engine for asynchronous operations.
    Handles connection pooling and SSL for cloud environments.
    """
    
    _instance = None
    _client: redis.Redis = None

    @classmethod
    def get_client(cls) -> redis.Redis:
        """Get or initialize the async Redis client"""
        if cls._client is None:
            # Handle SSL for managed Redis (rediss://)
            is_ssl = settings.REDIS_URL.startswith("rediss://")
            
            cls._client = redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=5.0,
                socket_connect_timeout=5.0,
                retry_on_timeout=True,
                # ssl_cert_reqs="none" if is_ssl else None, # Common for Render/Heroku
            )
            logger.info("Async Redis client initialized.")
        return cls._client

    @classmethod
    async def close(cls):
        """Close the Redis connection pool"""
        if cls._client:
            await cls._client.close()
            cls._client = None
            logger.info("Async Redis client closed.")

# Singleton instance
redis_client = RedisEngine.get_client()
