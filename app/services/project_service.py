"""
Project Service Layer

Contains business logic for project management, validation, and usage analytics.
Enforces RBAC and authorization rules.
"""
import uuid
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any
from collections import defaultdict

from fastapi import HTTPException, status
from sqlmodel import Session, select, func, col, and_, or_
from validators import url as validate_url

from app.models import (
    Project,
    ProjectCreate,
    ProjectUpdate,
    ProjectPublic,
    ProjectWithUsage,
    APIKey,
    APIRequest,
    User,
    Organization,
    OrganizationMember,
    ProjectType,
    ProjectStatus,
    UsageMetricsSummary,
    UsageTrendData,
    RecentAPICall,
    ProjectUsageResponse,
    ProjectCreated,
)
from app.services import api_key_service

logger = logging.getLogger(__name__)


# ==================== Authorization Helpers ====================

def check_project_access(
    *,
    session: Session,
    project: Project,
    user: User,
    require_owner: bool = False
) -> None:
    """
    Check if user has access to a project.

    Rules:
    - User must be the owner, OR
    - User must be org_super_admin in the project's organization

    Args:
        session: Database session
        project: Project to check
        user: Current user
        require_owner: If True, only the owner can access

    Raises:
        HTTPException: If user doesn't have access
    """
    # Check if user is the owner
    if project.owner_user_id == user.id:
        return

    if require_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the project owner can perform this action"
        )

    # Check org_super_admin role
    if project.org_id:
        stmt = select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == project.org_id,
                OrganizationMember.user_id == user.id,
                OrganizationMember.role == "org_super_admin"
            )
        )
        org_member = session.exec(stmt).first()

        if org_member:
            return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You don't have permission to access this project"
    )


def validate_org_membership(
    *,
    session: Session,
    org_id: uuid.UUID,
    user_id: uuid.UUID
) -> OrganizationMember:
    """
    Validate that user is a member of the organization.

    Args:
        session: Database session
        org_id: Organization ID
        user_id: User ID

    Returns:
        OrganizationMember object

    Raises:
        HTTPException: If user is not a member
    """
    stmt = select(OrganizationMember).where(
        and_(
            OrganizationMember.organization_id == org_id,
            OrganizationMember.user_id == user_id
        )
    )
    member = session.exec(stmt).first()

    if not member:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a member of this organization"
        )

    return member


# ==================== Validation ====================

def validate_api_key(
    *,
    session: Session,
    api_key_id: uuid.UUID,
    user_id: uuid.UUID,
    project_id: uuid.UUID | None = None
) -> APIKey:
    """
    Validate API key and ownership.

    Checks:
    1. API key exists
    2. User owns the API key
    3. API key is active
    4. API key is not already linked to another project

    Args:
        session: Database session
        api_key_id: API key ID to validate
        user_id: User ID for ownership check
        project_id: Current project ID (to allow relinking same key)

    Returns:
        APIKey object

    Raises:
        HTTPException: If validation fails
    """
    # Get API key
    api_key = session.get(APIKey, api_key_id)

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"API key with ID {api_key_id} not found"
        )

    # Check ownership
    if api_key.user_id != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't own this API key"
        )

    # Check if active
    if not api_key.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="API key is not active. Only active API keys can be linked to projects"
        )

    # Check if already linked to another project
    stmt = select(Project).where(
        and_(
            Project.api_key_id == api_key_id,
            Project.is_deleted == False,
            Project.id != project_id if project_id else True
        )
    )
    existing_project = session.exec(stmt).first()

    if existing_project:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"API key is already linked to project '{existing_project.name}'. "
                   "An API key can only be linked to one project at a time"
        )

    return api_key


def validate_project_name_unique(
    *,
    session: Session,
    name: str,
    user_id: uuid.UUID,
    org_id: uuid.UUID | None = None,
    exclude_project_id: uuid.UUID | None = None
) -> None:
    """
    Validate that project name is unique for user/org.

    Args:
        session: Database session
        name: Project name to check
        user_id: User ID
        org_id: Optional organization ID
        exclude_project_id: Project ID to exclude (for updates)

    Raises:
        HTTPException: If name already exists
    """
    # Build query
    conditions = [
        Project.name == name,
        Project.is_deleted == False
    ]

    # Scope to user or org
    if org_id:
        conditions.append(Project.org_id == org_id)
    else:
        conditions.append(
            and_(
                Project.owner_user_id == user_id,
                Project.org_id == None
            )
        )

    # Exclude current project (for updates)
    if exclude_project_id:
        conditions.append(Project.id != exclude_project_id)

    stmt = select(Project).where(and_(*conditions))
    existing = session.exec(stmt).first()

    if existing:
        scope = "organization" if org_id else "your account"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"A project with name '{name}' already exists in {scope}"
        )


