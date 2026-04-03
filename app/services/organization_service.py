import logging
import uuid
from datetime import datetime, timezone
from typing import Sequence

from fastapi import HTTPException, status
from sqlmodel import Session, select, func, and_

from app.models import (
    User,
    Organization,
    OrganizationMember,
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationPublic,
    OrganizationMemberPublic,
    UserRole,
    Role,
    RolePermission,
    Permission
)
from app.services.email_service import email_service, EmailType
from app.core.config import settings
from app.api.deps import CurrentUser

logger = logging.getLogger(__name__)


def get_organization_by_id(session: Session, organization_id: uuid.UUID) -> Organization:
    org = session.get(Organization, organization_id)
    if not org:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )
    return org

def update_organization(
    session: Session,
    organization: Organization,
    update_data: OrganizationUpdate
) -> Organization:
    """
    Update organization details.
    """
    data = update_data.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(organization, key, value)
    
    organization.updated_at = datetime.now(timezone.utc)
    session.add(organization)
    session.commit()
    session.refresh(organization)
    return organization

def check_organization_access(
    session: Session,
    organization_id: uuid.UUID,
    user: User,
    required_role: list[str] | None = None,
    required_permission: str | None = None
) -> OrganizationMember:
    """
    Check if user is a member of the organization and has the required role/permission.
    Returns the OrganizationMember object.
    """
    from app.utils import permissions as perm_utils

    # Platform super admin always has access
    if user.is_superuser:
        # Check if they are a member anyway to return the object
        member = session.exec(
            select(OrganizationMember).where(
                and_(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.user_id == user.id
                )
            )
        ).first()
        if member:
            return member
        # If superuser is not a member, we might still want to return a dummy or allow access
        # but most logic expects a member object. For now, if superuser, allow if they have perm.
        if required_permission and perm_utils.user_has_permission(session, user, required_permission):
             return None # type: ignore
        return None # type: ignore

    member = session.exec(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user.id
            )
        )
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization"
        )
    
    # 1. Check Permission-based access (Standard)
    if required_permission:
        if not perm_utils.user_has_permission(session, user, required_permission):
            # Format permission for display
            parts = required_permission.split(":")
            perm_display = parts[1].replace("_", " ").title() if len(parts) > 1 else required_permission
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Action Restricted: You do not have the '{perm_display}' permission required to perform this action."
            )

    # 2. Check Role-based access (Legacy/Fallback)
    if required_role:
        if member.role not in required_role:
             raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Required role: {', '.join(required_role)}"
             )

    return member

