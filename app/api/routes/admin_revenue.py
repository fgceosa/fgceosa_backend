from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import CurrentUser, SessionDep
from app import revenue_repository

router = APIRouter(prefix="/admin/revenue", tags=["Admin Revenue"])

@router.get("")
def get_revenue_dashboard(
    session: SessionDep,
    current_user: CurrentUser,
    period: str = "month"
) -> Dict[str, Any]:
    """
    Get full platform revenue and financial analytics.
    Only available to superusers.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can access revenue analytics"
        )
    
    return revenue_repository.get_admin_revenue_dashboard(
        session=session, 
        period=period
    )