def validate_project_url(url: str | None) -> None:
    """
    Validate project URL format.

    Args:
        url: URL to validate

    Raises:
        HTTPException: If URL is invalid
    """
    if url and not validate_url(url):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid project URL: {url}"
        )


# ==================== Project CRUD ====================

def create_project(
    *,
    session: Session,
    project_in: ProjectCreate,
    user: User
) -> ProjectCreated:
    """
    Create a new project.

    Validation:
    - API key ownership
    - API key is active
    - API key not linked to another project
    - Project name is unique
    - URL is valid
    - Org membership (if org_id provided)

    Args:
        session: Database session
        project_in: Project creation data
        user: Current user

    Returns:
        Created project

    Raises:
        HTTPException: If validation fails
    """
    # Validate organization membership if org_id provided
    if project_in.org_id:
        validate_org_membership(
            session=session,
            org_id=project_in.org_id,
            user_id=user.id
        )

    # Validate API key if provided, else generate new one
    plain_api_key = None
    api_key_id = project_in.api_key_id

    if api_key_id:
        validate_api_key(
            session=session,
            api_key_id=api_key_id,
            user_id=user.id
        )
    else:
        # Harmonization: Auto-generate API key for the project
        logger.info(f"No API key provided for project '{project_in.name}', generating new one")
        api_key_record, plain_api_key = api_key_service.create_api_key(
            session=session,
            user_id=user.id,
            name=f"Key for {project_in.name}"
        )
        api_key_id = api_key_record.id

    # Validate unique name
    validate_project_name_unique(
        session=session,
        name=project_in.name,
        user_id=user.id,
        org_id=project_in.org_id
    )

    # Validate URL
    validate_project_url(project_in.project_url)

    # Create project
    project = Project(
        name=project_in.name,
        description=project_in.description,
        type=project_in.type,
        status=project_in.status,
        project_url=project_in.project_url,
        owner_user_id=user.id,
        org_id=project_in.org_id,
        api_key_id=api_key_id,
        is_active=True,
        is_deleted=False
    )

    session.add(project)
    session.commit()
    session.refresh(project)

    logger.info(f"Created project {project.id} '{project.name}' for user {user.id}")

    # Return with plain key if it was newly created
    return ProjectCreated(
        **ProjectPublic.model_validate(project).model_dump(),
        plain_api_key=plain_api_key
    )


def update_project(
    *,
    session: Session,
    project: Project,
    project_in: ProjectUpdate,
    user: User
) -> Project:
    """
    Update an existing project.

    Args:
        session: Database session
        project: Project to update
        project_in: Update data
        user: Current user

    Returns:
        Updated project

    Raises:
        HTTPException: If validation fails
    """
    # Check access
    check_project_access(
        session=session,
        project=project,
        user=user
    )

    update_data = project_in.model_dump(exclude_unset=True)

    # Validate API key if changing
    if "api_key_id" in update_data and update_data["api_key_id"]:
        validate_api_key(
            session=session,
            api_key_id=update_data["api_key_id"],
            user_id=user.id,
            project_id=project.id
        )

    # Validate name uniqueness if changing
    if "name" in update_data and update_data["name"] != project.name:
        validate_project_name_unique(
            session=session,
            name=update_data["name"],
            user_id=user.id,
            org_id=project.org_id,
            exclude_project_id=project.id
        )

    # Validate URL if changing
    if "project_url" in update_data:
        validate_project_url(update_data["project_url"])

    # Update fields
    for field, value in update_data.items():
        setattr(project, field, value)

    project.updated_at = datetime.now(timezone.utc)

    session.add(project)
    session.commit()
    session.refresh(project)

    logger.info(f"Updated project {project.id} '{project.name}'")

    return project


def delete_project(
    *,
    session: Session,
    project: Project,
    user: User,
    soft_delete: bool = True
) -> None:
    """
    Delete a project (soft delete by default).

    Args:
        session: Database session
        project: Project to delete
        user: Current user
        soft_delete: If True, soft delete; if False, hard delete

    Raises:
        HTTPException: If validation fails
    """
    # Check access (owner only for delete)
    check_project_access(
        session=session,
        project=project,
        user=user,
        require_owner=True
    )

    if soft_delete:
        # Soft delete
        project.is_deleted = True
        project.deleted_at = datetime.now(timezone.utc)
        project.is_active = False
        session.add(project)
        session.commit()

        logger.info(f"Soft deleted project {project.id} '{project.name}'")
    else:
        # Hard delete
        session.delete(project)
        session.commit()

        logger.info(f"Hard deleted project {project.id} '{project.name}'")


