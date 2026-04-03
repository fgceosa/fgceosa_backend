import json
import hashlib
from typing import Any, Optional, Union
from app.core.redis import redis_client
import logging

logger = logging.getLogger(__name__)

class CacheService:
    """
    Unified caching service for the application.
    Supports LLM response caching, session storage, and more.
    """
    
    @staticmethod
    def _generate_key(prefix: str, identifier: Any) -> str:
        """Generate a stable cache key from any picklable object"""
        if isinstance(identifier, (dict, list)):
            identifier_str = json.dumps(identifier, sort_keys=True)
        else:
            identifier_str = str(identifier)
            
        identifier_hash = hashlib.md5(identifier_str.encode()).hexdigest()
        return f"cache:{prefix}:{identifier_hash}"

    async def get_llm_cache(self, model: str, messages: list) -> Optional[dict]:
        """Retrieve cached LLM response if available"""
        key = self._generate_key("llm", {"model": model, "messages": messages})
        cached = await redis_client.get(key)
        if cached:
            logger.info(f"LLM Cache Hit: {key}")
            return json.loads(cached)
        return None

    async def set_llm_cache(self, model: str, messages: list, response: dict, expire: int = 3600):
        """Cache an LLM response for 1 hour by default"""
        key = self._generate_key("llm", {"model": model, "messages": messages})
        await redis_client.set(key, json.dumps(response), ex=expire)
        logger.info(f"LLM Response Cached: {key}")

    async def get_session(self, session_id: str) -> Optional[dict]:
        """Get temporary session memory"""
        key = f"session:{session_id}"
        cached = await redis_client.get(key)
        return json.loads(cached) if cached else None

    async def set_session(self, session_id: str, data: dict, expire: int = 1800):
        """Set temporary session memory (default 30 mins)"""
        key = f"session:{session_id}"
        await redis_client.set(key, json.dumps(data), ex=expire)

cache_service = CacheService()