def list_organization_members(
    session: Session,
    organization_id: uuid.UUID,
    skip: int = 0,
    limit: int = 100,
    search: str | None = None
) -> tuple[list[OrganizationMemberPublic], int]:
    
    query = select(OrganizationMember, User).join(User).where(
        OrganizationMember.organization_id == organization_id
    )

    if search:
        query = query.where(
            (User.full_name.ilike(f"%{search}%")) |
            (User.email.ilike(f"%{search}%"))
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = session.exec(count_query).one()

    # Pagination
    query = query.offset(skip).limit(limit)
    results = session.exec(query).all()

    members_public = []
    for member, user in results:
        # Calculate workspace count
        # This assumes we added the relationship 'workspaces' to User or WorkspaceMember
        # For now, let's count WorkspaceMember entries for this user in workspaces belonging to this org
        # Optimized query would be better, but basic count for now:
        # Actually `member.workspaces_count` is in the public schema but not in DB model directly
        
        # We need to find how many workspaces in THIS organization this user is part of.
        # But Organization <-> Workspace relationship is new.
        
        workspaces_count = 0
        from app.models import WorkspaceMember, Workspace
        ws_count_stmt = select(func.count()).select_from(WorkspaceMember).join(Workspace).where(
            and_(
                Workspace.organization_id == organization_id,
                WorkspaceMember.user_id == user.id
            )
        )
        workspaces_count = session.exec(ws_count_stmt).one()

        # Auto-correct status if user is active but member status is still "invited"
        effective_status = member.status
        if member.status == "invited" and user.is_active:
            effective_status = "active"

        members_public.append(OrganizationMemberPublic(
            id=member.id,
            organization_id=member.organization_id,
            user_id=member.user_id,
            role=member.role,
            joined_at=member.joined_at,
            name=user.full_name or user.email,
            email=user.email,
            avatar=user.avatar,
            workspaces_count=workspaces_count,
            status=effective_status
        ))

    return members_public, total

def invite_member_to_organization(
    session: Session,
    organization_id: uuid.UUID,
    email: str,
    role: str,
    inviter: User,
    note: str | None = None,
    workspace_ids: list[str] | None = None
) -> OrganizationMemberPublic:
    
    # Get organization details
    organization = get_organization_by_id(session, organization_id)
    
    # Check if user exists
    user = session.exec(select(User).where(User.email == email)).first()
    
    is_new_user = False
    if not user:
        # Create "invited" user
        from app.core.security import get_password_hash
        import secrets
        
        temp_password = secrets.token_urlsafe(12)
        user = User(
            email=email,
            hashed_password=get_password_hash(temp_password),
            is_active=False,  # Invited status - not active until they accept
            organization_name=organization.name,
            account_type="organization_member" 
        )
        session.add(user)
        session.flush()  # Get user ID without committing
        is_new_user = True

        # Assign identity role via UserRole (RBAC)
        rbac_role = session.exec(select(Role).where(Role.name == role)).first()
        if rbac_role:
             user_role = UserRole(user_id=user.id, role_id=rbac_role.id)
             session.add(user_role)
    else:
        # If user exists, also ensure their Identity Role reflects this new invitation 
        # (This keeps Identity Role and Org Role in sync for already existing users)
        rbac_role = session.exec(select(Role).where(Role.name == role)).first()
        if rbac_role:
             # Sync UserRole (Identity Role)
             from sqlmodel import delete
             session.exec(delete(UserRole).where(UserRole.user_id == user.id))
             user_role = UserRole(user_id=user.id, role_id=rbac_role.id)
             session.add(user_role)
    
    # Check if already a member
    existing_member = session.exec(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user.id
            )
        )
    ).first()

    if existing_member:
        # If user is already invited/pending, we allow resending the invitation
        if existing_member.status in ["invited", "pending"]:
            # Logic continues to send email below...
            # We might want to update the role if it changed
            if role != existing_member.role:
                existing_member.role = role
                session.add(existing_member)
                session.commit()
                session.refresh(existing_member)
            
            # Use the existing member as 'user' logic is already handled via 'user' variable above
            # Just ensure we don't try to create a new OrganizationMember
            org_member = existing_member
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this organization"
            )

    if not existing_member:
        # Create OrganizationMember
        org_member = OrganizationMember(
            organization_id=organization_id,
            user_id=user.id,
            role=role,
            status="invited"
        )
        session.add(org_member)
        session.commit()
        session.refresh(org_member)

    # ---- Optional: Pre-assign workspaces at invite time ----
    # Creates pending WorkspaceMember entries (keyed by invited_email) so that
    # when the user accepts the org invite, their workspace access activates automatically.
    if workspace_ids:
        from app.models import Workspace, WorkspaceMember as WM
        for ws_id_str in workspace_ids:
            try:
                ws_id = uuid.UUID(ws_id_str)
                workspace = session.get(Workspace, ws_id)
                if not workspace or workspace.organization_id != organization_id:
                    logger.warning(f"Workspace {ws_id_str} not found in org {organization_id}, skipping.")
                    continue

                # Avoid duplicate pending entry
                existing_ws_member = session.exec(
                    select(WM).where(
                        and_(
                            WM.workspace_id == ws_id,
                            WM.invited_email == email
                        )
                    )
                ).first()

                if not existing_ws_member:
                    pending_member = WM(
                        workspace_id=ws_id,
                        user_id=None,  # Not linked until user accepts
                        invited_email=email,
                        status="pending",
                        joined_at=datetime.now(timezone.utc)
                    )
                    session.add(pending_member)
                    logger.info(f"Created pending workspace membership for {email} in workspace {ws_id_str}")
            except Exception as ws_err:
                logger.error(f"Failed to create pending workspace membership for {email} in {ws_id_str}: {ws_err}")

        session.commit()

    # Send Invitation Email
    try:
        # Generate invitation token for new users
        from app.email_utils import generate_team_invitation_token
        invitation_token = generate_team_invitation_token(email=email, organization_id=str(organization_id))
        if is_new_user:
            invitation_link = f"{settings.FRONTEND_HOST}/sign-up?invitation_token={invitation_token}"
        else:
            invitation_link = f"{settings.FRONTEND_HOST}/invitation/accept?token={invitation_token}"
        
        email_service.send_organization_invitation(
            email_to=email,
            inviter_name=inviter.full_name or inviter.email,
            organization_name=organization.name,
            invitation_link=invitation_link,
            custom_message=note
        )
        logger.info(f"Invitation email sent to {email} for organization {organization.name}")
    except Exception as e:
        # Log error but don't fail the invitation
        logger.error(f"Failed to send invitation email to {email}: {str(e)}")

    return OrganizationMemberPublic(
        id=org_member.id,
        organization_id=org_member.organization_id,
        user_id=org_member.user_id,
        role=org_member.role,
        joined_at=org_member.joined_at,
        name=user.full_name or user.email,
        email=user.email,
        avatar=user.avatar,
        workspaces_count=0,
        status=org_member.status
    )

