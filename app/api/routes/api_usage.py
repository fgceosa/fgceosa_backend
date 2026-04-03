"""
API Usage/Requests Routes

Handles API usage tracking and statistics
"""

from typing import Any
from uuid import UUID
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func, and_

from app.api import deps
from app.models import User, APIRequest, APIRequestPublic, APIRequestsPublic, Project
from app.services.project_service import check_project_access
from pydantic import BaseModel


class APIUsageStats(BaseModel):
    """API usage statistics"""
    total_requests: int
    total_tokens: int
    total_cost: float
    successful_requests: int
    failed_requests: int
    average_response_time: float | None


router = APIRouter(prefix="/api-usage", tags=["api-usage"])


@router.get("/requests", response_model=APIRequestsPublic)
def get_api_requests(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    project_id: UUID | None = Query(None, description="Filter by project"),
    organization_id: UUID | None = Query(None, description="Filter by organization"),
    model: str | None = Query(None, description="Filter by model"),
    status: str | None = Query(None, description="Filter by status"),
) -> Any:
    # Build base query
    query = select(APIRequest)
    
    # Filtering logic
    if project_id:
        # 1. Verify project access
        project = session.get(Project, project_id)
        if not project:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Project not found")
            
        check_project_access(session=session, project=project, user=current_user)
        
        # 2. Filter by project (shows all usage for this project)
        query = query.where(APIRequest.project_id == project_id)
    elif organization_id:
        # 3. Filter by organization (requires org access check)
        # For now, just filter by org_id if user is member
        from app.models import OrganizationMember
        member_stmt = select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == current_user.id
            )
        )
        member = session.exec(member_stmt).first()
        if not member:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Not an organization member")
            
        query = query.where(APIRequest.organization_id == organization_id)
    else:
        # 4. Default: Filter by current user across all projects
        query = query.where(APIRequest.user_id == current_user.id)

    # Add other filters
    if model:
        query = query.where(APIRequest.model == model)
    if status:
        query = query.where(APIRequest.status == status)

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.exec(count_query).one()

    # Apply pagination and ordering
    query = query.order_by(APIRequest.created_at.desc()).offset((page - 1) * page_size).limit(page_size)  # type: ignore

    # Execute query
    requests = session.exec(query).all()

    return APIRequestsPublic(data=list(requests), count=total)


@router.get("/stats", response_model=APIUsageStats)
def get_api_usage_stats(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    project_id: UUID | None = Query(None, description="Filter by project"),
    organization_id: UUID | None = Query(None, description="Filter by organization"),
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
) -> Any:
    """
    Get API usage statistics for the current user.
    """
    # Build filters
    start_date = datetime.now(timezone.utc) - timedelta(days=days)
    conditions = [APIRequest.created_at >= start_date]

    if project_id:
        # Verify project access
        project = session.get(Project, project_id)
        if not project:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail="Project not found")
        check_project_access(session=session, project=project, user=current_user)
        
        conditions.append(APIRequest.project_id == project_id)
    elif organization_id:
        # Verify org access
        from app.models import OrganizationMember
        member_stmt = select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == current_user.id
            )
        )
        member = session.exec(member_stmt).first()
        if not member:
            from fastapi import HTTPException
            raise HTTPException(status_code=403, detail="Not an organization member")
            
        conditions.append(APIRequest.organization_id == organization_id)
    else:
        conditions.append(APIRequest.user_id == current_user.id)

    query_filter = and_(*conditions)

    # Get total requests
    total_requests = session.exec(
        select(func.count(APIRequest.id)).where(query_filter)
    ).one()

    # Get total tokens
    total_tokens_result = session.exec(
        select(func.sum(APIRequest.total_tokens)).where(query_filter)
    ).one()
    total_tokens = total_tokens_result or 0

    # Get total cost
    total_cost_result = session.exec(
        select(func.sum(APIRequest.cost)).where(query_filter)
    ).one()
    total_cost = float(total_cost_result or 0)

    # Get successful requests
    successful_requests = session.exec(
        select(func.count(APIRequest.id)).where(
            and_(query_filter, APIRequest.status == "success")
        )
    ).one()

    # Get failed requests
    failed_requests = total_requests - successful_requests

    # Get average response time
    avg_response_time_result = session.exec(
        select(func.avg(APIRequest.response_time_ms)).where(
            and_(query_filter, APIRequest.response_time_ms.isnot(None))  # type: ignore
        )
    ).one()
    avg_response_time = float(avg_response_time_result) if avg_response_time_result else None

    return APIUsageStats(
        total_requests=total_requests,
        total_tokens=total_tokens,
        total_cost=round(total_cost, 4),
        successful_requests=successful_requests,
        failed_requests=failed_requests,
        average_response_time=round(avg_response_time, 2) if avg_response_time else None,
    )