def get_user_projects(
    *,
    session: Session,
    user: User,
    skip: int = 0,
    limit: int = 100,
    include_org_projects: bool = True
) -> tuple[list[ProjectPublic], int]:
    """
    Get projects for a user.

    Includes:
    - Projects owned by the user
    - Projects in orgs where user is org_super_admin (if include_org_projects=True)

    Args:
        session: Database session
        user: Current user
        skip: Pagination offset
        limit: Page size
        include_org_projects: Include org projects where user is admin

    Returns:
        Tuple of (projects list, total count)
    """
    # Base condition - non-deleted projects owned by user
    conditions = [
        Project.owner_user_id == user.id,
        Project.is_deleted == False
    ]

    # Add org projects if requested
    if include_org_projects:
        # Get orgs where user is super admin
        org_stmt = select(OrganizationMember.organization_id).where(
            and_(
                OrganizationMember.user_id == user.id,
                OrganizationMember.role == "org_super_admin"
            )
        )
        org_ids = session.exec(org_stmt).all()

        if org_ids:
            # Include projects from those orgs
            conditions = [
                or_(
                    and_(
                        Project.owner_user_id == user.id,
                        Project.is_deleted == False
                    ),
                    and_(
                        Project.org_id.in_(org_ids),
                        Project.is_deleted == False
                    )
                )
            ]

    # Count total
    count_stmt = select(func.count()).select_from(Project).where(*conditions)
    total = session.exec(count_stmt).one()

    # Get projects
    stmt = (
        select(Project)
        .where(*conditions)
        .order_by(col(Project.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    projects = session.exec(stmt).all()

    # Enrich with usage analytics
    if not projects:
        return [], total

    project_ids = [p.id for p in projects]
    usage_map = {}

    usage_stmt = (
        select(
            APIRequest.project_id,
            func.count(APIRequest.id),
            func.sum(APIRequest.total_tokens),
            func.sum(APIRequest.cost)
        )
        .where(APIRequest.project_id.in_(project_ids))
        .group_by(APIRequest.project_id)
    )
    usage_stats = session.exec(usage_stmt).all()
    
    for pid, count, tokens, cost in usage_stats:
        usage_map[pid] = {
            "total_requests": count,
            "total_tokens": tokens or 0,
            "total_cost": cost or Decimal("0.00")
        }

    results = []
    for p in projects:
        p_pub = ProjectPublic.model_validate(p)
        stats = usage_map.get(p.id, {})
        p_pub.total_requests = stats.get("total_requests", 0)
        p_pub.total_tokens = stats.get("total_tokens", 0)
        p_pub.total_cost = stats.get("total_cost", Decimal("0.00"))
        results.append(p_pub)

    return results, total


# ==================== Usage Analytics ====================

def compute_usage_metrics(
    *,
    session: Session,
    project_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime
) -> UsageMetricsSummary:
    """
    Compute usage metrics summary for a project.

    Metrics:
    - Total API calls
    - Total tokens
    - Total cost
    - Average response time
    - Success rate

    Args:
        session: Database session
        project_id: Project ID
        start_date: Start of date range
        end_date: End of date range

    Returns:
        UsageMetricsSummary
    """
    # Get all requests in date range
    stmt = select(APIRequest).where(
        and_(
            APIRequest.project_id == project_id,
            APIRequest.created_at >= start_date,
            APIRequest.created_at < end_date
        )
    )
    requests = session.exec(stmt).all()

    if not requests:
        return UsageMetricsSummary()

    total_calls = len(requests)
    total_tokens = sum(r.total_tokens for r in requests)
    total_cost = sum(r.cost for r in requests)

    # Calculate average response time (only successful requests)
    successful_requests = [r for r in requests if r.status == "success" and r.response_time_ms]
    avg_response_time = (
        sum(r.response_time_ms for r in successful_requests) / len(successful_requests)
        if successful_requests else 0.0
    )

    # Calculate success rate
    success_count = len([r for r in requests if r.status == "success"])
    success_rate = (success_count / total_calls * 100) if total_calls > 0 else 0.0

    return UsageMetricsSummary(
        total_calls=total_calls,
        total_tokens=total_tokens,
        total_cost=total_cost,
        avg_response_time_ms=round(avg_response_time, 2),
        success_rate=round(success_rate, 2)
    )


def compute_usage_trends(
    *,
    session: Session,
    project_id: uuid.UUID,
    start_date: datetime,
    end_date: datetime
) -> list[UsageTrendData]:
    """
    Compute daily usage trends.

    Groups requests by day and aggregates:
    - API calls per day
    - Tokens consumed per day
    - Cost per day

    Args:
        session: Database session
        project_id: Project ID
        start_date: Start of date range
        end_date: End of date range

    Returns:
        List of UsageTrendData (one per day)
    """
    # Get all requests in date range
    stmt = select(APIRequest).where(
        and_(
            APIRequest.project_id == project_id,
            APIRequest.created_at >= start_date,
            APIRequest.created_at < end_date
        )
    ).order_by(APIRequest.created_at)

    requests = session.exec(stmt).all()

    # Group by date
    daily_data = defaultdict(lambda: {
        "api_calls": 0,
        "tokens_consumed": 0,
        "cost": Decimal("0.00")
    })

    for request in requests:
        date_key = request.created_at.date().isoformat()
        daily_data[date_key]["api_calls"] += 1
        daily_data[date_key]["tokens_consumed"] += request.total_tokens
        daily_data[date_key]["cost"] += request.cost

    # Convert to list and sort
    trends = [
        UsageTrendData(
            date=date,
            api_calls=data["api_calls"],
            tokens_consumed=data["tokens_consumed"],
            cost=data["cost"]
        )
        for date, data in sorted(daily_data.items())
    ]

    return trends


def get_recent_api_calls(
    *,
    session: Session,
    project_id: uuid.UUID,
    limit: int = 50,
    skip: int = 0
) -> tuple[list[RecentAPICall], int]:
    """
    Get recent API calls for a project with pagination.

    Args:
        session: Database session
        project_id: Project ID
        limit: Maximum number of calls to return
        skip: Number of calls to skip

    Returns:
        Tuple of (List of RecentAPICall, Total count)
    """
    # Count total requests for this project
    count_stmt = select(func.count()).select_from(APIRequest).where(APIRequest.project_id == project_id)
    total = session.exec(count_stmt).one()

    # Get paginated requests
    stmt = (
        select(APIRequest)
        .where(APIRequest.project_id == project_id)
        .order_by(col(APIRequest.created_at).desc())
        .offset(skip)
        .limit(limit)
    )

    requests = session.exec(stmt).all()

    calls = [
        RecentAPICall(
            id=r.id,
            timestamp=r.created_at,
            model=r.model,
            endpoint=r.endpoint,
            total_tokens=r.total_tokens,
            cost=r.cost,
            status=r.status,
            response_time_ms=r.response_time_ms
        )
        for r in requests
    ]
    
    return calls, total


def get_project_usage(
    *,
    session: Session,
    project: Project,
    user: User,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    page: int = 1,
    page_size: int = 50
) -> ProjectUsageResponse:
    """
    Get complete usage analytics for a project.

    Args:
        session: Database session
        project: Project to analyze
        user: Current user
        start_date: Optional start date (default: 30 days ago)
        end_date: Optional end date (default: now)
        page: Page number for recent calls (default: 1)
        page_size: Page size for recent calls (default: 50)

    Returns:
        ProjectUsageResponse with all analytics

    Raises:
        HTTPException: If user doesn't have access
    """
    # Check access
    check_project_access(
        session=session,
        project=project,
        user=user
    )

    # Default date range: last 30 days
    if not end_date:
        end_date = datetime.now(timezone.utc)
    if not start_date:
        start_date = end_date - timedelta(days=30)

    # Compute metrics
    metrics_summary = compute_usage_metrics(
        session=session,
        project_id=project.id,
        start_date=start_date,
        end_date=end_date
    )

    # Compute trends
    usage_trends = compute_usage_trends(
        session=session,
        project_id=project.id,
        start_date=start_date,
        end_date=end_date
    )

    # Get recent calls with pagination
    skip = (page - 1) * page_size
    recent_calls, total_calls = get_recent_api_calls(
        session=session,
        project_id=project.id,
        limit=page_size,
        skip=skip
    )

    return ProjectUsageResponse(
        project=ProjectPublic.model_validate(project),
        date_range={
            "start": start_date.date().isoformat(),
            "end": end_date.date().isoformat()
        },
        metrics_summary=metrics_summary,
        usage_trends=usage_trends,
        recent_calls=recent_calls,
        total_recent_calls=total_calls,
        page=page,
        page_size=page_size
    )
