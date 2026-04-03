"""
Workspace Service Layer

Contains business logic for workspace management, members, projects, and credit allocation.
Enforces RBAC and authorization rules.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Tuple, List

from fastapi import HTTPException, status
from sqlmodel import Session, select, func, col, and_, or_, delete
from pydantic import EmailStr
from app.utils.permissions import user_has_any_permission
from app.core.config import settings

from app.services.email_service import EmailService, EmailType
from app.notification_repository import create_notification

from app.models import (
    User,
    OrganizationMember,
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspacePublic,
    WorkspaceMember,
    WorkspaceMemberPublic,
    WorkspaceRole,
    WorkspaceRoleCreate,
    WorkspaceRoleUpdate,
    WorkspaceRolePublic,
    WorkspaceMemberRole,
    WorkspaceProject,
    WorkspaceProjectCreate,
    WorkspaceProjectUpdate,
    WorkspaceProjectPublic,
    WorkspaceProjectMember,
    WorkspaceCreditTransaction,
    CreditTransactionPublic,
    AddMemberRequest,
    AllocateCreditsRequest,
    TopUpCreditsRequest,
    WorkspaceDashboardStats,
    MemberUsage,
    ProjectUsage,
    UsageTrend,
    WorkspaceUsageReport,
    RolePermissions,
)

logger = logging.getLogger(__name__)


# ==================== Authorization Helpers ====================

def check_workspace_access(
    *,
    session: Session,
    workspace: Workspace,
    user: User,
    require_owner: bool = False
) -> None:
    """
    Check if user has access to a workspace.

    Rules:
    - User must be the owner, OR
    - User must be a member of the workspace

    Args:
        session: Database session
        workspace: Workspace to check
        user: Current user
        require_owner: If True, only the owner can access

    Raises:
        HTTPException: If user doesn't have access
    """
    # Check if user is the owner
    if workspace.owner_id == user.id:
        return

    # Allow access if user is platform admin with manage/view_all permission
    if user_has_any_permission(session, user, ["organization:manage", "organization:view_all"]):
        return

    # Allow access if user is organization admin of the parent organization
    if workspace.organization_id:
        # Check if user is org_super_admin via OrganizationMember
        org_member = session.exec(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == workspace.organization_id,
                OrganizationMember.user_id == user.id
            )
        ).first()

        if org_member and org_member.role in ["org_super_admin", "org_admin"]:
            return

        if user_has_any_permission(session, user, ["team:manage"]):
             return

    if require_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Action Restricted: Only the workspace owner or organization administrator can perform this action."
        )

    # Check if user is a member
    stmt = select(WorkspaceMember).where(
        and_(
            WorkspaceMember.workspace_id == workspace.id,
            WorkspaceMember.user_id == user.id,
            WorkspaceMember.status == "active"
        )
    )
    member = session.exec(stmt).first()

    if member:
        return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to access this workspace"
    )


def get_workspace_by_id(
    *,
    session: Session,
    workspace_id: uuid.UUID
) -> Workspace:
    """
    Get workspace by ID.

    Raises:
        HTTPException: If workspace not found
    """
    workspace = session.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )
    return workspace


# ==================== Workspace CRUD ====================


def create_default_workspace_roles(session: Session, workspace_id: uuid.UUID) -> list[WorkspaceRole]:
    """Create default roles for a new workspace"""
    default_roles_data = [
        {
            "name": "Admin",
            "description": "Full access to all workspace features",
            "permissions": {
                "access_ai_credits": True,
                "manage_workspaces": True,
                "create_projects": True,
                "manage_billing": True,
                "manage_integrations": True,
                "invite_members": True,
                "manage_roles": True,
                "view_reports": True,
                "manage_members": True,
                "delete_workspace": True,
            }
        },
        {
            "name": "Member",
            "description": "Access to projects and AI features",
            "permissions": {
                "access_ai_credits": True,
                "manage_workspaces": False,
                "create_projects": True,
                "manage_billing": False,
                "manage_integrations": False,
                "invite_members": False,
                "manage_roles": False,
                "view_reports": True,
                "manage_members": False,
                "delete_workspace": False,
            }
        },
        {
            "name": "Viewer",
            "description": "Read-only access to projects and reports",
            "permissions": {
                "access_ai_credits": False,
                "manage_workspaces": False,
                "create_projects": False,
                "manage_billing": False,
                "manage_integrations": False,
                "invite_members": False,
                "manage_roles": False,
                "view_reports": True,
                "manage_members": False,
                "delete_workspace": False,
            }
        }
    ]

    roles = []
    for rd in default_roles_data:
        role = WorkspaceRole(
            workspace_id=workspace_id,
            name=rd["name"],
            description=rd["description"],
            is_custom=False,
            permissions=rd["permissions"]
        )
        session.add(role)
        roles.append(role)
    
    return roles


def create_workspace(
    *,
    session: Session,
    workspace_in: WorkspaceCreate,
    user: User
) -> WorkspacePublic:
    """
    Create a new workspace.

    Args:
        session: Database session
        workspace_in: Workspace creation data
        user: Current user (will be owner)

    Returns:
        Created workspace
    """
    # Find user's organization if they have one
    from app.models import OrganizationMember, WorkspaceMember
    org_member = session.exec(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    ).first()
    
    organization_id = org_member.organization_id if org_member else None
    
    # Restrict workspace creation to authorized users
    from app.utils import permissions as perm_utils
    has_org_manage = perm_utils.user_has_permission(session, user, "organization:manage")
    has_org_create = perm_utils.user_has_permission(session, user, "organization:create")
    
    if org_member and not (has_org_manage or has_org_create):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You do not have permission to create new workspaces within this organization"
        )

    # Create workspace
    workspace = Workspace(
        name=workspace_in.name,
        description=workspace_in.description,
        owner_id=user.id,
        organization_id=organization_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    session.add(workspace)
    session.flush() # Get workspace ID
    
    # Seed default roles
    roles = create_default_workspace_roles(session, workspace.id)
    session.flush() # Ensure roles get IDs

    # Add owner as the first member of the workspace
    owner_member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=user.id,
        status="active",
        joined_at=datetime.now(timezone.utc)
    )
    session.add(owner_member)
    session.flush() # Ensure owner_member gets ID

    # Assign Admin role to owner
    admin_role = next((r for r in roles if r.name == "Admin"), None)
    if admin_role:
        owner_role = WorkspaceMemberRole(
            member_id=owner_member.id,
            role_id=admin_role.id
        )
        session.add(owner_role)
    
    session.commit()
    session.refresh(workspace)

    logger.info(f"Workspace created: {workspace.id} by user {user.id}")

    # Convert to WorkspacePublic with computed fields
    return WorkspacePublic(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description,
        avatar=workspace.avatar,
        owner_id=workspace.owner_id,
        organization_id=workspace.organization_id,
        credits_balance=workspace.credits_balance,
        status=workspace.status,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        total_members=1,  # Owner is now a member
        total_projects=0  # New workspace has no projects yet
    )


def list_workspaces(
    *,
    session: Session,
    user: User,
    page: int = 1,
    page_size: int = 20
) -> Tuple[list[WorkspacePublic], int]:
    """
    List all workspaces for the current user (owned or member of).

    Args:
        session: Database session
        user: Current user
        page: Page number
        page_size: Items per page

    Returns:
        Tuple of (list of workspaces, total count)
    """
    # Find user's organization and role
    from app.models import OrganizationMember, Organization
    org_member = session.exec(
        select(OrganizationMember).where(OrganizationMember.user_id == user.id)
    ).first()

    # Base conditions: owner or member
    conditions = [
        Workspace.owner_id == user.id,
        Workspace.id.in_(
            select(WorkspaceMember.workspace_id).where(
                and_(
                    WorkspaceMember.user_id == user.id,
                    WorkspaceMember.status.in_(["active", "pending"])
                )
            )
        )
    ]

    # Add organization-wide access for privileged organization roles
    # Only org_super_admin and org_admin should see all workspaces by default
    if org_member and org_member.role in ["org_super_admin", "org_admin"]:
        conditions.append(Workspace.organization_id == org_member.organization_id)

    base_stmt = select(Workspace).where(or_(*conditions))
    
    # Get total count
    total = session.exec(select(func.count()).select_from(base_stmt.subquery())).one()
    
    # Get paginated data
    stmt = base_stmt.order_by(Workspace.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    workspaces = session.exec(stmt).all()

    # Build response with counts
    result = []
    for workspace in workspaces:
        members_count = session.exec(
            select(func.count()).select_from(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace.id
            )
        ).one()
        
        # Ensure at least 1 member (the owner) is counted
        if members_count == 0:
            members_count = 1

        projects_count = session.exec(
            select(func.count()).select_from(WorkspaceProject).where(
                WorkspaceProject.workspace_id == workspace.id
            )
        ).one()

        # Fetch organization name
        organization_name = None
        if workspace.organization_id:
            org = session.get(Organization, workspace.organization_id)
            if org:
                organization_name = org.name

        # Create WorkspacePublic explicitly to ensure counts are included correctly
        workspace_public = WorkspacePublic(
            id=workspace.id,
            name=workspace.name,
            description=workspace.description or "",
            avatar=workspace.avatar,
            owner_id=workspace.owner_id,
            organization_id=workspace.organization_id,
            credits_balance=workspace.credits_balance,
            status=workspace.status,
            created_at=workspace.created_at,
            updated_at=workspace.updated_at,
            total_members=members_count,
            total_projects=projects_count,
            organization_name=organization_name
        )
        result.append(workspace_public)

    return result, total


def count_all_workspaces(*, session: Session) -> int:
    """
    Count all workspaces in the system.

    Args:
        session: Database session

    Returns:
        Total number of workspaces
    """
    count = session.exec(select(func.count()).select_from(Workspace)).one()
    return count


def get_workspace(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User
) -> WorkspacePublic:
    """
    Get workspace by ID.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user

    Returns:
        Workspace details
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    members_count = session.exec(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id
        )
    ).one()
    
    # Ensure at least 1 member (the owner) is counted
    if members_count == 0:
        members_count = 1

    projects_count = session.exec(
        select(func.count()).select_from(WorkspaceProject).where(
            WorkspaceProject.workspace_id == workspace.id
        )
    ).one()

    # Create WorkspacePublic explicitly to ensure counts are included correctly
    workspace_public = WorkspacePublic(
        id=workspace.id,
        name=workspace.name,
        description=workspace.description or "",
        avatar=workspace.avatar,
        owner_id=workspace.owner_id,
        organization_id=workspace.organization_id,
        credits_balance=workspace.credits_balance,
        status=workspace.status,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        total_members=members_count,
        total_projects=projects_count
    )

    return workspace_public