def update_organization_member(
    session: Session,
    organization_id: uuid.UUID,
    member_id: uuid.UUID,
    role: str | None = None
) -> OrganizationMemberPublic:
    
    member = session.get(OrganizationMember, member_id)
    if not member or member.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Member not found")
    
    user = session.get(User, member.user_id)

    if role:
        member.role = role
        # Sync with UserRole (Identity Role) logic if strictly 1-to-1 per Org
        # The prompt says: "One user has one identity role per organization"
        # So we should update the UserRole to match this new Org Role
        
        # NOTE: This assumes User only belongs to ONE organization (Tenant model).
        # If User can belong to multiple Orgs, 'Identity Role' is ambiguous unless scoped to Org-Context.
        # Given "account_type=organization" in User model, it seems simplistic tenant model.
        
        rbac_role = session.exec(select(Role).where(Role.name == role)).first()
        if rbac_role:
            # Remove old roles
            session.exec(select(UserRole).where(UserRole.user_id == user.id))
            # Actually easier to delete all and add new
            from sqlmodel import delete
            session.exec(delete(UserRole).where(UserRole.user_id == user.id))
            
            new_ur = UserRole(user_id=user.id, role_id=rbac_role.id)
            session.add(new_ur)

    session.add(member)
    session.commit()
    session.refresh(member)
    
    return OrganizationMemberPublic(
        id=member.id,
        organization_id=member.organization_id,
        user_id=member.user_id,
        role=member.role,
        joined_at=member.joined_at,
        name=user.full_name,
        email=user.email,
        avatar=user.avatar,
        workspaces_count=0, # access proper count
        status=member.status
    )

def remove_organization_member(
    session: Session,
    organization_id: uuid.UUID,
    member_id: uuid.UUID
):
    member = session.get(OrganizationMember, member_id)
    if not member or member.organization_id != organization_id:
        raise HTTPException(status_code=404, detail="Member not found")
    
    # Prevent removal of Super Admin users
    if member.role == "org_super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Super Admin users cannot be removed from the organization"
        )

    # Check if user owns any workspaces in this organization
    from app.models import Workspace
    owned_workspaces = session.exec(
        select(Workspace).where(
            and_(
                Workspace.organization_id == organization_id,
                Workspace.owner_id == member.user_id
            )
        )
    ).all()

    if owned_workspaces:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot remove user: They own {len(owned_workspaces)} workspace(s). Please transfer ownership or delete workspaces first."
        )
    
    # Logic: "Automatically removes them from all workspaces"
    # WorkspaceMember has cascade_delete=True on User? No, check models.
    # WorkspaceMember.user_id is foreign key.
    
    # We should manually remove them from workspaces belonging to this org
    from app.models import WorkspaceMember, Workspace
    
    # Find all workspace memberships for this user in this org
    stm = select(WorkspaceMember).join(Workspace).where(
        and_(
            Workspace.organization_id == organization_id,
            WorkspaceMember.user_id == member.user_id
        )
    )
    ws_members = session.exec(stm).all()
    
    for wsm in ws_members:
        session.delete(wsm)
        
    session.delete(member)
    session.commit()

