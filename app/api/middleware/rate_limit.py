import time
from fastapi import Request, HTTPException, status
from app.core.redis import redis_client
from app.api.deps import get_current_user
import logging

logger = logging.getLogger(__name__)

async def rate_limiter(request: Request, limit: int = 100, window: int = 600):
    """
    Simpler custom rate limiter middleware using Redis.
    Default: 100 requests per 10 minutes (600 seconds) per user/IP.
    """
    # 1. Identify client (User ID or IP)
    # We try to get user from token first, else fallback to IP
    client_id = request.client.host
    
    # Try to extract user from Authorization header if present
    auth_header = request.headers.get("Authorization")
    if auth_header:
        # Note: We don't want to perform full DB auth here for speed, 
        # so we just use the token hash as ID
        client_id = f"token:{hash(auth_header)}"

    key = f"rate_limit:{client_id}"
    
    # 2. Use Redis to count requests
    # In a real production app, use the sliding window or leaky bucket algorithm.
    current_count = await redis_client.get(key)
    
    if current_count and int(current_count) >= limit:
        logger.warning(f"Rate limit exceeded for {client_id}")
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please wait before trying again."
        )
    
    # Increment count and set expiration if new
    async with redis_client.pipeline() as pipe:
        await pipe.incr(key)
        await pipe.expire(key, window)
        await pipe.execute()

    return True