def update_workspace(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    workspace_in: WorkspaceUpdate,
    user: User
) -> WorkspacePublic:
    """
    Update workspace.

    Args:
        session: Database session
        workspace_id: Workspace ID
        workspace_in: Update data
        user: Current user

    Returns:
        Updated workspace
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user, require_owner=True)

    # Update fields
    if workspace_in.name is not None:
        workspace.name = workspace_in.name
    if workspace_in.description is not None:
        workspace.description = workspace_in.description
    if workspace_in.avatar is not None:
        workspace.avatar = workspace_in.avatar
    if workspace_in.status is not None:
        workspace.status = workspace_in.status

    workspace.updated_at = datetime.now(timezone.utc)

    session.add(workspace)
    session.commit()
    session.refresh(workspace)

    logger.info(f"Workspace updated: {workspace.id}")

    # Get counts for computed fields
    members_count = session.exec(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace.id
        )
    ).one()

    projects_count = session.exec(
        select(func.count()).select_from(WorkspaceProject).where(
            WorkspaceProject.workspace_id == workspace.id
        )
    ).one()

    # Convert to WorkspacePublic
    workspace_public = WorkspacePublic.model_validate(workspace)
    workspace_public.total_members = members_count
    workspace_public.total_projects = projects_count

    return workspace_public


def delete_workspace(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User
) -> None:
    """
    Delete workspace.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user, require_owner=True)

    session.delete(workspace)
    session.commit()

    logger.info(f"Workspace deleted: {workspace_id}")