def verify_organization_invitation(
    session: Session,
    token: str
) -> dict:
    """
    Verify an organization invitation token and return organization details.
    Does not accept the invitation. Publicly accessible.
    """
    from app.email_utils import verify_organization_invitation_token
    from app.models import Organization
    
    token_data = verify_organization_invitation_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token"
        )

    organization_id = uuid.UUID(token_data["organization_id"])
    organization = session.get(Organization, organization_id)
    
    if not organization:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization not found"
        )

    return {
        "organization_id": str(organization.id),
        "organization_name": organization.name,
        "email": token_data["email"],
        "type": "organization_invitation"
    }

def accept_organization_invitation(
    session: Session,
    token: str,
    current_user: User
) -> OrganizationMemberPublic:
    """
    Accept an organization invitation using the invitation token.
    Requires the user to be logged in.
    """
    from app.email_utils import verify_organization_invitation_token
    from app.models import OrganizationMember, WorkspaceMember, Workspace
    from datetime import datetime, timezone

    # Verify the invitation token
    token_data = verify_organization_invitation_token(token)
    if not token_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired invitation token"
        )

    invited_email = token_data["email"]
    organization_id = uuid.UUID(token_data["organization_id"])

    # Verify the current user's email matches the invitation
    if current_user.email != invited_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This invitation was sent to a different email address"
        )

    # Find the pending membership
    member = session.exec(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == current_user.id
            )
        )
    ).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Organization membership not found"
        )

    # Activate user if they were invited
    if not current_user.is_active:
        current_user.is_active = True
        session.add(current_user)

    member.joined_at = datetime.now(timezone.utc)
    member.status = "active"

    session.add(member)
    session.flush()

    # Activate any pending workspace memberships that were pre-assigned at invite time
    # Only activate workspaces belonging to THIS organization
    from app.models import WorkspaceMember as WM, Workspace
    from sqlmodel import col
    pending_ws_members = session.exec(
        select(WM).join(Workspace).where(
            and_(
                WM.invited_email == current_user.email,
                WM.status == "pending",
                col(WM.user_id).is_(None),
                Workspace.organization_id == organization_id
            )
        )
    ).all()

    for ws_member in pending_ws_members:
        ws_member.user_id = current_user.id
        ws_member.status = "active"
        ws_member.joined_at = datetime.now(timezone.utc)
        session.add(ws_member)
        logger.info(f"Activated pending workspace membership for user {current_user.id} in workspace {ws_member.workspace_id}")

    session.commit()
    session.refresh(member)
    session.refresh(current_user)

    logger.info(f"User {current_user.id} accepted invitation to organization {organization_id}. Status changed to active. Activated {len(pending_ws_members)} pending workspace memberships.")

    return OrganizationMemberPublic(
        id=member.id,
        organization_id=member.organization_id,
        user_id=member.user_id,
        role=member.role,
        joined_at=member.joined_at,
        name=current_user.full_name or current_user.email,
        email=current_user.email,
        avatar=current_user.avatar,
        workspaces_count=0,
        status=member.status  # Use the actual updated status from the DB object
    )


def list_organization_roles(
    session: Session,
    organization_id: uuid.UUID
) -> list[dict]: # Returns simplified dict compatible with frontend for now
    """List all available roles (system + custom) for an organization"""
    from app.services.roles_permissions_service import get_permission_category
    
    # 1. Fetch System Roles (global)
    # Using org_ prefix or specific roles relevant to orgs
    system_roles = session.exec(
        select(Role).where(
            (Role.organization_id == None) &
            ((Role.name.startswith("org_")) | (Role.name == "member"))
        )
    ).all()
    
    # 2. Fetch Custom Roles (org-specific)
    custom_roles = session.exec(
        select(Role).where(Role.organization_id == organization_id)
    ).all()
    
    all_roles = system_roles + custom_roles
    
    result = []
    
    for role in all_roles:
        # Calculate user count
        # Currently mapping by name string in OrganizationMember
        user_count = session.exec(
            select(func.count(OrganizationMember.id)).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == role.name
            )
        ).one()
        
        # Get permissions
        # Join RolePermission and Permission
        role_permissions = session.exec(
            select(Permission).join(RolePermission).where(
                RolePermission.role_id == role.id,
                RolePermission.allowed == True
            )
        ).all()
        
        perm_names = [p.name for p in role_permissions]
        
        # For compatibility with frontend which expects 'permissions' as array of strings or grouped objects
        # The frontend interface OrganizationRole has permissions: string[]
        # But RoleModal might expect grouped permissions.
        # Let's verify what frontend expects. 
        # OrganizationRole interface: permissions: string[]
        
        result.append({
            "id": str(role.id),
            "name": role.name,
            "description": role.description,
            "isSystem": role.organization_id is None,
            "permissions": perm_names,
            "userCount": user_count
        })
        
    return result


