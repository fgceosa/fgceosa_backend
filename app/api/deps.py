from collections.abc import Generator
from typing import Annotated, Optional
import hashlib
import logging

import jwt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.core.db import engine, copilot_engine
from app.models import TokenPayload, User
from app.utils import permissions as perm_utils

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    """Get main database session (port 5432) with explicit closure to prevent leaks"""
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


def get_copilot_db() -> Generator[Session, None, None]:
    """Get Copilot Hub database session with explicit closure to prevent leaks"""
    session = Session(copilot_engine)
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_db)]
CopilotSessionDep = Annotated[Session, Depends(get_copilot_db)]
TokenDep = Annotated[str, Depends(reusable_oauth2)]


def get_current_user(session: SessionDep, token: TokenDep) -> User:
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )
    
    # Platform session invalidation or additional checks can be added here
    # Ensure current table existence before adding lookups to every request

    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != "active":
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


from fastapi import Request

async def get_user_from_api_key(session: Session, api_key: str, request: Request = None) -> User:
    """
    Authenticate a user using an API key

    Args:
        session: Database session
        api_key: The API key (format: qb_live_XXXXXXXX)
        request: FastAPI request object for security validation

    Returns:
        User object if key is valid

    Raises:
        HTTPException: If key is invalid or expired
    """
    from datetime import datetime, timezone
    from app.models import APIKey

    # Hash the API key to compare with stored hash
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    # Find the API key in database
    statement = select(APIKey).where(
        APIKey.key_hash == key_hash,
        APIKey.is_active == True
    )
    api_key_record = session.exec(statement).first()

    if not api_key_record:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key"
        )

    # Check expiration
    if api_key_record.expires_at:
        if datetime.now(timezone.utc) > api_key_record.expires_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API key has expired"
            )

    # Security Best Practice: IP Whitelisting
    if request and api_key_record.allowed_ips:
        client_ip = request.client.host
        allowed_ips = [ip.strip() for ip in api_key_record.allowed_ips.split(",") if ip.strip()]
        if allowed_ips and client_ip not in allowed_ips:
            # Check for CIDR or partial matches if needed, but for now exact match
            logger.warning(f"Unauthorized IP {client_ip} tried using API key {api_key_record.id}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requests from IP {client_ip} are not allowed for this API key"
            )

    # Security Best Practice: Domain Whitelisting (CORS-like)
    if request and api_key_record.allowed_domains:
        origin = request.headers.get("origin") or request.headers.get("referer")
        if origin:
            # Extract domain from origin
            from urllib.parse import urlparse
            domain = urlparse(origin).netloc
            allowed_domains = [d.strip().lower() for d in api_key_record.allowed_domains.split(",") if d.strip()]
            if allowed_domains and domain not in allowed_domains:
                logger.warning(f"Unauthorized domain {domain} tried using API key {api_key_record.id}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Requests from domain {domain} are not allowed for this API key"
                )

    # Update last used timestamp
    api_key_record.last_used_at = datetime.now(timezone.utc)
    session.add(api_key_record)
    session.commit()

    # Get and return the user
    user = session.get(User, api_key_record.user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found"
        )

    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive"
        )

    return user


async def get_current_user_flexible(
    session: SessionDep,
    request: Request,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
) -> User:
    """
    Authenticate user via either API Key or JWT Token

    Supports two authentication methods:
    1. API Key: Authorization: Bearer qb_live_XXXXXXXX
    2. JWT Token: Authorization: Bearer eyJhbGc...

    This allows both web app users (JWT) and external developers (API keys)
    to access the same endpoints.

    Args:
        session: Database session
        request: FastAPI request object
        authorization: Authorization header value
        x_api_key: X-API-Key header value

    Returns:
        Authenticated User object

    Raises:
        HTTPException: If authentication fails
    """
    # Try to get API key from X-API-Key header first
    if x_api_key:
        return await get_user_from_api_key(session, x_api_key.strip(), request)

    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header or X-API-Key required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization header format. Expected: 'Bearer <token>'",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract the token/key
    token_or_key = authorization.replace("Bearer ", "").strip()

    # Check if it's an API key (starts with qb_live_)
    if token_or_key.startswith("qb_live_"):
        # API Key authentication
        return await get_user_from_api_key(session, token_or_key, request)

    # Otherwise, treat as JWT token
    try:
        payload = jwt.decode(
            token_or_key, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        token_data = TokenPayload(**payload)
    except (InvalidTokenError, ValidationError):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Could not validate credentials",
        )

    # Check for global session invalidation (fault-tolerant)
    try:
        from app.models import SecurityConfig
        from datetime import datetime, timezone
        config = session.get(SecurityConfig, 1)
        if config and config.sessions_invalidated_at and token_data.iat:
            if token_data.iat < config.sessions_invalidated_at.timestamp():
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Your session has been invalidated. Please log in again.",
                )
    except (Exception,):
        # Fail safe
        pass

    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != "active":
        raise HTTPException(status_code=400, detail="Inactive user")

    return user


# Flexible authentication dependency for AI endpoints
CurrentUserFlexible = Annotated[User, Depends(get_current_user_flexible)]


def RequiresPermission(permission: str):
    """FastAPI dependency to check permission"""
    def check_permission(current_user: CurrentUser, session: SessionDep):
        if not perm_utils.user_has_permission(session, current_user, permission):
            # Format the permission name for a user-friendly message
            # e.g., "copilot:create" -> "Create Copilots"
            parts = permission.split(":")
            if len(parts) > 1:
                resource = parts[0].replace("_", " ").title()
                action = parts[1].replace("_", " ").title()
                perm_name = f"{action} {resource}"
            else:
                perm_name = permission.replace("_", " ").title()
            
            # Align with Workspace terminology
            perm_name = perm_name.replace("Organization", "Workspace")
            
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action Restricted: You do not have the '{perm_name}' permission required to perform this action. Please contact your system administrator if you believe this is an error."
            )
        return current_user
    return check_permission


def RequiresRole(role: str):
    """FastAPI dependency to check role"""
    def check_role(current_user: CurrentUser, session: SessionDep):
        if not perm_utils.user_has_role(session, current_user, role):
            role_display = role.replace("_", " ").title()
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access Denied: This area is reserved for users with the '{role_display}' role. Your current account level does not have sufficient clearance."
            )
        return current_user
    return check_role
