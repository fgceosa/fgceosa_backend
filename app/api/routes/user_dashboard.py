"""
User Dashboard API Routes

Handles user dashboard data including metrics, usage trends, and statistics
"""

from typing import Any, List
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from sqlmodel import Session, select, func, and_
from pydantic import BaseModel

from app.api import deps
from app.models import User, Project, APIRequest, CreditTransaction
from app import analytics_repository

class PeriodMetrics(BaseModel):
    """Metrics for a specific period"""
    creditBalance: float
    apiRequests: int
    spending: float
    activeProjects: int
    spendingTrend: str | None = None
    # Add optional admin fields
    activeUsers: int | None = None
    totalRevenue: float | None = None
    tokenUsage: int | None = None
    aiAgents: int | None = None
    avgRevenuePerUser: float | None = None

    class Config:
        populate_by_name = True


class WeeklyTrend(BaseModel):
    """Daily trend data"""
    date: str
    requests: int
    cost: float

    class Config:
        populate_by_name = True


class WeeklyUsageTrends(BaseModel):
    """Weekly usage trends"""
    series: List[dict]
    dates: List[str]

    class Config:
        populate_by_name = True


class ModelUsageItem(BaseModel):
    """Model usage statistics"""
    model: str
    count: int
    percentage: float
    color: str | None = None

    class Config:
        populate_by_name = True


class CreditBalanceResponse(BaseModel):
    """Credit balance information"""
    available_credits: float
    credits_used_this_month: float

    class Config:
        populate_by_name = True


class DashboardData(BaseModel):
    """Complete dashboard data"""
    weekly: PeriodMetrics
    monthly: PeriodMetrics
    annually: PeriodMetrics
    weeklyUsageTrends: WeeklyUsageTrends
    modelUsageDistribution: List[ModelUsageItem]
    
    # Admin specific fields
    topWorkspaces: List[dict] | None = None
    activities: List[dict] | None = None
    systemHealth: dict | None = None

    class Config:
        populate_by_name = True


