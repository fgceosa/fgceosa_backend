import uuid
from typing import Any
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Query, Response, HTTPException
from sqlmodel import func, select
import csv
import io

from app.api.deps import (
    SessionDep,
    RequiresPermission,
    CurrentUser,
)
from app.models import (
    AuditLog,
    AuditLogPublic,
    AuditLogListResponse,
    AuditLogStats,
)

router = APIRouter(prefix="/audit-logs", tags=["audit-logs"])

@router.get("", response_model=AuditLogListResponse, dependencies=[Depends(RequiresPermission("system:view_audit_logs"))], response_model_by_alias=True)
def get_audit_logs(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    actor_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    action_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> Any:
    """Retrieve audit logs with filtering and pagination."""
    # Security: If not superuser, restrict to own organization
    if not current_user.is_superuser:
        from app.models import OrganizationMember
        org_member = session.exec(select(OrganizationMember).where(OrganizationMember.user_id == current_user.id)).first()
        if not org_member:
            raise HTTPException(status_code=403, detail="Access denied: User is not part of an organization")
        
        # Override or restrict organization_id
        organization_id = org_member.organization_id
    
    statement = select(AuditLog)
    
    if search:
        search_filter = f"%{search}%"
        statement = statement.where(
            (AuditLog.actor_name.ilike(search_filter)) |
            (AuditLog.actor_role.ilike(search_filter)) |
            (AuditLog.action.ilike(search_filter)) |
            (AuditLog.target_id.ilike(search_filter)) |
            (AuditLog.ip_address.ilike(search_filter)) |
            (AuditLog.location.ilike(search_filter))
        )
    
    if actor_id:
        statement = statement.where(AuditLog.actor_id == actor_id)
    if organization_id:
        statement = statement.where(AuditLog.organization_id == organization_id)
    if action_type:
        statement = statement.where(AuditLog.action == action_type)
    if severity:
        statement = statement.where(AuditLog.severity == severity)
    if status:
        statement = statement.where(AuditLog.status == status)
    if start_date:
        statement = statement.where(AuditLog.timestamp >= start_date)
    if end_date:
        statement = statement.where(AuditLog.timestamp <= end_date)
    
    # Sort by timestamp descending
    statement = statement.order_by(AuditLog.timestamp.desc())
    
    # Total count
    count_statement = select(func.count()).select_from(statement.subquery())
    total = session.exec(count_statement).one()
    
    # Pagination
    skip = (page - 1) * page_size
    logs = session.exec(statement.offset(skip).limit(page_size)).all()
    
    return AuditLogListResponse(logs=logs, total=total)

@router.get("/stats", response_model=AuditLogStats, dependencies=[Depends(RequiresPermission("platform:view_audit_logs"))], response_model_by_alias=True)
def get_audit_stats(
    session: SessionDep,
    range: str = Query("24h", pattern="^(24h|7d|30d)$")
) -> Any:
    """Get summarized audit statistics for the dashboard."""
    now = datetime.now(timezone.utc)
    if range == "24h":
        start_time = now - timedelta(hours=24)
    elif range == "7d":
        start_time = now - timedelta(days=7)
    else:
        start_time = now - timedelta(days=30)
        
    def safe_count(stmt):
        return session.exec(stmt).one() or 0

    total_events = safe_count(
        select(func.count()).select_from(AuditLog).where(AuditLog.timestamp >= start_time)
    )
    
    critical_actions = safe_count(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.timestamp >= start_time,
            AuditLog.severity == 'critical'
        )
    )
    
    admin_actions = safe_count(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.timestamp >= start_time,
            AuditLog.actor_role.in_(['Platform Super Admin', 'Org Admin'])
        )
    )
    
    security_sensitive = safe_count(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.timestamp >= start_time,
            AuditLog.action_category.in_(['access_control', 'security'])
        )
    )
    
    failed_actions = safe_count(
        select(func.count()).select_from(AuditLog).where(
            AuditLog.timestamp >= start_time,
            AuditLog.status == 'failed'
        )
    )

    return AuditLogStats(
        totalEvents=total_events,
        criticalActions=critical_actions,
        adminActions=admin_actions,
        securitySensitive=security_sensitive,
        failedActions=failed_actions
    )

@router.get("/export", dependencies=[Depends(RequiresPermission("platform:view_audit_logs"))])
def export_audit_logs(
    session: SessionDep,
    search: str | None = None,
    actor_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    action_type: str | None = None,
    severity: str | None = None,
    status: str | None = None,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> Response:
    """Export audit logs as CSV."""
    statement = select(AuditLog)
    
    if search:
        search_filter = f"%{search}%"
        statement = statement.where(
            (AuditLog.actor_name.ilike(search_filter)) |
            (AuditLog.action.ilike(search_filter)) |
            (AuditLog.target_id.ilike(search_filter)) |
            (AuditLog.ip_address.ilike(search_filter))
        )
    
    if actor_id:
        statement = statement.where(AuditLog.actor_id == actor_id)
    if organization_id:
        statement = statement.where(AuditLog.organization_id == organization_id)
    if action_type:
        statement = statement.where(AuditLog.action == action_type)
    if severity:
        statement = statement.where(AuditLog.severity == severity)
    if status:
        statement = statement.where(AuditLog.status == status)
    if start_date:
        statement = statement.where(AuditLog.timestamp >= start_date)
    if end_date:
        statement = statement.where(AuditLog.timestamp <= end_date)
    
    # Sort by timestamp descending
    statement = statement.order_by(AuditLog.timestamp.desc())
    
    # Limit to 10000 for safety, though typically exports might need more
    # For now, let's just get all that match filters
    logs = session.exec(statement).all()
    
    # Create CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Timestamp (UTC)", "Actor Name", "Actor Role", "Action", 
        "Target Type", "Target ID", "Severity", "Status", 
        "IP Address", "Location", "User Agent"
    ])
    
    # Write log entries
    for log in logs:
        writer.writerow([
            log.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            log.actor_name,
            log.actor_role,
            log.action,
            log.target_type,
            log.target_id,
            log.severity,
            log.status,
            log.ip_address,
            log.location,
            log.user_agent
        ])
    
    csv_content = output.getvalue()
    output.close()
    
    filename = f"audit_logs_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

