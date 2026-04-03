"""
Workspace API Routes

Provides REST API endpoints for workspace management, including:
- Workspace CRUD operations
- Member management
- Role management
- Project management
- Credit allocation and transactions
- Usage reports and analytics
"""
import uuid
import os
import shutil
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, status
from fastapi.responses import JSONResponse
from sqlmodel import select
from pydantic import BaseModel

from app.api.deps import CurrentUser, SessionDep, RequiresPermission
from app.models import (
    Message,
    User,
    WorkspaceCreate,
    WorkspaceUpdate,
    WorkspacePublic,
    WorkspacesPublic,
    WorkspaceMember,
    WorkspaceMemberPublic,
    WorkspaceRole,
    WorkspaceMemberRole,
    AddMemberRequest,
    WorkspaceRoleCreate,
    WorkspaceRoleUpdate,
    WorkspaceRolePublic,
    WorkspaceProjectCreate,
    WorkspaceProjectUpdate,
    WorkspaceProjectPublic,
    AllocateCreditsRequest,
    TopUpCreditsRequest,
    CreditTransactionPublic,
    WorkspaceDashboardStats,
    WorkspaceUsageReport,
)
from app.services import workspace_service

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


# ==================== Helper Functions ====================

def serialize_project(project) -> dict:
    """Helper to convert project to camelCase dict"""
    # Get members list - either from members attribute or project_members relationship
    members = []
    if hasattr(project, 'members'):
        members = project.members
    elif hasattr(project, 'project_members'):
        # Extract member IDs from project_members relationship
        members = [str(pm.member_id) for pm in project.project_members]

    return {
        "id": str(project.id),
        "workspaceId": str(project.workspace_id),
        "name": project.name,
        "description": project.description,
        "createdBy": str(project.created_by),
        "status": project.status,
        "creditsUsed": str(project.credits_used),
        "apiCallsCount": project.api_calls_count,
        "lastActivity": project.last_activity.isoformat() if project.last_activity else None,
        "createdAt": project.created_at.isoformat(),
        "updatedAt": project.updated_at.isoformat(),
        "members": members,
    }


# ==================== Workspace Management ====================

@router.post("", response_model=WorkspacePublic, response_model_by_alias=True, status_code=201)
def create_workspace(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_in: WorkspaceCreate,
) -> Any:
    """
    Create a new workspace.

    The current user will be set as the workspace owner.
    """
    workspace = workspace_service.create_workspace(
        session=session,
        workspace_in=workspace_in,
        user=current_user
    )
    return workspace


