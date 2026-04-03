import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, SQLModel

from app.api.deps import SessionDep, CurrentUser, RequiresPermission
from app.models import (
    OrganizationMemberPublic,
    OrganizationTeamListResponse,
    Role,
    OrganizationUpdate
)
from app.services import organization_service

import logging
router = APIRouter(prefix="/organizations", tags=["organizations"])
logger = logging.getLogger(__name__)

@router.get("/me")
def get_my_organization(
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get the current user's organization.
    Returns the first organization the user is a member of.
    """
    from app.models import OrganizationMember, Organization
    
    # Get user's organization membership
    stmt = select(OrganizationMember).where(
        OrganizationMember.user_id == current_user.id
    )
    logger.info(f"Checking org membership for user {current_user.id}")
    org_member = session.exec(stmt).first()
    
    if not org_member:
        # Before failing, check if this is a platform admin
        from app.models import Role, UserRole
        platform_roles = session.exec(
            select(Role).where(Role.name.in_(["platform_super_admin", "platform_admin"]))
        ).all()
        platform_role_ids = [r.id for r in platform_roles]
        
        if platform_role_ids:
            user_platform_role = session.exec(
                select(UserRole).where(
                    UserRole.user_id == current_user.id,
                    UserRole.role_id.in_(platform_role_ids)
                )
            ).first()
            
            if user_platform_role:
                # Get the actual role name
                role_obj = next(r for r in platform_roles if r.id == user_platform_role.role_id)
                return {
                    "id": None,
                    "name": "Platform HQ",
                    "description": "System Context",
                    "isActive": True,
                    "createdAt": current_user.created_at.isoformat(),
                    "updatedAt": current_user.created_at.isoformat(),
                    "ownerId": str(current_user.id),
                    "userRole": role_obj.name
                }

        logger.warning(f"User {current_user.id} is not a member of any organization")
        raise HTTPException(status_code=404, detail="User is not a member of any organization")
    
    # Get the organization
    organization = session.get(Organization, org_member.organization_id)
    
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    return {
        "id": str(organization.id),
        "name": organization.name,
        "description": organization.description,
        "isActive": organization.is_active,
        "createdAt": organization.created_at.isoformat(),
        "updatedAt": organization.updated_at.isoformat(),
        "ownerId": str(organization.owner_id),
        "userRole": org_member.role
    }


@router.patch("/me")
def update_my_organization(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    org_in: OrganizationUpdate,
) -> Any:
    """
    Update the current user's organization.
    """
    from app.models import OrganizationMember, Organization
    
    # Get user's organization membership
    stmt = select(OrganizationMember).where(
        OrganizationMember.user_id == current_user.id
    )
    org_member = session.exec(stmt).first()
    
    if not org_member:
        raise HTTPException(status_code=404, detail="User is not a member of any organization")
    
    # Check permissions (only org_super_admin or org_admin can update)
    if org_member.role not in ["org_super_admin", "org_admin"]:
        raise HTTPException(status_code=403, detail="Not enough permissions to update organization")

    # Get the organization
    organization = session.get(Organization, org_member.organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    updated_org = organization_service.update_organization(
        session=session,
        organization=organization,
        update_data=org_in
    )
    
    return {
        "id": str(updated_org.id),
        "name": updated_org.name,
        "description": updated_org.description,
        "isActive": updated_org.is_active,
        "createdAt": updated_org.created_at.isoformat(),
        "updatedAt": updated_org.updated_at.isoformat(),
        "ownerId": str(updated_org.owner_id),
        "userRole": org_member.role
    }


@router.get("/{org_id}/team", response_model=OrganizationTeamListResponse)
def list_organization_members_route(
    org_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 100,
    search: str | None = None,
) -> Any:
    """
    List all members of an organization.
    Requires 'user:manage' or 'team:view' permission (or just be a member).
    """
    # Verify access
    organization_service.check_organization_access(session, org_id, current_user)
    
    members, total = organization_service.list_organization_members(
        session=session,
        organization_id=org_id,
        skip=(page - 1) * page_size,
        limit=page_size,
        search=search
    )
    
    return OrganizationTeamListResponse(list=members, total=total)

@router.post("/{org_id}/team/invite", response_model=OrganizationMemberPublic)
def invite_organization_member(
    org_id: uuid.UUID,
    invite_data: dict, # {email: str, role: str}
    session: SessionDep,
    current_user: CurrentUser,
    # permission check: requires org management
) -> Any:
    """
    Invite a user to the organization.
    """
    # Check permission explicitly for management
    organization_service.check_organization_access(
        session, 
        org_id, 
        current_user, 
        required_permission="team:manage" 
    )

    email = invite_data.get("email")
    role = invite_data.get("role", "org_member")
    note = invite_data.get("note")
    workspace_ids = invite_data.get("workspace_ids")  # Optional list of workspace UUIDs
    
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    return organization_service.invite_member_to_organization(
        session=session,
        organization_id=org_id,
        email=email,
        role=role,
        inviter=current_user,
        note=note,
        workspace_ids=workspace_ids
    )

@router.put("/{org_id}/team/{member_id}", response_model=OrganizationMemberPublic)
def update_organization_member_role(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    update_data: dict, # {role: str}
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Update a member's identity role.
    """
    organization_service.check_organization_access(
        session, 
        org_id, 
        current_user, 
        required_permission="team:manage"
    )
    
    role = update_data.get("role")
    
    return organization_service.update_organization_member(
        session=session,
        organization_id=org_id,
        member_id=member_id,
        role=role
    )

@router.delete("/{org_id}/team/{member_id}")
def remove_organization_member_route(
    org_id: uuid.UUID,
    member_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Remove a member from the organization.
    """
    organization_service.check_organization_access(
        session, 
        org_id, 
        current_user, 
        required_permission="team:manage"
    )
    
    organization_service.remove_organization_member(
        session=session,
        organization_id=org_id,
        member_id=member_id
    )
    
    return {"success": True, "message": "Member removed from organization"}

from app.schemas.roles_permissions import RoleCreate, RoleUpdate, RolePublic, OrganizationRoleCreate, OrganizationRoleUpdate, OrganizationRolePublic

# ... (omitted imports)

@router.get("/{org_id}/roles")
def list_organization_roles(
    org_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    List available identity roles for organizations.
    """
    organization_service.check_organization_access(session, org_id, current_user)
    
    roles = organization_service.list_organization_roles(session, org_id)
    
    return {
        "roles": roles
    }


@router.post("/{org_id}/roles", response_model=OrganizationRolePublic)
def create_organization_role(
    org_id: uuid.UUID,
    role_data: OrganizationRoleCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Create a new custom role for the organization.
    """
    organization_service.check_organization_access(
        session, 
        org_id, 
        current_user, 
        required_permission="organization:manage"
    )
    
    role = organization_service.create_organization_role(
        session=session,
        organization_id=org_id,
        name=role_data.name,
        description=role_data.description,
        permissions=role_data.permissions
    )
    
    # Reload role to get relationships
    session.refresh(role)
    
    # Get simplified permissions list
    perm_names = []
    if role.role_permissions:
        for rp in role.role_permissions:
             if rp.permission:
                 perm_names.append(rp.permission.name)
             else:
                 pass 
                 
    # Double check permissions if not loaded via relationship
    if not perm_names and role.role_permissions:
         from app.models import Permission, RolePermission
         perm_ids = [rp.permission_id for rp in role.role_permissions]
         perms = session.exec(select(Permission).where(Permission.id.in_(perm_ids))).all()
         perm_names = [p.name for p in perms]
    
    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "userCount": 0,
        "permissions": perm_names,
        "isSystem": role.organization_id is None
    }


@router.put("/{org_id}/roles/{role_id}", response_model=OrganizationRolePublic)
def update_organization_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    role_data: OrganizationRoleUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Update a custom organization role.
    """
    organization_service.check_organization_access(
        session, 
        org_id, 
        current_user, 
        required_permission="organization:manage"
    )
    
    role = organization_service.update_organization_role(
        session=session,
        organization_id=org_id,
        role_id=role_id,
        name=role_data.name,
        description=role_data.description,
        permissions=role_data.permissions
    )
    
    # Calculate user count
    # Ideally should be in service but doing here for response construction
    from app.models import OrganizationMember
    from sqlmodel import func, select 
    
    user_count = session.exec(
        select(func.count(OrganizationMember.id)).where(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.role == role.name
        )
    ).one()
    
    # Refresh role and its relationships to be sure
    session.refresh(role)
    
    # Get permissions directly from the updated RolePermission table
    from app.models import Permission, RolePermission
    perms = session.exec(
        select(Permission).join(RolePermission, Permission.id == RolePermission.permission_id).where(
            RolePermission.role_id == role.id,
            RolePermission.allowed == True
        )
    ).all()
    perm_names = [p.name for p in perms]

    return {
        "id": role.id,
        "name": role.name,
        "description": role.description,
        "userCount": user_count,
        "permissions": perm_names,
        "isSystem": role.organization_id is None
    }


@router.delete("/{org_id}/roles/{role_id}")
def delete_organization_role(
    org_id: uuid.UUID,
    role_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Delete a custom organization role.
    """
    organization_service.check_organization_access(
        session, 
        org_id, 
        current_user, 
        required_permission="organization:manage"
    )
    
    return organization_service.delete_organization_role(
        session=session,
        organization_id=org_id,
        role_id=role_id
    )

class AcceptOrgInvitationRequest(SQLModel):
    token: str

@router.get("/invitation/verify")
def verify_organization_invitation_route(
    token: str,
    session: SessionDep,
) -> Any:
    """
    Verify an organization invitation token.
    Public endpoint to show invitation details before accepting.
    """
    return organization_service.verify_organization_invitation(
        session=session,
        token=token
    )

@router.post("/invitation/accept", response_model=OrganizationMemberPublic)
def accept_organization_invitation_route(
    request: AcceptOrgInvitationRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Accept an organization invitation using a token.
    Requires authentication.
    """
    return organization_service.accept_organization_invitation(
        session=session,
        token=request.token,
        current_user=current_user
    )