# ==================== Dashboard Stats ====================

def get_dashboard_stats(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User,
    filter_by_user: bool = False
) -> WorkspaceDashboardStats:
    """
    Get workspace dashboard statistics.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user
        filter_by_user: Whether to filter stats for the current user only

    Returns:
        Dashboard statistics
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    # Get user's member ID if filtering
    member_id = None
    if filter_by_user:
        member = session.exec(
            select(WorkspaceMember).where(
                and_(
                    WorkspaceMember.workspace_id == workspace_id,
                    WorkspaceMember.user_id == user.id
                )
            )
        ).first()
        if member:
            member_id = member.id

    # Total members
    total_members = session.exec(
        select(func.count()).select_from(WorkspaceMember).where(
            WorkspaceMember.workspace_id == workspace_id
        )
    ).one()

    # Total projects
    project_query = select(func.count()).select_from(WorkspaceProject).where(
        WorkspaceProject.workspace_id == workspace_id
    )
    if filter_by_user:
        project_query = project_query.where(WorkspaceProject.created_by == user.id)
    
    total_projects = session.exec(project_query).one()

    # Base transaction filters
    base_tx_filter = and_(
        WorkspaceCreditTransaction.workspace_id == workspace_id,
        WorkspaceCreditTransaction.type == "usage"
    )
    if filter_by_user and member_id:
        base_tx_filter = and_(base_tx_filter, WorkspaceCreditTransaction.recipient_id == member_id)

    # Total API calls (count of usage transactions)
    total_api_calls = session.exec(
        select(func.count()).select_from(WorkspaceCreditTransaction).where(base_tx_filter)
    ).one() or 0

    # Credits & Tokens used today
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    today_stats = session.exec(
        select(
            func.sum(WorkspaceCreditTransaction.amount),
            func.sum(WorkspaceCreditTransaction.tokens)
        ).where(
            and_(
                base_tx_filter,
                WorkspaceCreditTransaction.created_at >= today_start
            )
        )
    ).first()
    credits_used_today = today_stats[0] or Decimal("0.0000")
    tokens_used_today = today_stats[1] or 0

    # Credits & Tokens used this month
    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_stats = session.exec(
        select(
            func.sum(WorkspaceCreditTransaction.amount),
            func.sum(WorkspaceCreditTransaction.tokens)
        ).where(
            and_(
                base_tx_filter,
                WorkspaceCreditTransaction.created_at >= month_start
            )
        )
    ).first()
    credits_used_this_month = month_stats[0] or Decimal("0.0000")
    tokens_used_this_month = month_stats[1] or 0

    # Credit burn rate (average per day this month)
    days_in_month = (datetime.now(timezone.utc) - month_start).days + 1
    credit_burn_rate = credits_used_this_month / Decimal(days_in_month) if days_in_month > 0 else Decimal("0.0000")

    # Active integrations (placeholder - implement when integrations are added)
    active_integrations = 0

    # Success rate (placeholder - calculate from API calls)
    success_rate = Decimal("98.5")

    # Daily usage for the last 12 days
    daily_usage = []
    end_date = datetime.now(timezone.utc)
    for i in range(12):
        d_start = end_date - timedelta(days=11-i)
        d_start = d_start.replace(hour=0, minute=0, second=0, microsecond=0)
        d_end = d_start + timedelta(days=1)
        
        daily_stats_stmt = select(
            func.coalesce(func.sum(WorkspaceCreditTransaction.tokens), 0).label("tokens"),
            func.count(WorkspaceCreditTransaction.id).label("requests")
        ).where(
            and_(
                base_tx_filter,
                WorkspaceCreditTransaction.created_at >= d_start,
                WorkspaceCreditTransaction.created_at < d_end
            )
        )
        stats = session.exec(daily_stats_stmt).first()
        tokens = int(stats.tokens) if stats else 0
        requests = int(stats.requests) if stats else 0
        daily_usage.append({
            "date": d_start.strftime("%Y-%m-%d"),
            "tokens": tokens,
            "requests": requests
        })

    # Recent requests
    recent_txs = session.exec(
        select(WorkspaceCreditTransaction)
        .where(base_tx_filter)
        .order_by(WorkspaceCreditTransaction.created_at.desc())
        .limit(5)
    ).all()
    recent_requests = [
        {
            "id": str(tx.id),
            "description": tx.description,
            "tokens": tx.tokens,
            "amount": float(tx.amount),
            "created_at": tx.created_at.isoformat()
        } for tx in recent_txs
    ]

    return WorkspaceDashboardStats(
        credits_balance=workspace.credits_balance,
        total_members=total_members,
        total_projects=total_projects,
        total_api_calls=total_api_calls,
        credits_used_today=credits_used_today,
        credits_used_this_month=credits_used_this_month,
        tokens_used_today=tokens_used_today,
        tokens_used_this_month=tokens_used_this_month,
        credit_burn_rate=credit_burn_rate,
        active_integrations=active_integrations,
        success_rate=success_rate,
        daily_usage=daily_usage,
        recent_requests=recent_requests
    )



# ==================== Member Management ====================

def list_workspace_members(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    role: str | None = None
) -> tuple[list[WorkspaceMemberPublic], int]:
    """
    List workspace members with filters and pagination.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user
        page: Page number
        page_size: Items per page
        search: Search query
        status: Filter by status
        role: Filter by role

    Returns:
        Tuple of (members list, total count)
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    # Build query
    stmt = select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)

    if status:
        stmt = stmt.where(WorkspaceMember.status == status)

    # Count total
    count_stmt = select(func.count()).select_from(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace_id
    )
    if status:
        count_stmt = count_stmt.where(WorkspaceMember.status == status)
    total = session.exec(count_stmt).one()

    # Pagination
    skip = (page - 1) * page_size
    stmt = stmt.offset(skip).limit(page_size)

    members = session.exec(stmt).all()

    # Build response
    result = []
    for member in members:
        # Get user info (may be None for pending invitations to non-existing users)
        user_obj = None
        if member.user_id:
            user_obj = session.get(User, member.user_id)

        # Get roles
        role_names = []
        for member_role in member.member_roles:
            role_obj = session.get(WorkspaceRole, member_role.role_id)
            if role_obj:
                role_names.append(role_obj.name)

        # For pending invitations without user, use invited_email
        if user_obj:
            display_name = user_obj.full_name or user_obj.email
            display_email = user_obj.email
            display_avatar = user_obj.avatar
        else:
            # Pending invitation for non-existing user
            display_name = member.invited_email or "Pending Invitation"
            display_email = member.invited_email or ""
            display_avatar = None

        member_public = WorkspaceMemberPublic(
            id=member.id,
            workspace_id=member.workspace_id,
            user_id=member.user_id,
            name=display_name,
            email=display_email,
            avatar=display_avatar,
            roles=role_names,
            credits_allocated=member.credits_allocated,
            status=member.status,
            joined_at=member.joined_at,
            last_active=member.last_active
        )
        result.append(member_public)

    return result, total


