from collections.abc import Generator
from typing import Annotated, Optional
import logging

import jwt
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from pydantic import ValidationError
from sqlmodel import Session, select

from app.core import security
from app.core.config import settings
from app.core.db import engine
from app.models import TokenPayload, User
from app.utils import permissions as perm_utils

logger = logging.getLogger(__name__)

reusable_oauth2 = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/login/access-token"
)


def get_db() -> Generator[Session, None, None]:
    """Get main database session"""
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()


SessionDep = Annotated[Session, Depends(get_db)]
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
    
    user = session.get(User, token_data.sub)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.status != "active":
        raise HTTPException(status_code=400, detail="Inactive user")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def get_current_user_optional(
    session: SessionDep, 
    token: Annotated[Optional[str], Depends(OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False))] = None
) -> Optional[User]:
    if not token:
        return None
    try:
        return get_current_user(session=session, token=token)
    except HTTPException:
        return None


OptionalCurrentUser = Annotated[Optional[User], Depends(get_current_user_optional)]


def get_current_active_superuser(current_user: CurrentUser) -> User:
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="The user doesn't have enough privileges"
        )
    return current_user


def RequiresPermission(permission: str):
    """FastAPI dependency to check permission"""
    def check_permission(current_user: CurrentUser, session: SessionDep):
        if not perm_utils.user_has_permission(session, current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action Restricted: You do not have the required permission to perform this action."
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
                detail=f"Access Denied: This area is reserved for users with the '{role_display}' role."
            )
        return current_user
    return check_role