def create_organization_role(
    session: Session,
    organization_id: uuid.UUID,
    name: str,
    description: str | None = None,
    permissions: list[str] | None = None
) -> Role:
    """Create a new custom role for an organization"""
    from app.services.roles_permissions_service import SYSTEM_ROLES
    
    # Check if role name exists in this organization
    existing = session.exec(
        select(Role).where(
            Role.organization_id == organization_id,
            Role.name == name
        )
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role with this name already exists in the organization"
        )
    
    if name in SYSTEM_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot use system role names"
        )
    
    role = Role(
        name=name,
        description=description,
        organization_id=organization_id
    )
    session.add(role)
    session.commit()
    session.refresh(role)
    
    # Assign permissions
    if permissions:
        # Find permissions by name
        perms = session.exec(select(Permission).where(Permission.name.in_(permissions))).all()
        for perm in perms:
            role_perm = RolePermission(
                role_id=role.id,
                permission_id=perm.id,
                allowed=True
            )
            session.add(role_perm)
        session.commit()
        
    return role


def update_organization_role(
    session: Session,
    organization_id: uuid.UUID,
    role_id: uuid.UUID,
    name: str | None = None,
    description: str | None = None,
    permissions: list[str] | None = None
) -> Role:
    """Update a custom role for an organization"""
    role = session.get(Role, role_id)
    # Allow if the role belongs to the organization OR if it's a system role (org_id is None)
    if not role or (role.organization_id is not None and role.organization_id != organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    if name and name != role.name:
        from app.services.roles_permissions_service import SYSTEM_ROLES
        if role.name in SYSTEM_ROLES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot rename system roles"
            )
            
        existing = session.exec(
            select(Role).where(
                Role.organization_id == organization_id,
                Role.name == name
            )
        ).first()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Role with this name already exists in the organization"
            )
        role.name = name
    
    if description is not None:
        role.description = description
        
    session.add(role)
    session.commit()
    
    if permissions is not None:
        # Remove old permissions
        # Delete using SQLModel delete statement
        from sqlmodel import delete
        session.exec(
            delete(RolePermission).where(RolePermission.role_id == role.id)
        )
        session.flush()
        
        # Add new permissions
        # Robust matching: Try exact match first
        perms = session.exec(select(Permission).where(Permission.name.in_(permissions))).all()
        
        # If we didn't find all permissions, maybe case sensitivity issue?
        if len(perms) < len(permissions):
            found_names = {p.name for p in perms}
            missing_names = [p for p in permissions if p not in found_names]
            if missing_names:
                print(f"Warning: Could not find permissions: {missing_names}")
                # Try case-insensitive fallback for missing ones
                for m_name in missing_names:
                     fallback = session.exec(select(Permission).where(Permission.name == m_name.lower())).first()
                     if fallback:
                         perms.append(fallback)

        # Deduplicate perms list
        perms = list({p.id: p for p in perms}.values())

        for perm in perms:
            role_perm = RolePermission(
                role_id=role.id,
                permission_id=perm.id,
                allowed=True
            )
            session.add(role_perm)
        session.commit()

    session.refresh(role)
    return role


def delete_organization_role(
    session: Session,
    organization_id: uuid.UUID,
    role_id: uuid.UUID
) -> dict:
    """Delete a custom role from an organization"""
    role = session.get(Role, role_id)
    # Allow if the role belongs to the organization OR if it's a system role (org_id is None)
    if not role or (role.organization_id is not None and role.organization_id != organization_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Block deletion of system roles
    from app.services.roles_permissions_service import SYSTEM_ROLES
    if role.name in SYSTEM_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system roles"
        )
    
    # Check if assigned to any members
    # OrganizationMember has `role` as string currently, so we check by name
    # Ideally Role ID should be foreign key in OrganizationMember but it's string now.
    user_count = session.exec(
        select(func.count(OrganizationMember.id)).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.role == role.name
        )
    ).one()
    
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role. It is assigned to {user_count} member(s)."
        )
        
    session.delete(role)
    session.commit()
    
    return {"success": True, "message": "Role deleted successfully"}
