"""
RBAC Permission utilities and decorators
"""
from functools import wraps
from typing import List, Optional, Callable, Any
from fastapi import HTTPException, status, Depends
from sqlmodel import Session, select

from app.models import User, Role, Permission, RolePermission, UserRole


def get_user_roles(session: Session, user: User) -> List[str]:
    """Get all roles for a user"""
    user_roles = session.exec(
        select(Role.name)
        .join(UserRole, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id)
    ).all()
    return list(user_roles)


def get_user_permissions(session: Session, user: User) -> List[str]:
    """Get all permissions for a user based on their roles"""
    permissions = session.exec(
        select(Permission.name)
        .join(RolePermission, Permission.id == RolePermission.permission_id)
        .join(Role, RolePermission.role_id == Role.id)
        .join(UserRole, Role.id == UserRole.role_id)
        .where(UserRole.user_id == user.id)
        .where(RolePermission.allowed == True)
    ).all()
    return list(set(permissions))  # Remove duplicates


def user_has_permission(session: Session, user: User, permission: str) -> bool:
    """Check if user has a specific permission"""
    if user.is_superuser:
        return True
    user_permissions = get_user_permissions(session, user)
    return permission in user_permissions


def user_has_any_permission(session: Session, user: User, permissions: List[str]) -> bool:
    """Check if user has any of the specified permissions"""
    if user.is_superuser:
        return True
    user_permissions = get_user_permissions(session, user)
    return any(perm in user_permissions for perm in permissions)


def user_has_role(session: Session, user: User, role: str) -> bool:
    """Check if user has a specific role"""
    if user.is_superuser:
        return True
    user_roles = get_user_roles(session, user)
    return role in user_roles


def user_has_any_role(session: Session, user: User, roles: List[str]) -> bool:
    """Check if user has any of the specified roles"""
    if user.is_superuser:
        return True
    user_roles = get_user_roles(session, user)
    return any(role in user_roles for role in roles)


def assign_role_to_user(session: Session, user: User, role_name: str) -> bool:
    """Assign a role to a user"""
    role = session.exec(select(Role).where(Role.name == role_name)).first()
    if not role:
        return False
    
    # Check if user already has this role
    existing_user_role = session.exec(
        select(UserRole)
        .where(UserRole.user_id == user.id)
        .where(UserRole.role_id == role.id)
    ).first()
    
    if not existing_user_role:
        user_role = UserRole(user_id=user.id, role_id=role.id)
        session.add(user_role)
        session.commit()
    
    return True


def remove_role_from_user(session: Session, user: User, role_name: str) -> bool:
    """Remove a role from a user"""
    role = session.exec(select(Role).where(Role.name == role_name)).first()
    if not role:
        return False
    
    user_role = session.exec(
        select(UserRole)
        .where(UserRole.user_id == user.id)
        .where(UserRole.role_id == role.id)
    ).first()
    
    if user_role:
        session.delete(user_role)
        session.commit()
    
    return True


def requires_permission(permission: str):
    """Decorator to require a specific permission"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get current user and session from dependencies
            current_user = None
            session = None
            
            # Extract dependencies from kwargs
            for key, value in kwargs.items():
                if isinstance(value, User):
                    current_user = value
                elif isinstance(value, Session):
                    session = value
            
            if not current_user or not session:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unable to verify permissions"
                )
            
            if not user_has_permission(session, current_user, permission):
                # Format the permission name
                parts = permission.split(":")
                if len(parts) > 1:
                    resource = parts[0].replace("_", " ").title()
                    action = parts[1].replace("_", " ").title()
                    perm_name = f"{action} {resource}"
                else:
                    perm_name = permission.replace("_", " ").title()
                
                perm_name = perm_name.replace("Organization", "Workspace")

                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Action Restricted: You do not have the '{perm_name}' permission required to perform this action. Please contact your system administrator if you believe this is an error."
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def requires_any_permission(permissions: List[str]):
    """Decorator to require any of the specified permissions"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get current user and session from dependencies
            current_user = None
            session = None
            
            # Extract dependencies from kwargs
            for key, value in kwargs.items():
                if isinstance(value, User):
                    current_user = value
                elif isinstance(value, Session):
                    session = value
            
            if not current_user or not session:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unable to verify permissions"
                )
            
            if not user_has_any_permission(session, current_user, permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Insufficient permissions. Required any of: {', '.join(permissions)}"
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


def requires_role(role: str):
    """Decorator to require a specific role"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get current user and session from dependencies
            current_user = None
            session = None
            
            # Extract dependencies from kwargs
            for key, value in kwargs.items():
                if isinstance(value, User):
                    current_user = value
                elif isinstance(value, Session):
                    session = value
            
            if not current_user or not session:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Unable to verify permissions"
                )
            
            if not user_has_role(session, current_user, role):
                role_display = role.replace("_", " ").title()
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access Denied: This area is reserved for users with the '{role_display}' role. Your current account level does not have sufficient clearance."
                )
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


# FastAPI dependency functions have been moved to app.api.deps 
# to avoid circular imports.