def add_workspace_member(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    add_data: AddMemberRequest,
    user: User
) -> WorkspaceMemberPublic:
    """
    Add an existing organization member to a workspace.
    
    This skips the invitation flow and directly adds the user as an active member.
    The user must already be a member of the workspace's organization.
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    # Check if the actor has access to manage this workspace
    check_workspace_access(session=session, workspace=workspace, user=user, require_owner=False)
    
    # 1. Verify the user to be added exists and belongs to the workspace's organization
    target_user = session.get(User, add_data.user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
        
    if workspace.organization_id:
        from app.models import OrganizationMember
        org_member = session.exec(
            select(OrganizationMember).where(
                and_(
                    OrganizationMember.organization_id == workspace.organization_id,
                    OrganizationMember.user_id == target_user.id
                )
            )
        ).first()
        if not org_member:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User must be a member of the organization before being added to a workspace"
            )

    # 2. Check if already a member of the workspace
    existing_member = session.exec(
        select(WorkspaceMember).where(
            and_(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == target_user.id
            )
        )
    ).first()
    
    if existing_member:
        if existing_member.status == "active":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already an active member of this workspace"
            )
        # If they were pending or suspended, we set them to active
        existing_member.status = "active"
        member = existing_member
    else:
        # 3. Create active workspace membership
        member = WorkspaceMember(
            workspace_id=workspace_id,
            user_id=target_user.id,
            credits_allocated=add_data.credits_to_allocate or Decimal("0.0000"),
            status="active",
            joined_at=datetime.now(timezone.utc)
        )
        session.add(member)
        session.flush()

    # 4. Assign Roles
    # Remove existing roles if any (for updates/reactivations)
    if existing_member:
        session.exec(
            delete(WorkspaceMemberRole).where(WorkspaceMemberRole.member_id == member.id)
        )

    for role_name in add_data.roles:
        stmt = select(WorkspaceRole).where(
            and_(
                WorkspaceRole.workspace_id == workspace_id,
                WorkspaceRole.name == role_name
            )
        )
        role = session.exec(stmt).first()
        if role:
            member_role = WorkspaceMemberRole(
                member_id=member.id,
                role_id=role.id,
                assigned_at=datetime.now(timezone.utc)
            )
            session.add(member_role)

    session.commit()
    session.refresh(member)

    # 5. Notify the user
    try:
        from app.notification_repository import create_notification
        create_notification(
            session=session,
            user_id=target_user.id,
            title="Workspace Access Granted",
            description=f"You have been added to the {workspace.name} workspace.",
            type="workspace_add",
            metadata={
                "workspace_id": str(workspace.id),
                "workspace_name": workspace.name,
                "status": "active",
                "actor_id": str(user.id),
                "actor_name": user.full_name or user.email
            }
        )
    except Exception as e:
        logger.error(f"Failed to create workspace add notification: {e}")

    # Build response
    return WorkspaceMemberPublic(
        id=member.id,
        workspace_id=member.workspace_id,
        user_id=member.user_id,
        name=target_user.full_name or target_user.email,
        email=target_user.email,
        avatar=target_user.avatar,
        roles=add_data.roles,
        credits_allocated=member.credits_allocated,
        status=member.status,
        joined_at=member.joined_at,
        last_active=member.last_active
    )


def remove_workspace_member(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    user: User
) -> None:
    """
    Remove a member from the workspace.

    Args:
        session: Database session
        workspace_id: Workspace ID
        member_id: Member ID
        user: Current user
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user, require_owner=True)

    member = session.get(WorkspaceMember, member_id)
    if not member or member.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    # Nullify recipient_id in transactions to avoid foreign key violation
    # This preserves the audit trail of the transaction while allowing member deletion
    transactions = session.exec(
        select(WorkspaceCreditTransaction).where(WorkspaceCreditTransaction.recipient_id == member_id)
    ).all()
    for tx in transactions:
        tx.recipient_id = None
        session.add(tx)
        
    session.delete(member)
    session.commit()

    logger.info(f"Member removed from workspace {workspace_id}: {member_id}")