@router.get("", response_model=WorkspacesPublic, response_model_by_alias=True)
def list_workspaces(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """
    List all workspaces for the current user.

    Returns workspaces where the user is either the owner or a member.
    """
    workspaces, total = workspace_service.list_workspaces(
        session=session,
        user=current_user,
        page=page,
        page_size=page_size
    )
    return WorkspacesPublic(
        workspaces=workspaces,
        total=total
    )


@router.get("/count/all", response_model=dict, dependencies=[Depends(RequiresPermission("organization:view_all"))])
def get_total_workspaces_count(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get total count of all workspaces in the system.
    """
    count = workspace_service.count_all_workspaces(session=session)
    return {"total": count}


@router.get("/{workspace_id}", response_model=WorkspacePublic, response_model_by_alias=True)
def get_workspace(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> Any:
    """
    Get workspace details by ID.

    User must be the owner or a member to access.
    """
    workspace = workspace_service.get_workspace(
        session=session,
        workspace_id=workspace_id,
        user=current_user
    )
    return workspace.model_dump(by_alias=True, mode='json')


@router.put("/{workspace_id}", response_model=WorkspacePublic, response_model_by_alias=True)
def update_workspace(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    workspace_in: WorkspaceUpdate,
) -> Any:
    """
    Update workspace details.

    Only the workspace owner can update workspace details.
    """
    workspace = workspace_service.update_workspace(
        session=session,
        workspace_id=workspace_id,
        workspace_in=workspace_in,
        user=current_user
    )
    return workspace


@router.delete("/{workspace_id}", response_model=Message)
def delete_workspace(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> Any:
    """
    Delete a workspace.

    Only the workspace owner can delete the workspace.
    This will cascade delete all members, projects, and transactions.
    """
    workspace_service.delete_workspace(
        session=session,
        workspace_id=workspace_id,
        user=current_user
    )
    return Message(message="Workspace deleted successfully")


@router.post("/{workspace_id}/avatar", response_model=WorkspacePublic, response_model_by_alias=True)
def upload_workspace_avatar(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
) -> Any:
    """
    Upload workspace avatar.
    """
    # Check access
    workspace = workspace_service.get_workspace(
        session=session,
        workspace_id=workspace_id,
        user=current_user
    )
    if workspace.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can upload an avatar")

    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
        )

    # Validate file size (max 5MB)
    file.file.seek(0, 2)
    file_size = file.file.tell()
    file.file.seek(0)

    max_size = 5 * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {max_size / 1024 / 1024}MB",
        )

    # Create uploads directory
    upload_dir = Path("uploads/workspaces")
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    file_extension = Path(file.filename).suffix if file.filename else ".jpg"
    unique_filename = f"{workspace_id}{file_extension}"
    file_path = upload_dir / unique_filename

    # Save file
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")
    finally:
        file.file.close()

    # Update avatar URL
    workspace.avatar = f"/uploads/workspaces/{unique_filename}"
    workspace.updated_at = datetime.now(timezone.utc)
    session.add(workspace)
    session.commit()
    session.refresh(workspace)

    return workspace.model_dump(by_alias=True, mode='json')


@router.delete("/{workspace_id}/avatar", response_model=WorkspacePublic, response_model_by_alias=True)
def delete_workspace_avatar(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> Any:
    """
    Delete workspace avatar.
    """
    # Check access
    workspace = workspace_service.get_workspace(
        session=session,
        workspace_id=workspace_id,
        user=current_user
    )
    if workspace.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the owner can delete the avatar")

    if workspace.avatar:
        try:
            file_path = Path(workspace.avatar.lstrip("/"))
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass

    workspace.avatar = None
    workspace.updated_at = datetime.now(timezone.utc)
    session.add(workspace)
    session.commit()
    session.refresh(workspace)

    return workspace.model_dump(by_alias=True, mode='json')


@router.get("/{workspace_id}/dashboard-stats")
def get_dashboard_stats(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    filter_by_user: bool = Query(False, description="Filter stats for the current user only")
) -> Any:
    """
    Get workspace dashboard statistics.

    Returns metrics like credit balance, member count, project count,
    API calls, and usage trends.
    """
    stats = workspace_service.get_dashboard_stats(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        filter_by_user=filter_by_user
    )

    # Manual conversion to camelCase since SQLModel doesn't properly handle serialization_alias
    result = {
        "creditsBalance": str(stats.credits_balance),
        "totalMembers": stats.total_members,
        "totalProjects": stats.total_projects,
        "totalApiCalls": stats.total_api_calls,
        "creditsUsedToday": str(stats.credits_used_today),
        "creditsUsedThisMonth": str(stats.credits_used_this_month),
        "tokensUsedToday": stats.tokens_used_today,
        "tokensUsedThisMonth": stats.tokens_used_this_month,
        "creditBurnRate": str(stats.credit_burn_rate),
        "activeIntegrations": stats.active_integrations,
        "successRate": str(stats.success_rate),
    }

    return JSONResponse(content=result)


# ==================== Member Management ====================

@router.get("/{workspace_id}/members", response_model=dict, response_model_by_alias=True)
def list_workspace_members(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None),
    status: str | None = Query(default=None),
    role: str | None = Query(default=None),
) -> Any:
    """
    List workspace members with pagination and filters.

    Supports filtering by status, role, and search query.
    Returns paginated results with total count.
    """
    members, total = workspace_service.list_workspace_members(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        role=role
    )
    return {
        "members": [m.model_dump(by_alias=True, mode='json') for m in members],
        "total": total
    }


@router.post("/{workspace_id}/members/add", response_model=WorkspaceMemberPublic, response_model_by_alias=True)
def add_workspace_member(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    add_data: AddMemberRequest,
) -> Any:
    """
    Add an existing organization member to the workspace.

    Directly creates an active membership for users already in the organization.
    """
    member = workspace_service.add_workspace_member(
        session=session,
        workspace_id=workspace_id,
        add_data=add_data,
        user=current_user
    )
    return JSONResponse(content=member.model_dump(by_alias=True, mode='json'))


@router.delete("/{workspace_id}/members/{member_id}", response_model=Message)
def remove_workspace_member(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
) -> Any:
    """
    Remove a member from the workspace.

    Only the workspace owner can remove members.
    """
    workspace_service.remove_workspace_member(
        session=session,
        workspace_id=workspace_id,
        member_id=member_id,
        user=current_user
    )
    return Message(message="Member removed successfully")


@router.post("/{workspace_id}/members/{member_id}/suspend", response_model=WorkspaceMemberPublic, response_model_by_alias=True)
def suspend_workspace_member(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
) -> Any:
    """
    Suspend a workspace member.

    Suspended members cannot access workspace resources.
    Only the workspace owner can suspend members.
    """
    from app.models import User, WorkspaceRole, WorkspaceMemberRole

    member = workspace_service.suspend_workspace_member(
        session=session,
        workspace_id=workspace_id,
        member_id=member_id,
        user=current_user
    )

    # Get user info
    user_obj = session.get(User, member.user_id) if member.user_id else None

    # Get roles
    role_names = []
    for member_role in member.member_roles:
        role_obj = session.get(WorkspaceRole, member_role.role_id)
        if role_obj:
            role_names.append(role_obj.name)

    # Build response
    if user_obj:
        display_name = user_obj.full_name or user_obj.email
        display_email = user_obj.email
        display_avatar = user_obj.avatar
    else:
        display_name = member.invited_email or "Unknown"
        display_email = member.invited_email or ""
        display_avatar = None

    return WorkspaceMemberPublic(
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


class AssignRolesRequest(BaseModel):
    """Request body for assigning roles to a member"""
    role_ids: list[str]


@router.put("/{workspace_id}/members/{member_id}/roles", response_model=WorkspaceMemberPublic, response_model_by_alias=True)
def assign_member_roles(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    request: AssignRolesRequest,
) -> Any:
    """
    Assign roles to a workspace member.

    Replaces all existing roles with the new set of roles.
    Only the workspace owner can assign roles.
    """
    from app.models import User, WorkspaceRole, WorkspaceMemberRole

    # Get workspace and check access
    workspace = workspace_service.get_workspace_by_id(session=session, workspace_id=workspace_id)
    workspace_service.check_workspace_access(session=session, workspace=workspace, user=current_user, require_owner=True)

    # Get member
    member = session.get(WorkspaceMember, member_id)
    if not member or member.workspace_id != workspace_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Member not found"
        )

    # Delete existing role assignments
    from sqlmodel import delete
    stmt = delete(WorkspaceMemberRole).where(WorkspaceMemberRole.member_id == member_id)
    session.exec(stmt)

    # Assign new roles
    role_names = []
    for role_id in request.role_ids:
        try:
            role_uuid = uuid.UUID(role_id)
        except ValueError:
            continue

        role = session.get(WorkspaceRole, role_uuid)
        if role and role.workspace_id == workspace_id:
            member_role = WorkspaceMemberRole(
                member_id=member_id,
                role_id=role_uuid,
                assigned_at=datetime.now(timezone.utc)
            )
            session.add(member_role)
            role_names.append(role.name)

    session.commit()
    session.refresh(member)

    # Get user info for response
    user_obj = session.get(User, member.user_id) if member.user_id else None
    if user_obj:
        display_name = user_obj.full_name or user_obj.email
        display_email = user_obj.email
        display_avatar = user_obj.avatar
    else:
        display_name = member.invited_email or "Unknown"
        display_email = member.invited_email or ""
        display_avatar = None

    return WorkspaceMemberPublic(
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


# ==================== Role Management ====================

@router.get("/{workspace_id}/roles", response_model=dict, response_model_by_alias=True)
def list_workspace_roles(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
) -> Any:
    """
    List all roles for a workspace.

    Returns both system roles and custom roles.
    """
    roles = workspace_service.list_workspace_roles(
        session=session,
        workspace_id=workspace_id,
        user=current_user
    )
    return {
        "roles": [r.model_dump(by_alias=True, mode='json') for r in roles],
        "total": len(roles)
    }


@router.post("/{workspace_id}/roles", response_model=WorkspaceRolePublic, response_model_by_alias=True, status_code=201)
def create_workspace_role(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    role_in: WorkspaceRoleCreate,
) -> Any:
    """
    Create a custom workspace role.

    Only the workspace owner can create roles.
    """
    role = workspace_service.create_workspace_role(
        session=session,
        workspace_id=workspace_id,
        role_in=role_in,
        user=current_user
    )
    return role


@router.delete("/{workspace_id}/roles/{role_id}", response_model=Message)
def delete_workspace_role(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    role_id: uuid.UUID,
) -> Any:
    """
    Delete a custom workspace role.

    Only the workspace owner can delete roles.
    Cannot delete system roles.
    """
    workspace_service.delete_workspace_role(
        session=session,
        workspace_id=workspace_id,
        role_id=role_id,
        user=current_user
    )
    return Message(message="Role deleted successfully")


# ==================== Project Management ====================

@router.get("/{workspace_id}/projects", response_model=dict, response_model_by_alias=True)
def list_workspace_projects(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    status: str | None = Query(default=None),
) -> Any:
    """
    List workspace projects with pagination.

    Supports filtering by status.
    Returns paginated results with total count.
    """
    projects, total = workspace_service.list_workspace_projects(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        page=page,
        page_size=page_size,
        status=status
    )
    return {
        "projects": [serialize_project(p) for p in projects],
        "total": total
    }


@router.post("/{workspace_id}/projects", status_code=201)
def create_workspace_project(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    project_in: WorkspaceProjectCreate,
) -> Any:
    """
    Create a new workspace project.

    Optionally assign members to the project.
    """
    project = workspace_service.create_workspace_project(
        session=session,
        workspace_id=workspace_id,
        project_in=project_in,
        user=current_user
    )
    return JSONResponse(content=serialize_project(project), status_code=201)


@router.put("/{workspace_id}/projects/{project_id}")
def update_workspace_project(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
    project_in: WorkspaceProjectUpdate,
) -> Any:
    """
    Update workspace project details.

    Can update name, description, status, and assigned members.
    """
    project = workspace_service.update_workspace_project(
        session=session,
        workspace_id=workspace_id,
        project_id=project_id,
        project_in=project_in,
        user=current_user
    )
    return JSONResponse(content=serialize_project(project))


@router.delete("/{workspace_id}/projects/{project_id}", response_model=Message)
def delete_workspace_project(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    project_id: uuid.UUID,
) -> Any:
    """
    Delete a workspace project.

    Only the workspace owner or project creator can delete.
    """
    workspace_service.delete_workspace_project(
        session=session,
        workspace_id=workspace_id,
        project_id=project_id,
        user=current_user
    )
    return Message(message="Project deleted successfully")


# ==================== Credit Management ====================

@router.get("/{workspace_id}/credit-transactions", response_model=dict, response_model_by_alias=True)
def list_credit_transactions(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    transaction_type: str | None = Query(default=None, alias="type"),
    current_user_with_perm: User = Depends(RequiresPermission("credit:transactions_view")),
) -> Any:
    """
    List workspace credit transactions.

    Returns history of credit purchases, allocations, usage, and refunds.
    Supports pagination and filtering by transaction type.
    """
    transactions, total = workspace_service.list_credit_transactions(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        page=page,
        page_size=page_size,
        type=transaction_type
    )
    return {
        "transactions": [
            {
                **t.model_dump(by_alias=True, mode='json'),
                "amount": float(t.amount),
                "balance": float(t.balance)
            }
            for t in transactions
        ],
        "total": total
    }


@router.post("/{workspace_id}/members/{member_id}/allocate-credits", response_model=CreditTransactionPublic, response_model_by_alias=True)
def allocate_credits_to_member(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    member_id: uuid.UUID,
    allocation_data: AllocateCreditsRequest,
    current_user_with_perm: User = Depends(RequiresPermission("credit:can_share_credit")),
) -> Any:
    """
    Allocate credits to a workspace member.

    Credits are deducted from the workspace balance and added to the member's allocation.
    Only the workspace owner can allocate credits.
    """
    transaction = workspace_service.allocate_credits_to_member(
        session=session,
        workspace_id=workspace_id,
        member_id=member_id,
        allocation_data=allocation_data,
        user=current_user
    )
    return transaction.model_dump(by_alias=True, mode='json')


@router.post("/{workspace_id}/credits/top-up", response_model=CreditTransactionPublic, response_model_by_alias=True)
def top_up_workspace_credits(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    topup_data: TopUpCreditsRequest,
) -> Any:
    """
    Top up workspace credits.

    Adds credits to the workspace balance through a purchase transaction.
    Only the workspace owner can top up credits.
    """
    transaction = workspace_service.top_up_workspace_credits(
        session=session,
        workspace_id=workspace_id,
        topup_data=topup_data,
        user=current_user
    )
    return transaction.model_dump(by_alias=True, mode='json')


# ==================== Usage Reports ====================

@router.get("/{workspace_id}/usage-report", response_model=WorkspaceUsageReport, response_model_by_alias=True)
def get_usage_report(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    period: str = Query(default="month", regex="^(day|week|month|custom)$"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> Any:
    """
    Get workspace usage report.

    Returns detailed analytics including:
    - Total credits consumed
    - Per-member usage
    - Per-project usage
    - Usage trends over time

    Period options: day, week, month, custom
    For custom period, provide start_date and end_date in YYYY-MM-DD format.
    """
    report = workspace_service.get_usage_report(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        period=period,
        start_date=start_date,
        end_date=end_date
    )
    return report


@router.get("/{workspace_id}/usage-report/export")
def export_usage_report(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    period: str = Query(default="month", regex="^(day|week|month|custom)$"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> Response:
    """
    Export usage report as CSV.

    Downloads a CSV file with detailed usage data.
    Same parameters as the usage-report endpoint.
    """
    import csv
    import io

    # Get the usage report
    report = workspace_service.get_usage_report(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        period=period,
        start_date=start_date,
        end_date=end_date
    )

    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow([
        "Type", "Name", "Email", "Credits Used", "API Calls", "Tokens"
    ])

    # Write per-member usage
    for member_usage in report.per_member_usage:
        writer.writerow([
            "Member",
            member_usage.member_name,
            member_usage.member_email,
            float(member_usage.credits_used),
            member_usage.api_calls,
            member_usage.tokens
        ])

    # Write per-project usage
    for project_usage in report.per_project_usage:
        writer.writerow([
            "Project",
            project_usage.project_name,
            "",
            float(project_usage.credits_used),
            project_usage.api_calls,
            project_usage.tokens
        ])

    # Get CSV content
    csv_content = output.getvalue()
    output.close()

    # Return as downloadable file
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=workspace_{workspace_id}_usage_report.csv"
        }
    )

@router.get("/{workspace_id}/activities", response_model=dict)
def list_workspace_activities(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=50),
) -> Any:
    """
    List recent activities (audit logs) for the workspace.
    """
    activities, total = workspace_service.list_workspace_activities(
        session=session,
        workspace_id=workspace_id,
        user=current_user,
        page=page,
        page_size=page_size
    )
    return {
        "activities": activities,
        "total": total
    }
