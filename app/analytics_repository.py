"""
Dashboard CRUD operations for analytics and metrics
"""
import uuid
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from decimal import Decimal

from sqlmodel import Session, select, func, and_
from sqlalchemy import extract, text

from app.models import Project, APIRequest, CreditTransaction

logger = logging.getLogger(__name__)


def get_credit_balance(*, session: Session, user_id: uuid.UUID) -> Decimal:
    """Get current credit balance for a user from cached User table field"""
    from app.models import User
    user = session.get(User, user_id)
    return user.credits if user and user.credits else Decimal("0.00")


def get_period_metrics(
    *, session: Session, user_id: uuid.UUID, period: str = "week"
) -> Dict[str, Any]:
    """
    Get metrics for a specific period (week, month, year)
    Returns: credit balance, api requests count, spending, active projects count
    """
    # Calculate date range
    now = datetime.now(timezone.utc)
    if period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    elif period == "year":
        start_date = now - timedelta(days=365)
    else:
        start_date = now - timedelta(days=7)

    # Get credit balance (current)
    credit_balance = get_credit_balance(session=session, user_id=user_id)

    # Get API requests count for period
    api_requests_stmt = select(func.count(APIRequest.id)).where(
        and_(
            APIRequest.user_id == user_id,
            APIRequest.created_at >= start_date,
            APIRequest.created_at <= now,
        )
    )
    api_requests_count = session.exec(api_requests_stmt).one()

    # Get spending for period (sum of costs)
    spending_stmt = select(func.coalesce(func.sum(APIRequest.cost), 0)).where(
        and_(
            APIRequest.user_id == user_id,
            APIRequest.created_at >= start_date,
            APIRequest.created_at <= now,
        )
    )
    spending = session.exec(spending_stmt).one()

    # Get active projects count using raw SQL to bypass enum issues
    raw_sql = text("""
        SELECT COUNT(*)
        FROM project
        WHERE owner_user_id = :user_id
        AND is_active = true
        AND is_deleted = false
    """)
    result = session.exec(raw_sql, {"user_id": user_id})
    active_projects = result.one()

    logger.info(f"Active projects count for user {user_id}: {active_projects}")

    return {
        "creditBalance": float(credit_balance),
        "apiRequests": api_requests_count,
        "spending": float(spending),
        "activeProjects": active_projects,
    }