def suspend_workspace_member(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    user: User
) -> WorkspaceMember:
    """
    Suspend a workspace member.

    Args:
        session: Database session
        workspace_id: Workspace ID
        member_id: Member ID
        user: Current user

    Returns:
        Updated member
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user, require_owner=True)

    member = session.get(WorkspaceMember, member_id)
    if not member or member.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    member.status = "suspended"
    session.add(member)
    session.commit()
    session.refresh(member)

    logger.info(f"Member suspended in workspace {workspace_id}: {member_id}")
    return member


# ==================== Role Management ====================

def list_workspace_roles(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User
) -> list[WorkspaceRolePublic]:
    """
    List workspace roles.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user

    Returns:
        List of roles
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    stmt = select(WorkspaceRole).where(WorkspaceRole.workspace_id == workspace_id)
    roles = session.exec(stmt).all()

    # Lazy initialize default roles if none exist (for existing workspaces)
    if not roles:
        roles = create_default_workspace_roles(session, workspace_id)
        session.commit()
        # No need to refresh roles as they are in the session

    return [WorkspaceRolePublic.model_validate(role) for role in roles]


def create_workspace_role(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    role_in: WorkspaceRoleCreate,
    user: User
) -> WorkspaceRole:
    """
    Create a workspace role.

    Args:
        session: Database session
        workspace_id: Workspace ID
        role_in: Role creation data
        user: Current user

    Returns:
        Created role
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user, require_owner=True)

    role = WorkspaceRole(
        workspace_id=workspace_id,
        name=role_in.name,
        description=role_in.description,
        is_custom=True,
        permissions=role_in.permissions.model_dump(),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    session.add(role)
    session.commit()
    session.refresh(role)

    logger.info(f"Role created in workspace {workspace_id}: {role.name}")
    return role


def delete_workspace_role(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
    user: User
) -> None:
    """
    Delete a workspace role.

    Args:
        session: Database session
        workspace_id: Workspace ID
        role_id: Role ID
        user: Current user
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user, require_owner=True)

    role = session.get(WorkspaceRole, role_id)
    if not role or role.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )

    session.delete(role)
    session.commit()

    logger.info(f"Role deleted from workspace {workspace_id}: {role_id}")


# ==================== Project Management ====================

