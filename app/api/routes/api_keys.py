"""
API Keys Management Routes

Handles:
- Creating API keys for developers
- Listing user's API keys
- Revoking API keys
- Tracking API key usage

API keys allow users to use the AI Engine in their own applications
without exposing their JWT tokens.
"""
import logging
import secrets
import hashlib
import uuid
from typing import Any
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status, Depends, Header
from sqlmodel import select, func, col

from app.api.deps import SessionDep, CurrentUser, RequiresPermission
from app.models import (
    APIKey,
    APIKeyPublic,
    APIKeyCreate,
    APIKeyCreated,
    APIKeysResponse,
    Project,
    User,
)

from app.services import api_key_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


# ==================== Endpoints ====================

@router.post("", response_model=APIKeyCreated, status_code=201, dependencies=[Depends(RequiresPermission("api:access"))])
async def create_api_key(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    key_create: APIKeyCreate,
) -> Any:
    """
    Create a new API key for the current user

    The API key is only shown once in the response.
    Store it securely - you won't be able to retrieve it again.

    API keys allow you to use the AI Engine programmatically
    without exposing your JWT authentication token.
    """

    api_key_record, plain_key = api_key_service.create_api_key(
        session=session,
        user_id=current_user.id,
        name=key_create.name,
        expires_in_days=key_create.expires_in_days,
        allowed_ips=key_create.allowed_ips,
        allowed_domains=key_create.allowed_domains
    )

    return APIKeyCreated(
        id=api_key_record.id,
        name=api_key_record.name,
        key=plain_key,  # Only time the actual key is returned!
        key_prefix=api_key_record.key_prefix,
        created_at=api_key_record.created_at,
        expires_at=api_key_record.expires_at,
    )


@router.get("", response_model=APIKeysResponse, dependencies=[Depends(RequiresPermission("api:access"))])
async def list_api_keys(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    List all API keys for the current user

    Returns all keys (active and inactive) with usage statistics
    """

    # Get total count
    count_stmt = select(func.count()).select_from(APIKey).where(
        APIKey.user_id == current_user.id
    )
    total = session.exec(count_stmt).one()

    # Get all keys with project info
    statement = (
        select(APIKey, Project)
        .outerjoin(Project, col(APIKey.id) == col(Project.api_key_id))
        .where(APIKey.user_id == current_user.id)
        .order_by(col(APIKey.created_at).desc())
    )
    results = session.exec(statement).all()

    api_keys = []
    for api_key, project in results:
        api_key_dict = api_key.model_dump()
        if project:
            api_key_dict["project_id"] = project.id
            api_key_dict["project_name"] = project.name
        api_keys.append(APIKeyPublic(**api_key_dict))

    return APIKeysResponse(
        keys=api_keys,
        total=total,
    )


@router.delete("/{key_id}", status_code=204, dependencies=[Depends(RequiresPermission("api:access"))])
async def delete_api_key(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    key_id: uuid.UUID,
) -> None:
    """
    Delete an API key permanently

    The key will be removed from the database and can no longer be used.
    This action cannot be undone.
    """

    # Get the API key
    statement = select(APIKey).where(
        APIKey.id == key_id,
        APIKey.user_id == current_user.id
    )
    api_key = session.exec(statement).first()

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    # Delete the key from database
    session.delete(api_key)
    session.commit()

    logger.info(f"Deleted API key {key_id} for user {current_user.email}")


@router.get("/{key_id}", response_model=APIKeyPublic, dependencies=[Depends(RequiresPermission("api:access"))])
async def get_api_key(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    key_id: uuid.UUID,
) -> Any:
    """
    Get details about a specific API key

    Returns usage statistics and metadata
    """

    statement = (
        select(APIKey, Project)
        .outerjoin(Project, col(APIKey.id) == col(Project.api_key_id))
        .where(
            APIKey.id == key_id,
            APIKey.user_id == current_user.id
        )
    )
    result = session.exec(statement).first()

    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API key not found"
        )

    api_key, project = result
    api_key_dict = api_key.model_dump()
    if project:
        api_key_dict["project_id"] = project.id
        api_key_dict["project_name"] = project.name

    return APIKeyPublic(**api_key_dict)