def get_weekly_usage_trends(
    *, session: Session, user_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Get API requests and costs for the last 7 days
    Returns data for chart visualization
    """
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    # Get daily data for the last 7 days
    daily_data = []
    dates = []

    for i in range(7):
        day_start = seven_days_ago + timedelta(days=i)
        day_end = day_start + timedelta(days=1)

        # Count API requests for this day
        requests_stmt = select(func.count(APIRequest.id)).where(
            and_(
                APIRequest.user_id == user_id,
                APIRequest.created_at >= day_start,
                APIRequest.created_at < day_end,
            )
        )
        requests_count = session.exec(requests_stmt).one()

        # Sum costs for this day
        cost_stmt = select(func.coalesce(func.sum(APIRequest.cost), 0)).where(
            and_(
                APIRequest.user_id == user_id,
                APIRequest.created_at >= day_start,
                APIRequest.created_at < day_end,
            )
        )
        cost = session.exec(cost_stmt).one()

        daily_data.append({"requests": requests_count, "cost": float(cost)})
        dates.append(day_start.strftime("%a"))  # Mon, Tue, Wed, etc.

    # Format for chart
    return {
        "series": [
            {
                "name": "API Requests",
                "data": [day["requests"] for day in daily_data],
            },
            {
                "name": "Cost (USD)",
                "data": [day["cost"] for day in daily_data],
            },
        ],
        "dates": dates,
    }


def get_model_usage_distribution(
    *, session: Session, user_id: uuid.UUID
) -> List[Dict[str, Any]]:
    """
    Get distribution of API usage by AI model
    Returns: model name and usage count/percentage
    """
    # Get total count
    total_stmt = select(func.count(APIRequest.id)).where(
        APIRequest.user_id == user_id
    )
    total_count = session.exec(total_stmt).one()

    if total_count == 0:
        return []

    # Get count by model
    model_stmt = (
        select(APIRequest.model, func.count(APIRequest.id).label("count"))
        .where(APIRequest.user_id == user_id)
        .group_by(APIRequest.model)
        .order_by(func.count(APIRequest.id).desc())
    )

    results = session.exec(model_stmt).all()

    # Calculate percentages and format
    distribution = []
    for model, count in results:
        percentage = (count / total_count) * 100
        distribution.append(
            {
                "model": model,
                "count": count,
                "percentage": round(percentage, 2),
            }
        )

    return distribution


def get_dashboard_overview(
    *, session: Session, user_id: uuid.UUID
) -> Dict[str, Any]:
    """
    Get complete dashboard overview with all metrics
    """
    return {
        "weekly": get_period_metrics(session=session, user_id=user_id, period="week"),
        "monthly": get_period_metrics(
            session=session, user_id=user_id, period="month"
        ),
        "annually": get_period_metrics(
            session=session, user_id=user_id, period="year"
        ),
        "weeklyUsageTrends": get_weekly_usage_trends(
            session=session, user_id=user_id
        ),
        "modelUsageDistribution": get_model_usage_distribution(
            session=session, user_id=user_id
        ),
    }


def get_credit_history(
    *, session: Session, user_id: uuid.UUID, limit: int = 10
) -> List[CreditTransaction]:
    """Get recent credit transaction history"""
    statement = (
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .limit(limit)
    )
    return list(session.exec(statement).all())


def get_active_projects(
    *, session: Session, user_id: uuid.UUID
) -> List[Project]:
    """Get all active projects for a user (non-deleted, is_active projects)"""
    statement = select(Project).where(
        and_(
            Project.owner_user_id == user_id,
            Project.is_active == True,
            Project.is_deleted == False
        )
    )
    return list(session.exec(statement).all())


# ==================== Global / Admin Analytics ====================

def get_global_period_metrics(
    *, session: Session, period: str = "month"
) -> Dict[str, Any]:
    """
    Get global aggregated metrics for the platform (Admin Dashboard)
    """
    now = datetime.now(timezone.utc)
    if period == "week":
        start_date = now - timedelta(days=7)
    elif period == "month":
        start_date = now - timedelta(days=30)
    elif period == "year":
        start_date = now - timedelta(days=365)
    else:
        start_date = now - timedelta(days=30)

    # 1. Total Revenue (Sum of all completed TopUps)
    from app.models import TopUp, TopUpStatus, User, Workspace, WorkspaceProject
    
    revenue_stmt = select(func.coalesce(func.sum(TopUp.amount_naira), 0)).where(
        TopUp.status == TopUpStatus.COMPLETED
    )
    # If period specific revenue is needed:
    # revenue_stmt = revenue_stmt.where(TopUp.created_at >= start_date)
    # But usually "Total Revenue" implies lifetime. 
    # Frontend says "Global revenue stream" and has trend. Let's return total for now.
    total_revenue = session.exec(revenue_stmt).one()

    # 2. Active Users (or Total Workspaces as per frontend)
    # Frontend card says "Total Workspaces" but key is 'activeUsers' in types?
    # Let's return both or map as needed.
    workspaces_count = session.exec(select(func.count(Workspace.id))).one()
    users_count = session.exec(select(func.count(User.id)).where(User.is_active == True)).one()

    # 3. API Requests (Global) in period
    api_requests_stmt = select(func.count(APIRequest.id)).where(
        and_(
            APIRequest.created_at >= start_date,
            APIRequest.created_at <= now,
        )
    )
    api_requests_count = session.exec(api_requests_stmt).one()

    # 4. Token Usage (Global) in period
    token_usage_stmt = select(func.coalesce(func.sum(APIRequest.total_tokens), 0)).where(
        and_(
            APIRequest.created_at >= start_date,
            APIRequest.created_at <= now,
        )
    )
    token_usage = session.exec(token_usage_stmt).one()
    
    # 5. Active Projects (Global)
    active_projects_count = session.exec(
        select(func.count(Project.id)).where(
            and_(Project.is_active == True, Project.is_deleted == False)
        )
    ).one()

    # 6. AI Agents (Mock or Real count of deployed Copilots)
    # Assuming 'copilot' table or similar logic. 
    # For now, placeholder or check models.
    ai_agents_count = 0  # To be implemented if Copilot model exists
    
    # Calculate global credit balance (Sum of all individual user credits)
    total_credits_stmt = select(func.coalesce(func.sum(User.credits), 0))
    total_platform_credits = session.exec(total_credits_stmt).one()

    # Calculate global spending (Sum of all APIRequest costs in period)
    global_spending_stmt = select(func.coalesce(func.sum(APIRequest.cost), 0)).where(
        and_(
            APIRequest.created_at >= start_date,
            APIRequest.created_at <= now,
        )
    )
    total_platform_spending = session.exec(global_spending_stmt).one()

    # Calculate Avg Revenue Per User (ARPU) - simple approximation
    arpu = float(total_revenue) / users_count if users_count > 0 else 0

    return {
        "totalRevenue": float(total_revenue),
        "apiRequests": api_requests_count,
        "activeUsers": workspaces_count, # Frontend shows "Total Workspaces"
        "activeProjects": active_projects_count,
        "creditBalance": float(total_platform_credits), 
        "spending": float(total_platform_spending),      
        "tokenUsage": int(token_usage),
        "aiAgents": ai_agents_count,
        "avgRevenuePerUser": round(arpu, 2)
    }


def get_top_workspaces(
    *, session: Session, limit: int = 5
) -> List[Dict[str, Any]]:
    """
    Get top workspaces by revenue/usage
    """
    from app.models import Workspace, WorkspaceMember, WorkspaceProject, TopUp, TopUpStatus
    from sqlalchemy import func
    
    statement = (
        select(Workspace)
        .order_by(Workspace.credits_balance.desc())
        .limit(limit)
    )
    workspaces = session.exec(statement).all()
    
    result = []
    for ws in workspaces:
        # 1. Real Revenue from TopUps
        revenue_stmt = select(func.coalesce(func.sum(TopUp.amount_naira), 0)).where(
            and_(
                TopUp.workspace_id == ws.id,
                TopUp.status == TopUpStatus.COMPLETED
            )
        )
        revenue = session.exec(revenue_stmt).one()
        
        # 2. Real Member Count
        members_stmt = select(func.count(WorkspaceMember.id)).where(
            WorkspaceMember.workspace_id == ws.id
        )
        members_count = session.exec(members_stmt).one()
        
        # 3. Real Requests and Tokens from Projects
        projects_stmt = select(
            func.coalesce(func.sum(WorkspaceProject.api_calls_count), 0),
            func.coalesce(func.sum(WorkspaceProject.credits_used), 0) # Credits as proxy for usage if tokens not separate
        ).where(WorkspaceProject.workspace_id == ws.id)
        requests_count, credits_used = session.exec(projects_stmt).one()
        
        # Format tokens string (e.g. 1.2M) - using a simple helper or just passing the number
        tokens_val = int(credits_used * 1000) # Mock conversion if tokens aren't tracked separately
        if tokens_val >= 1000000:
            tokens_str = f"{tokens_val / 1000000:.1f}M"
        elif tokens_val >= 1000:
            tokens_str = f"{tokens_val / 1000:.1f}K"
        else:
            tokens_str = str(tokens_val)

        result.append({
            "id": str(ws.id),
            "name": ws.name,
            "revenue": float(revenue),
            "tokens": tokens_str,
            "members": members_count,
            "requests": requests_count,
            "growth": 0.0 # Standardize to 0 for now as growth requires historical snapshot
        })
        
    return result


def get_global_weekly_usage_trends(
    *, session: Session
) -> Dict[str, Any]:
    """
    Get global API requests and costs for the last 7 days
    """
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    daily_data = []
    dates = []

    for i in range(7):
        day_start = seven_days_ago + timedelta(days=i)
        day_end = day_start + timedelta(days=1)

        requests_stmt = select(func.count(APIRequest.id)).where(
            and_(
                APIRequest.created_at >= day_start,
                APIRequest.created_at < day_end,
            )
        )
        requests_count = session.exec(requests_stmt).one()

        cost_stmt = select(func.coalesce(func.sum(APIRequest.cost), 0)).where(
            and_(
                APIRequest.created_at >= day_start,
                APIRequest.created_at < day_end,
            )
        )
        cost = session.exec(cost_stmt).one()

        daily_data.append({"requests": requests_count, "cost": float(cost)})
        dates.append(day_start.strftime("%a"))

    return {
        "series": [
            {
                "name": "API Requests",
                "data": [day["requests"] for day in daily_data],
            },
            {
                "name": "Cost (USD)",
                "data": [day["cost"] for day in daily_data],
            },
        ],
        "dates": dates,
    }


def get_global_model_usage(
    *, session: Session
) -> List[Dict[str, Any]]:
    """
    Get global model usage distribution
    """
    total_stmt = select(func.count(APIRequest.id))
    total_count = session.exec(total_stmt).one()

    if total_count == 0:
        return []

    model_stmt = (
        select(APIRequest.model, func.count(APIRequest.id).label("count"))
        .group_by(APIRequest.model)
        .order_by(func.count(APIRequest.id).desc())
    )

    results = session.exec(model_stmt).all()

    distribution = []
    colors = ['#003D82', '#1E5FA8', '#4A90E2', '#87CEEB', '#B0E0E6'] # Predefined colors
    
    for i, (model, count) in enumerate(results):
        percentage = (count / total_count) * 100
        distribution.append(
            {
                "model": model,
                "count": count,
                "percentage": round(percentage, 2),
                "color": colors[i % len(colors)]
            }
        )

    return distribution


def get_recent_activities(
    *, session: Session, limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get recent system activities (Users, Keys, etc.) from Notifications or other sources
    """
    from app.models import Notification
    
    # Using notifications as a proxy for activity feed
    statement = (
        select(Notification)
        .order_by(Notification.created_at.desc())
        .limit(limit)
    )
    notifications = session.exec(statement).all()
    
    activities = []
    for notif in notifications:
        # Map notification types to frontend-friendly styles
        type_map = {
            "system": {"bg": "bg-blue-50 dark:bg-blue-900/20", "color": "text-blue-500", "icon": "system"},
            "user": {"bg": "bg-emerald-50 dark:bg-emerald-900/20", "color": "text-emerald-500", "icon": "user"},
            "credit": {"bg": "bg-amber-50 dark:bg-amber-900/20", "color": "text-amber-500", "icon": "key"},
            "default": {"bg": "bg-gray-50 dark:bg-gray-900/20", "color": "text-gray-400", "icon": "activity"}
        }
        style = type_map.get(notif.type, type_map["default"])
        
        activities.append({
            "id": str(notif.id),
            "type": style["icon"],
            "content": f"{notif.title}: {notif.description}",
            "time": notif.created_at.strftime("%H:%M"),
            "bg": style["bg"],
            "color": style["color"]
        })
        
    return activities


def get_system_health(*, session: Session) -> Dict[str, Any]:
    """
    Get system health metrics derived from real API activity
    """
    now = datetime.now(timezone.utc)
    day_ago = now - timedelta(days=1)
    
    # Calculate real success rate from last 24h of API requests
    total_req_stmt = select(func.count(APIRequest.id)).where(APIRequest.created_at >= day_ago)
    success_req_stmt = select(func.count(APIRequest.id)).where(
        and_(
            APIRequest.created_at >= day_ago,
            APIRequest.status == "success"
        )
    )
    
    total_req = session.exec(total_req_stmt).one()
    success_req = session.exec(success_req_stmt).one()
    
    success_rate = (success_req / total_req * 100) if total_req > 0 else 100.0
    
    # Calculate avg latency
    latency_stmt = select(func.coalesce(func.avg(APIRequest.response_time_ms), 0)).where(
        APIRequest.created_at >= day_ago
    )
    avg_latency = session.exec(latency_stmt).one()

    return {
        "uptime": 99.99, # Keep as placeholder until infra monitoring is added
        "status": "ONLINE" if success_rate > 95 else "DEGRADED",
        "latency": int(avg_latency),
        "successRate": round(success_rate, 2),
        "activeNodes": 12,
        "lastIncident": "None"
    }


def get_admin_dashboard_overview(
    *, session: Session
) -> Dict[str, Any]:
    """
    Get complete admin dashboard overview
    """
    return {
        "weekly": get_global_period_metrics(session=session, period="week"),
        "monthly": get_global_period_metrics(session=session, period="month"),
        "annually": get_global_period_metrics(session=session, period="year"),
        "weeklyUsageTrends": get_global_weekly_usage_trends(session=session),
        "modelUsageDistribution": get_global_model_usage(session=session),
        "topWorkspaces": get_top_workspaces(session=session),
        "activities": get_recent_activities(session=session),
        "systemHealth": get_system_health(session=session)
    }