def list_workspace_projects(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None
) -> tuple[list[WorkspaceProjectPublic], int]:
    """
    List workspace projects.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user
        page: Page number
        page_size: Items per page
        status: Filter by status

    Returns:
        Tuple of (projects list, total count)
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    stmt = select(WorkspaceProject).where(WorkspaceProject.workspace_id == workspace_id)
    if status:
        stmt = stmt.where(WorkspaceProject.status == status)

    # Count total
    count_stmt = select(func.count()).select_from(WorkspaceProject).where(
        WorkspaceProject.workspace_id == workspace_id
    )
    if status:
        count_stmt = count_stmt.where(WorkspaceProject.status == status)
    total = session.exec(count_stmt).one()

    # Pagination
    skip = (page - 1) * page_size
    stmt = stmt.offset(skip).limit(page_size).order_by(WorkspaceProject.created_at.desc())

    projects = session.exec(stmt).all()

    # Build response
    result = []
    for project in projects:
        # Get member IDs
        member_ids = [str(pm.member_id) for pm in project.project_members]

        project_public = WorkspaceProjectPublic.model_validate(project)
        project_public.members = member_ids
        result.append(project_public)

    return result, total


def create_workspace_project(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    project_in: WorkspaceProjectCreate,
    user: User
) -> WorkspaceProject:
    """
    Create a workspace project.

    Args:
        session: Database session
        workspace_id: Workspace ID
        project_in: Project creation data
        user: Current user

    Returns:
        Created project
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    project = WorkspaceProject(
        workspace_id=workspace_id,
        name=project_in.name,
        description=project_in.description,
        created_by=user.id,
        status="active",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc)
    )
    session.add(project)
    session.flush()

    # Add members
    for member_id in project_in.members:
        project_member = WorkspaceProjectMember(
            project_id=project.id,
            member_id=member_id,
            added_at=datetime.now(timezone.utc)
        )
        session.add(project_member)

    session.commit()
    session.refresh(project)

    logger.info(f"Project created in workspace {workspace_id}: {project.name}")
    return project


def update_workspace_project(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    project_in: WorkspaceProjectUpdate,
    user: User
) -> WorkspaceProject:
    """
    Update a workspace project.

    Args:
        session: Database session
        workspace_id: Workspace ID
        project_id: Project ID
        project_in: Update data
        user: Current user

    Returns:
        Updated project
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    project = session.get(WorkspaceProject, project_id)
    if not project or project.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    if project_in.name is not None:
        project.name = project_in.name
    if project_in.description is not None:
        project.description = project_in.description
    if project_in.status is not None:
        project.status = project_in.status

    project.updated_at = datetime.now(timezone.utc)

    session.add(project)
    session.commit()
    session.refresh(project)

    logger.info(f"Project updated in workspace {workspace_id}: {project_id}")
    return project


def delete_workspace_project(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    user: User
) -> None:
    """
    Delete a workspace project.

    Args:
        session: Database session
        workspace_id: Workspace ID
        project_id: Project ID
        user: Current user
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    project = session.get(WorkspaceProject, project_id)
    if not project or project.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )

    session.delete(project)
    session.commit()

    logger.info(f"Project deleted from workspace {workspace_id}: {project_id}")


# ==================== Credit Management ====================

