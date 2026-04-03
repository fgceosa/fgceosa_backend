"""
Projects API Routes

Production-grade project management endpoints with full RBAC support.

Endpoints:
- POST /projects - Create a new project
- GET /projects - List all user/org projects
- GET /projects/:id - Get project details
- PATCH /projects/:id - Update a project
- DELETE /projects/:id - Delete a project
- GET /projects/:id/usage - Get project usage analytics
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlmodel import Session

from app.api.deps import CurrentUser, SessionDep
from app.models import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    ProjectPublic,
    ProjectCreated,
    ProjectsPublic,
    ProjectUsageResponse,
    User,
)
from app.services import project_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/projects", tags=["projects"])


# ==================== Create Project ====================

@router.post("", response_model=ProjectCreated, status_code=status.HTTP_201_CREATED)
def create_project(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    project_in: ProjectCreate,
) -> Any:
    """
    Create a new project.

    **Validation:**
    - API key must exist and be owned by the user
    - API key must be active
    - API key cannot already be linked to another project
    - Project name must be unique (per user/org)
    - Project URL must be valid (if provided)
    - User must be a member of the organization (if org_id provided)

    **RBAC:**
    - `user`: Can create projects for themselves
    - `org_super_admin`: Can create projects for their organization

    **Returns:**
    - Created project with all details
    """
    try:
        project = project_service.create_project(
            session=session,
            project_in=project_in,
            user=current_user
        )

        return project

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating project: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create project: {str(e)}"
        )


# ==================== List Projects ====================

@router.get("", response_model=ProjectsPublic)
def list_projects(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Maximum number of records"),
    include_org: bool = Query(True, description="Include organization projects (if org_super_admin)"),
) -> Any:
    """
    Get all projects for the current user.

    **What's included:**
    - Projects owned by the user
    - Projects in organizations where user is `org_super_admin` (if include_org=True)

    **RBAC:**
    - `user`: Can see their own projects
    - `org_super_admin`: Can see their projects + organization projects

    **Pagination:**
    - Default page size: 100
    - Maximum page size: 100

    **Returns:**
    - Paginated list of projects
    - Total count
    """
    try:
        projects, total = project_service.get_user_projects(
            session=session,
            user=current_user,
            skip=skip,
            limit=limit,
            include_org_projects=include_org
        )

        return ProjectsPublic(data=projects, count=total)

    except Exception as e:
        logger.error(f"Error listing projects: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list projects: {str(e)}"
        )


# ==================== Get Project ====================

@router.get("/{project_id}", response_model=ProjectPublic)
def get_project(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    project_id: UUID,
) -> Any:
    """
    Get detailed information about a specific project.

    **RBAC:**
    - `user`: Can only see projects they own
    - `org_super_admin`: Can see projects in their organization

    **Returns:**
    - Project details

    **Errors:**
    - 404: Project not found
    - 403: Not authorized to access this project
    """
    # Get project
    project = session.get(Project, project_id)

    if not project or project.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )

    # Check access
    project_service.check_project_access(
        session=session,
        project=project,
        user=current_user
    )

    return project


# ==================== Update Project ====================

@router.patch("/{project_id}", response_model=ProjectPublic)
def update_project(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    project_id: UUID,
    project_in: ProjectUpdate,
) -> Any:
    """
    Update a project.

    **Updatable fields:**
    - name
    - description
    - type
    - status
    - project_url
    - api_key_id (switch API key with validation)

    **Validation:**
    - New API key must be owned by user
    - New API key must be active
    - New API key cannot be linked to another project
    - New name must be unique (if changed)
    - New URL must be valid (if changed)

    **RBAC:**
    - `user`: Can update projects they own
    - `org_super_admin`: Can update projects in their organization

    **Returns:**
    - Updated project

    **Errors:**
    - 404: Project not found
    - 403: Not authorized to update this project
    - 400: Validation failed
    """
    # Get project
    project = session.get(Project, project_id)

    if not project or project.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )

    try:
        updated_project = project_service.update_project(
            session=session,
            project=project,
            project_in=project_in,
            user=current_user
        )

        return updated_project

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to update project: {str(e)}"
        )


# ==================== Delete Project ====================

@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    project_id: UUID,
    hard_delete: bool = Query(False, description="Permanently delete (default: soft delete)"),
) -> None:
    """
    Delete a project.

    **Delete behavior:**
    - Default: Soft delete (project marked as deleted, can be restored)
    - Hard delete: Permanently removes project and all related data

    **RBAC:**
    - Only the project **owner** can delete it
    - `org_super_admin` cannot delete projects they don't own

    **Returns:**
    - 204 No Content on success

    **Errors:**
    - 404: Project not found
    - 403: Only the project owner can delete it
    """
    # Get project
    project = session.get(Project, project_id)

    if not project or project.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )

    try:
        project_service.delete_project(
            session=session,
            project=project,
            user=current_user,
            soft_delete=not hard_delete
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting project {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete project: {str(e)}"
        )


# ==================== Get Project Usage ====================

@router.get("/{project_id}/usage", response_model=ProjectUsageResponse)
def get_project_usage(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    project_id: UUID,
    start_date: str | None = Query(None, description="Start date (YYYY-MM-DD), default: 30 days ago"),
    end_date: str | None = Query(None, description="End date (YYYY-MM-DD), default: today"),
    page: int = Query(1, ge=1, description="Page number for recent calls"),
    page_size: int = Query(50, ge=1, le=100, description="Page size for recent calls"),
) -> Any:
    """
    Get comprehensive usage analytics for a project.

    **Date range:**
    - Default: Last 30 days
    - Maximum: 365 days
    - Format: YYYY-MM-DD

    **Returns:**

    ### A. Metrics Summary
    - `total_calls`: Total API requests
    - `total_tokens`: Total tokens consumed
    - `total_cost`: Total cost in USD
    - `avg_response_time_ms`: Average response time (ms)
    - `success_rate`: Percentage of successful requests

    ### B. Usage Trends (Daily)
    - `date`: Date (YYYY-MM-DD)
    - `api_calls`: Number of API calls that day
    - `tokens_consumed`: Tokens used that day
    - `cost`: Cost for that day

    ### C. Recent API Calls
    - Latest 50 API calls with full details
    - Includes timestamp, model, endpoint, tokens, cost, status

    **RBAC:**
    - `user`: Can see usage for projects they own
    - `org_super_admin`: Can see usage for organization projects

    **Errors:**
    - 404: Project not found
    - 403: Not authorized to access this project
    - 400: Invalid date range
    """
    # Get project
    project = session.get(Project, project_id)

    if not project or project.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Project with ID {project_id} not found"
        )

    # Parse dates
    try:
        if end_date:
            end_dt = datetime.fromisoformat(end_date).replace(
                hour=23, minute=59, second=59, tzinfo=timezone.utc
            )
        else:
            end_dt = datetime.now(timezone.utc)

        if start_date:
            start_dt = datetime.fromisoformat(start_date).replace(
                hour=0, minute=0, second=0, tzinfo=timezone.utc
            )
        else:
            start_dt = end_dt - timedelta(days=30)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid date format. Use YYYY-MM-DD. Error: {str(e)}"
        )

    # Validate date range
    if start_dt >= end_dt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date must be before end date"
        )

    if (end_dt - start_dt).days > 365:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Date range cannot exceed 365 days"
        )

    # Get usage data
    try:
        usage_data = project_service.get_project_usage(
            session=session,
            project=project,
            user=current_user,
            start_date=start_dt,
            end_date=end_dt,
            page=page,
            page_size=page_size
        )

        return usage_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting project usage for {project_id}: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get project usage: {str(e)}"
        )
