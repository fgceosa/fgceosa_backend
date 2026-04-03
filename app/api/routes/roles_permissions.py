"""
API routes for Roles and Permissions management
"""
from uuid import UUID
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.api.deps import get_current_active_superuser, SessionDep, RequiresPermission
from app.schemas.roles_permissions import (
    RoleCreate,
    RoleUpdate,
    RolePublic,
    RolesListPublic,
    PermissionPublic,
    PermissionGroupPublic,
    PermissionCreate
)
from app.services import roles_permissions_service as rp_service


router = APIRouter()


@router.get("", response_model=list[RolePublic], dependencies=[Depends(RequiresPermission("user:roles_assign"))])
def get_roles(
    session: SessionDep,
) -> list[RolePublic]:
    """
    Get all roles with their permissions grouped by category.
    Only accessible by platform super admins.
    """
    return rp_service.get_all_roles(session)


@router.get("/{role_id}", response_model=RolePublic, dependencies=[Depends(RequiresPermission("user:roles_assign"))])
def get_role(
    role_id: UUID,
    session: SessionDep,
) -> RolePublic:
    """
    Get a specific role by ID with all permissions.
    Only accessible by platform super admins.
    """
    return rp_service.get_role_by_id(session, role_id)


@router.post("", response_model=RolePublic, status_code=status.HTTP_201_CREATED, dependencies=[Depends(RequiresPermission("user:roles_assign"))])
def create_role(
    role_data: RoleCreate,
    session: SessionDep,
) -> RolePublic:
    """
    Create a new custom role with specified permissions.
    Only accessible by platform super admins.
    """
    return rp_service.create_role(session, role_data)


@router.put("/{role_id}", response_model=RolePublic, dependencies=[Depends(RequiresPermission("user:roles_assign"))])
def update_role(
    role_id: UUID,
    role_data: RoleUpdate,
    session: SessionDep,
) -> RolePublic:
    """
    Update an existing role.
    System roles cannot have their names changed.
    Only accessible by platform super admins.
    """
    return rp_service.update_role(session, role_id, role_data)


@router.delete("/{role_id}", dependencies=[Depends(RequiresPermission("user:roles_assign"))])
def delete_role(
    role_id: UUID,
    session: SessionDep,
) -> dict:
    """
    Delete a custom role.
    System roles cannot be deleted.
    Roles assigned to users cannot be deleted.
    Only accessible by platform super admins.
    """
    return rp_service.delete_role(session, role_id)


@router.get("/permissions/all", response_model=list[PermissionGroupPublic], dependencies=[Depends(RequiresPermission("dashboard:admin"))])
def get_all_permissions(
    session: SessionDep,
) -> list[PermissionGroupPublic]:
    """
    Get all available permissions in the system grouped by category.
    """
    return rp_service.get_all_permissions(session)


@router.post("/permissions", response_model=PermissionPublic, status_code=status.HTTP_201_CREATED, dependencies=[Depends(RequiresPermission("dashboard:admin"))])
def create_permission(
    permission_data: PermissionCreate,
    session: SessionDep,
) -> PermissionPublic:
    """
    Create a new system permission.
    """
    return rp_service.create_permission(session, permission_data)