def allocate_credits_to_member(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    allocation_data: AllocateCreditsRequest,
    user: User
) -> CreditTransactionPublic:
    """
    Allocate credits to a workspace member.

    Args:
        session: Database session
        workspace_id: Workspace ID
        member_id: Member ID
        allocation_data: Allocation data
        user: Current user

    Returns:
        Credit transaction
    """
    try:
        workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
        check_workspace_access(session=session, workspace=workspace, user=user, require_owner=True)
    except Exception as e:
        logger.error(f"Error accessing workspace {workspace_id}: {str(e)}")
        raise

    # Check if workspace has enough credits
    if workspace.credits_balance < allocation_data.amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Insufficient workspace credits"
        )

    member = session.get(WorkspaceMember, member_id)
    if not member or member.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    # Get the user associated with this workspace member
    if not member.user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot allocate credits to a pending member"
        )

    recipient_user = session.get(User, member.user_id)
    if not recipient_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found for this member"
        )

    # Perform centralized sharing via OrganizationCreditService
    if workspace.organization_id:
        from app.services.organization_credit_service import OrganizationCreditService
        
        # This handles:
        # 1. Debit Organization Wallet (atomic)
        # 2. Credit Member Wallet (atomic) 
        # 3. Log OrganizationCreditTransaction
        # 4. Sync cached balances (org.credits_balance and user.credits)
        OrganizationCreditService.share_credits(
            session=session,
            org_id=workspace.organization_id,
            member_id=recipient_user.id,
            amount=allocation_data.amount,
            admin_id=user.id,
            description=allocation_data.message or f"Credits allocated from workspace: {workspace.name}",
            workspace_id=workspace_id,
            commit=False # We'll commit everything together
        )
    else:
        # Fallback for manual updates if no organization is attached (unlikely in current architecture)
        workspace.credits_balance -= allocation_data.amount
        recipient_user.credits = (recipient_user.credits or 0) + int(allocation_data.amount)
        session.add(workspace)
        session.add(recipient_user)

    # Update member's allocated credits (workspace local tracking)
    member.credits_allocated = (member.credits_allocated or Decimal("0")) + allocation_data.amount

    # Create transaction in workspace ledger (for workspace visibility)
    transaction = WorkspaceCreditTransaction(
        workspace_id=workspace_id,
        type="allocation",
        amount=allocation_data.amount,
        balance=workspace.credits_balance, # Note: This might be slightly stale if we used Org Treasury, but kept for audit
        description=allocation_data.message or f"Credits allocated from {workspace.name}",
        recipient_id=member_id,
        status="completed",
        created_at=datetime.now(timezone.utc)
    )

    try:
        session.add(member)
        session.add(transaction)
        
        # Create in-app notification for the recipient
        create_notification(
            session=session,
            user_id=recipient_user.id,
            title="Credits Received! 🎉",
            description=f"You received {float(allocation_data.amount)} credits from workspace: {workspace.name}.",
            type="credit_received",
            metadata={
                "workspace_id": str(workspace_id),
                "amount": float(allocation_data.amount),
                "sender_id": str(user.id)
            },
            commit=False
        )

        session.commit()
        session.refresh(transaction)
    except Exception as e:
        session.rollback()
        logger.error(f"Database error allocating credits: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to allocate credits: {str(e)}"
        )

    logger.info(f"Credits allocated in workspace {workspace_id}: {allocation_data.amount} to member {member_id} (user: {recipient_user.email})")

    # Get recipient name (we already have the user object)
    recipient_name = recipient_user.full_name or recipient_user.email

    # Create the public transaction object manually since recipient_name is not in DB
    try:
        transaction_public = CreditTransactionPublic(
            id=transaction.id,
            workspace_id=transaction.workspace_id,
            type=transaction.type,
            amount=transaction.amount,
            balance=transaction.balance,
            description=transaction.description,
            recipient_id=transaction.recipient_id,
            recipient_name=recipient_name,
            status=transaction.status,
            created_at=transaction.created_at
        )
    except Exception as e:
        logger.error(f"Error creating transaction response: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to format transaction response: {str(e)}"
        )

    # Send email notification to the recipient
    try:
        email_service = EmailService()

        # Create email content
        html_content = f"""
        <html>
        <body style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: linear-gradient(135deg, #0055BA 0%, #003d85 100%); padding: 30px; border-radius: 10px; text-align: center;">
                <h1 style="color: white; margin: 0;">Credits Allocated! 🎉</h1>
            </div>

            <div style="background: #f9f9f9; padding: 30px; border-radius: 10px; margin-top: 20px;">
                <p style="font-size: 16px; color: #333;">Hello {recipient_name},</p>

                <p style="font-size: 16px; color: #333;">
                    Great news! You have been allocated <strong style="color: #0055BA; font-size: 24px;">{int(allocation_data.amount)} AI credits</strong>
                    from the <strong>{workspace.name}</strong> workspace.
                </p>

                <div style="background: white; padding: 20px; border-radius: 8px; margin: 20px 0; border-left: 4px solid #0055BA;">
                    <p style="margin: 5px 0; color: #666;">
                        <strong>Amount:</strong> {int(allocation_data.amount)} credits
                    </p>
                    <p style="margin: 5px 0; color: #666;">
                        <strong>Workspace:</strong> {workspace.name}
                    </p>
                    {'<p style="margin: 5px 0; color: #666;"><strong>Message:</strong> ' + str(allocation_data.message) + '</p>' if allocation_data.message else ''}
                    <p style="margin: 5px 0; color: #666;">
                        <strong>Date:</strong> {datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")}
                    </p>
                </div>

                <p style="font-size: 16px; color: #333;">
                    These credits have been added to your personal wallet and are ready to use!
                </p>

                <div style="text-align: center; margin-top: 30px;">
                    <a href="{settings.FRONTEND_HOST}/dashboard"
                       style="background: #0055BA; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">
                        View Your Wallet
                    </a>
                </div>
            </div>

            <div style="text-align: center; margin-top: 20px; color: #999; font-size: 12px;">
                <p>This is an automated notification from Qorebit</p>
                <p>© {datetime.now().year} Qorebit. All rights reserved.</p>
            </div>
        </body>
        </html>
        """

        email_service.send_email(
            email_to=recipient_user.email,
            subject=f"🎉 You've Received {int(allocation_data.amount)} AI Credits!",
            html_content=html_content,
            email_type=EmailType.TRANSACTION_ALERT,
            metadata={
                "workspace_id": str(workspace_id),
                "transaction_id": str(transaction.id),
                "amount": float(allocation_data.amount),
                "recipient_id": str(recipient_user.id)
            }
        )
        logger.info(f"Credit allocation email sent to {recipient_user.email}")
    except Exception as e:
        # Don't fail the transaction if email fails, just log it
        logger.warning(f"Failed to send credit allocation email to {recipient_user.email}: {str(e)}")

    return transaction_public


