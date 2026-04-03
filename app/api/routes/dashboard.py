from datetime import datetime, timedelta
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.api import deps
from app.api.deps import CurrentUser, SessionDep
from app import analytics_repository
from app.utils.permissions import user_has_permission

router = APIRouter(
    prefix="",
    tags=["Platform Dashboard"],
)


@router.get("/dashboard")
def get_dashboard_data(
    session: SessionDep,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """
    Get complete dashboard data.
    If user is superuser (Admin), returns global platform metrics including top workspaces and activity.
    If regular user, returns personal metrics.
    """
    if user_has_permission(session, current_user, "dashboard:admin"):
        return analytics_repository.get_admin_dashboard_overview(session=session)
    
    return analytics_repository.get_dashboard_overview(
        session=session, user_id=current_user.id
    )


@router.get("/dashboard/metrics")
def get_dashboard_metrics(
    session: SessionDep,
    current_user: CurrentUser,
    period: str = "week",
) -> Dict[str, Any]:
    """
    Get dashboard metrics for a specific period (week, month, year).
    """
    if user_has_permission(session, current_user, "analytics:system"):
        return analytics_repository.get_global_period_metrics(
            session=session, period=period
        )

    return analytics_repository.get_period_metrics(
        session=session, user_id=current_user.id, period=period
    )


@router.get("/dashboard/weekly-trends")
def get_weekly_trends(
    session: SessionDep,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """
    Get weekly usage trends - API requests and costs over last 7 days.
    """
    if user_has_permission(session, current_user, "analytics:usage"):
        return analytics_repository.get_global_weekly_usage_trends(session=session)

    return analytics_repository.get_weekly_usage_trends(
        session=session, user_id=current_user.id
    )


@router.get("/dashboard/model-usage")
def get_model_usage(
    session: SessionDep,
    current_user: CurrentUser,
) -> List[Dict[str, Any]]:
    """
    Get model usage distribution by AI model.
    """
    if user_has_permission(session, current_user, "model:view"):
        return analytics_repository.get_global_model_usage(session=session)

    return analytics_repository.get_model_usage_distribution(
        session=session, user_id=current_user.id
    )


@router.get("/dashboard/credit-balance")
def get_credit_balance(
    session: SessionDep,
    current_user: CurrentUser,
) -> Dict[str, Any]:
    """
    Get current credit balance for the user.
    """
    balance = analytics_repository.get_credit_balance(
        session=session, user_id=current_user.id
    )
    return {"balance": float(balance)}


@router.get("/dashboard/active-projects")
def get_active_projects(
    session: SessionDep,
    current_user: CurrentUser,
):
    """
    Get all active projects for the user.
    """
    # For admin, this might need to return all active projects in system?
    # Keeping it user-specific for now as 'active projects' list is usually personal.
    # If admin needs all projects, that's likely a separate 'projects' management page.
    return analytics_repository.get_active_projects(
        session=session, user_id=current_user.id
    )


@router.get("/dashboard/credit-history")
def get_credit_history(
    session: SessionDep,
    current_user: CurrentUser,
    limit: int = 10,
):
    """
    Get recent credit transaction history.
    """
    return analytics_repository.get_credit_history(
        session=session, user_id=current_user.id, limit=limit
    )


@router.get("/dashboard/recent-requests")
def get_recent_requests(
    session: SessionDep,
    current_user: CurrentUser,
    limit: int = 20,
):
    """
    Get recent API requests for the user.
    """
    return analytics_repository.get_recent_api_requests(
        session=session, user_id=current_user.id, limit=limit
    )
