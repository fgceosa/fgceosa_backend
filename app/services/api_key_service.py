"""
API Key Service Layer

Contains business logic for API key generation, hashing, and management.
"""
import secrets
import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Tuple

from sqlmodel import Session, select
from app.models import APIKey, User

logger = logging.getLogger(__name__)

def generate_api_key_string() -> str:
    """
    Generate a secure API key string
    Format: qb_live_XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
    """
    random_part = secrets.token_urlsafe(32)
    return f"qb_live_{random_part}"

def hash_api_key(key: str) -> str:
    """Hash an API key for secure storage"""
    return hashlib.sha256(key.encode()).hexdigest()

def get_key_prefix(key: str) -> str:
    """Get the first 12 characters of the key for display"""
    return key[:12] + "..."

def create_api_key(
    *,
    session: Session,
    user_id: uuid.UUID,
    name: str,
    expires_in_days: int | None = None,
    allowed_ips: str | None = None,
    allowed_domains: str | None = None
) -> Tuple[APIKey, str]:
    """
    Create a new API key record and return it with the plain key string.
    
    Args:
        session: Database session
        user_id: User who owns the key
        name: Friendly name for the key
        expires_in_days: Optional expiration time
        
    Returns:
        Tuple of (APIKey record, plain_key_string)
    """
    plain_key = generate_api_key_string()
    key_hash = hash_api_key(plain_key)
    key_prefix = get_key_prefix(plain_key)

    expires_at = None
    if expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

    api_key_record = APIKey(
        user_id=user_id,
        name=name,
        key_prefix=key_prefix,
        key_hash=key_hash,
        is_active=True,
        expires_at=expires_at,
        allowed_ips=allowed_ips,
        allowed_domains=allowed_domains,
    )

    session.add(api_key_record)
    session.commit()
    session.refresh(api_key_record)

    logger.info(f"Created API key {api_key_record.id} for user {user_id}")
    
    return api_key_record, plain_key