router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardData)
def get_dashboard_data(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get complete dashboard data for the current user.
    If user is superuser, returns Admin Dashboard data.
    """
    if current_user.is_superuser:
        return analytics_repository.get_admin_dashboard_overview(session=session)

    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    year_ago = now - timedelta(days=365)

    # Helper function to calculate metrics
    def get_metrics(start_date: datetime, period_days: int) -> PeriodMetrics:
        query_filter = and_(
            APIRequest.user_id == current_user.id,
            APIRequest.created_at >= start_date
        )

        # Get total API requests
        total_requests = session.exec(
            select(func.count(APIRequest.id)).where(query_filter)
        ).one()

        # Get total cost/spending
        total_cost_result = session.exec(
            select(func.sum(APIRequest.cost)).where(query_filter)
        ).one()
        total_cost = float(total_cost_result or 0)

        # Get active projects count for this period
        active_projects = session.exec(
            select(func.count(func.distinct(APIRequest.project_id))).where(query_filter)
        ).one()

        # Calculate Trend
        previous_start_date = start_date - timedelta(days=period_days)
        previous_query_filter = and_(
             APIRequest.user_id == current_user.id,
             APIRequest.created_at >= previous_start_date,
             APIRequest.created_at < start_date
        )
        previous_cost_result = session.exec(
            select(func.sum(APIRequest.cost)).where(previous_query_filter)
        ).one()
        previous_cost = float(previous_cost_result or 0)

        trend_val = "0%"
        is_positive = True
        
        if previous_cost == 0:
            if total_cost > 0:
                trend_val = "100%"
                is_positive = True
            else:
                trend_val = "0%"
                is_positive = True
        else:
            change = ((total_cost - previous_cost) / previous_cost) * 100
            trend_val = f"{abs(change):.1f}%"
            is_positive = change >= 0
        
        # Add sign for clarity
        sign = "+" if is_positive else "-"
        # If 0%, just show 0%
        if trend_val == "0%" or trend_val == "0.0%":
             sign = ""
        
        final_trend = f"{sign}{trend_val}"


        return PeriodMetrics(
            creditBalance=float(analytics_repository.get_credit_balance(session=session, user_id=current_user.id)),
            apiRequests=total_requests,
            spending=float(total_cost),
            activeProjects=active_projects,
            spendingTrend=final_trend
        )

    # Get metrics for different periods
    weekly_metrics = get_metrics(week_ago, 7)
    monthly_metrics = get_metrics(month_ago, 30)
    yearly_metrics = get_metrics(year_ago, 365)

    # Get weekly usage trends
    trends_data = []
    dates_data = []
    requests_data = []
    costs_data = []

    for i in range(6, -1, -1):  # Last 7 days
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        query_filter = and_(
            APIRequest.user_id == current_user.id,
            APIRequest.created_at >= day_start,
            APIRequest.created_at < day_end
        )

        requests_count = session.exec(
            select(func.count(APIRequest.id)).where(query_filter)
        ).one()

        cost_result = session.exec(
            select(func.sum(APIRequest.cost)).where(query_filter)
        ).one()
        cost = float(cost_result or 0)

        dates_data.append(day_start.strftime("%Y-%m-%d"))
        requests_data.append(requests_count)
        costs_data.append(float(cost))

    weekly_usage_trends = WeeklyUsageTrends(
        series=[
            {"name": "API Requests", "data": requests_data},
            {"name": "Cost (₦)", "data": costs_data}
        ],
        dates=dates_data
    )

    # Get model usage distribution
    total_requests = session.exec(
        select(func.count(APIRequest.id)).where(APIRequest.user_id == current_user.id)
    ).one()

    model_usage = []
    if total_requests > 0:
        result = session.exec(
            select(APIRequest.model, func.count(APIRequest.id))
            .where(APIRequest.user_id == current_user.id)
            .group_by(APIRequest.model)
        ).all()

        for model, count in result:
            percentage = (count / total_requests) * 100
            model_usage.append(ModelUsageItem(
                model=model,
                count=count,
                percentage=round(percentage, 2)
            ))

        # Sort by count descending
        model_usage.sort(key=lambda x: x.count, reverse=True)

    return DashboardData(
        weekly=weekly_metrics,
        monthly=monthly_metrics,
        annually=yearly_metrics,
        weeklyUsageTrends=weekly_usage_trends,
        modelUsageDistribution=model_usage
    )


@router.get("/metrics", response_model=PeriodMetrics)
def get_dashboard_metrics(
    period: str = Query("week", description="Period: week, month, or year"),
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get dashboard metrics for a specific period.
    """
    if current_user.is_superuser:
        return analytics_repository.get_global_period_metrics(
            session=session, period=period
        )

    now = datetime.now(timezone.utc)
    period_days = 7

    if period == "week":
        start_date = now - timedelta(days=7)
        period_days = 7
    elif period == "month":
        start_date = now - timedelta(days=30)
        period_days = 30
    elif period == "year":
        start_date = now - timedelta(days=365)
        period_days = 365
    else:
        start_date = now - timedelta(days=7)
        period_days = 7

    query_filter = and_(
        APIRequest.user_id == current_user.id,
        APIRequest.created_at >= start_date
    )

    # Get total API requests
    total_requests = session.exec(
        select(func.count(APIRequest.id)).where(query_filter)
    ).one()

    # Get total cost/spending
    total_cost_result = session.exec(
        select(func.sum(APIRequest.cost)).where(query_filter)
    ).one()
    total_cost = float(total_cost_result or 0)

    # Get active projects count for this period
    active_projects = session.exec(
        select(func.count(func.distinct(APIRequest.project_id))).where(query_filter)
    ).one()

    # Calculate Trend
    previous_start_date = start_date - timedelta(days=period_days)
    previous_query_filter = and_(
            APIRequest.user_id == current_user.id,
            APIRequest.created_at >= previous_start_date,
            APIRequest.created_at < start_date
    )
    previous_cost_result = session.exec(
        select(func.sum(APIRequest.cost)).where(previous_query_filter)
    ).one()
    previous_cost = float(previous_cost_result or 0)

    trend_val = "0%"
    is_positive = True
    
    if previous_cost == 0:
        if total_cost > 0:
            trend_val = "100%"
            is_positive = True
        else:
            trend_val = "0%"
            is_positive = True
    else:
        change = ((total_cost - previous_cost) / previous_cost) * 100
        trend_val = f"{abs(change):.1f}%"
        is_positive = change >= 0
    
    sign = "+" if is_positive else "-"
    if trend_val == "0%" or trend_val == "0.0%":
            sign = ""
    
    final_trend = f"{sign}{trend_val}"

    return PeriodMetrics(
        creditBalance=float(analytics_repository.get_credit_balance(session=session, user_id=current_user.id)),
        apiRequests=total_requests,
        spending=float(total_cost),
        activeProjects=active_projects,
        spendingTrend=final_trend
    )


@router.get("/weekly-trends", response_model=WeeklyUsageTrends)
def get_weekly_trends(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get weekly usage trends - daily breakdown of requests and costs.
    """
    if current_user.is_superuser:
        return analytics_repository.get_global_weekly_usage_trends(session=session)

    now = datetime.now(timezone.utc)
    dates_data = []
    requests_data = []
    costs_data = []

    for i in range(6, -1, -1):  # Last 7 days
        day_start = (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        query_filter = and_(
            APIRequest.user_id == current_user.id,
            APIRequest.created_at >= day_start,
            APIRequest.created_at < day_end
        )

        requests_count = session.exec(
            select(func.count(APIRequest.id)).where(query_filter)
        ).one()

        cost_result = session.exec(
            select(func.sum(APIRequest.cost)).where(query_filter)
        ).one()
        cost = float(cost_result or 0)

        dates_data.append(day_start.strftime("%Y-%m-%d"))
        requests_data.append(requests_count)
        costs_data.append(float(cost))

    return WeeklyUsageTrends(
        series=[
            {"name": "API Requests", "data": requests_data},
            {"name": "Cost (₦)", "data": costs_data}
        ],
        dates=dates_data
    )


@router.get("/model-usage", response_model=List[ModelUsageItem])
def get_model_usage(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get model usage distribution.
    """
    if current_user.is_superuser:
        return analytics_repository.get_global_model_usage(session=session)

    # Get total requests
    total_requests = session.exec(
        select(func.count(APIRequest.id)).where(APIRequest.user_id == current_user.id)
    ).one()

    if total_requests == 0:
        return []

    # Get requests by model
    result = session.exec(
        select(APIRequest.model, func.count(APIRequest.id))
        .where(APIRequest.user_id == current_user.id)
        .group_by(APIRequest.model)
    ).all()

    model_usage = []
    for model, count in result:
        percentage = (count / total_requests) * 100
        model_usage.append(ModelUsageItem(
            model=model,
            count=count,
            percentage=round(percentage, 2)
        ))

    # Sort by count descending
    model_usage.sort(key=lambda x: x.count, reverse=True)

    return model_usage


@router.get("/credit-balance", response_model=CreditBalanceResponse)
def get_credit_balance(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get current credit balance and usage.
    """
    available_credits = current_user.credits

    # Get credits used this month
    month_ago = datetime.now(timezone.utc) - timedelta(days=30)
    credits_used_result = session.exec(
        select(func.sum(CreditTransaction.amount)).where(
            and_(
                CreditTransaction.sender_id == current_user.id,
                CreditTransaction.created_at >= month_ago
            )
        )
    ).one()
    credits_used_this_month = int(credits_used_result or 0)

    return CreditBalanceResponse(
        available_credits=available_credits,
        credits_used_this_month=credits_used_this_month
    )


@router.get("/active-projects")
def get_active_projects(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get all active projects.
    """
    projects = session.exec(
        select(Project).where(
            and_(Project.user_id == current_user.id, Project.is_active == True)
        ).order_by(Project.updated_at.desc())  # type: ignore
    ).all()

    return list(projects)


@router.get("/credit-history")
def get_credit_history(
    limit: int = Query(10, ge=1, le=100),
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get recent credit transaction history.
    """
    # Get transactions where user is sender or recipient
    transactions = session.exec(
        select(CreditTransaction).where(
            (CreditTransaction.sender_id == current_user.id) |
            (CreditTransaction.recipient_id == current_user.id)
        ).order_by(CreditTransaction.created_at.desc())  # type: ignore
        .limit(limit)
    ).all()

    return list(transactions)


@router.get("/recent-requests")
def get_recent_requests(
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get recent API requests.
    """
    requests = session.exec(
        select(APIRequest).where(APIRequest.user_id == current_user.id)
        .order_by(APIRequest.created_at.desc())  # type: ignore
        .limit(limit)
    ).all()

    return list(requests)