def top_up_workspace_credits(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    top_up_data: TopUpCreditsRequest,
    user: User
) -> CreditTransactionPublic:
    """
    Top up workspace credits.

    Args:
        session: Database session
        workspace_id: Workspace ID
        top_up_data: Top-up data
        user: Current user

    Returns:
        Credit transaction
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user, require_owner=True)

    # Update workspace credits
    workspace.credits_balance += top_up_data.amount

    # Create transaction
    transaction = WorkspaceCreditTransaction(
        workspace_id=workspace_id,
        type="purchase",
        amount=top_up_data.amount,
        balance=workspace.credits_balance,
        description=f"Credits top-up",
        status="completed",
        created_at=datetime.now(timezone.utc)
    )

    session.add(workspace)
    session.add(transaction)
    session.commit()
    session.refresh(transaction)

    logger.info(f"Credits topped up in workspace {workspace_id}: {top_up_data.amount}")

    transaction_public = CreditTransactionPublic.model_validate(transaction)
    transaction_public.recipient_name = None

    return transaction_public


def list_credit_transactions(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User,
    page: int = 1,
    page_size: int = 20,
    type: str | None = None
) -> tuple[list[CreditTransactionPublic], int]:
    """
    List workspace credit transactions.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user
        page: Page number
        page_size: Items per page
        type: Filter by transaction type

    Returns:
        Tuple of (transactions list, total count)
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    stmt = select(WorkspaceCreditTransaction).where(
        WorkspaceCreditTransaction.workspace_id == workspace_id
    )
    if type:
        stmt = stmt.where(WorkspaceCreditTransaction.type == type)

    # Count total
    count_stmt = select(func.count()).select_from(WorkspaceCreditTransaction).where(
        WorkspaceCreditTransaction.workspace_id == workspace_id
    )
    if type:
        count_stmt = count_stmt.where(WorkspaceCreditTransaction.type == type)
    total = session.exec(count_stmt).one()

    # Pagination
    skip = (page - 1) * page_size
    stmt = stmt.offset(skip).limit(page_size).order_by(WorkspaceCreditTransaction.created_at.desc())

    transactions = session.exec(stmt).all()

    # Build response
    result = []
    for transaction in transactions:
        recipient_name = None
        if transaction.recipient_id:
            member = session.get(WorkspaceMember, transaction.recipient_id)
            if member:
                user_obj = session.get(User, member.user_id)
                if user_obj:
                    recipient_name = user_obj.full_name or user_obj.email

        # Create the public transaction object manually since recipient_name is not in DB
        transaction_public = CreditTransactionPublic(
            id=transaction.id,
            workspace_id=transaction.workspace_id,
            type=transaction.type,
            amount=transaction.amount,
            balance=transaction.balance,
            description=transaction.description,
            recipient_id=transaction.recipient_id,
            recipient_name=recipient_name,
            status=transaction.status,
            created_at=transaction.created_at
        )
        result.append(transaction_public)

    return result, total


# ==================== Usage Reports ====================

def get_usage_report(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User,
    period: str,
    start_date: str | None = None,
    end_date: str | None = None
) -> WorkspaceUsageReport:
    """
    Get workspace usage report.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user
        period: Report period
        start_date: Start date for custom period
        end_date: End date for custom period

    Returns:
        Usage report
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    # Calculate date range
    now = datetime.now(timezone.utc)
    if period == "day":
        start = now - timedelta(days=1)
    elif period == "week":
        start = now - timedelta(days=7)
    elif period == "month":
        start = now - timedelta(days=30)
    else:
        # Custom period
        start = datetime.fromisoformat(start_date) if start_date else now - timedelta(days=30)
        now = datetime.fromisoformat(end_date) if end_date else now

    # Total credits consumed
    total_credits = session.exec(
        select(func.sum(WorkspaceCreditTransaction.amount)).where(
            and_(
                WorkspaceCreditTransaction.workspace_id == workspace_id,
                WorkspaceCreditTransaction.type == "usage",
                WorkspaceCreditTransaction.created_at >= start,
                WorkspaceCreditTransaction.created_at <= now
            )
        )
    ).one() or Decimal("0.0000")

    # Total API calls
    total_api_calls = session.exec(
        select(func.sum(WorkspaceProject.api_calls_count)).where(
            WorkspaceProject.workspace_id == workspace_id
        )
    ).one() or 0

    # Placeholder data for per-member and per-project usage
    per_member_usage: list[MemberUsage] = []
    per_project_usage: list[ProjectUsage] = []
    trends: list[UsageTrend] = []

    return WorkspaceUsageReport(
        workspace_id=workspace_id,
        period=period,
        total_credits_consumed=total_credits,
        total_api_calls=total_api_calls,
        total_tokens=0,  # Placeholder
        per_member_usage=per_member_usage,
        per_project_usage=per_project_usage,
        trends=trends
    )



# ==================== Activities / Audit Logs ====================

def list_workspace_activities(
    *,
    session: Session,
    workspace_id: uuid.UUID,
    user: User,
    page: int = 1,
    page_size: int = 10
) -> tuple[list[dict], int]:
    """
    List recent activities (audit logs) for the workspace.

    Args:
        session: Database session
        workspace_id: Workspace ID
        user: Current user
        page: Page number
        page_size: Items per page

    Returns:
        Tuple of (activities list, total count)
    """
    workspace = get_workspace_by_id(session=session, workspace_id=workspace_id)
    check_workspace_access(session=session, workspace=workspace, user=user)

    # Query AuditLog
    from app.models import AuditLog
    
    stmt = select(AuditLog).where(AuditLog.workspace_id == workspace_id).order_by(AuditLog.timestamp.desc())
    
    # Count
    count_stmt = select(func.count()).select_from(AuditLog).where(AuditLog.workspace_id == workspace_id)
    total = session.exec(count_stmt).one()
    
    # Pagination
    stmt = stmt.offset((page - 1) * page_size).limit(page_size)
    logs = session.exec(stmt).all()
    
    # Format for frontend
    activities = []
    for log in logs:
        activities.append({
            "id": str(log.id),
            "type": log.action.lower(), # converted to lowercase for frontend mapping
            "action": log.action,
            "actorName": log.actor_name,
            "targetType": log.target_type,
            "targetId": log.target_id,
            "details": log.details if hasattr(log, "details") else {}, # Handle potential missing attribute
            "timestamp": log.timestamp.replace(tzinfo=timezone.utc).isoformat() if log.timestamp.tzinfo is None else log.timestamp.isoformat(),
        })
        
    return activities, total
