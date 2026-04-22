import uuid
import logging
from typing import Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, func, desc

from app.api.deps import (
    CurrentUser,
    SessionDep,
)
from app.models import (
    Notification,
    NotificationPublic,
    NotificationsPublic,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/notifications", tags=["notifications"])

@router.get("", response_model=NotificationsPublic)
def read_notifications(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    unread_only: bool = False
) -> Any:
    """
    Retrieve notifications for the current user.
    """
    statement = select(Notification).where(Notification.user_id == current_user.id).order_by(desc(Notification.created_at))
    
    if unread_only:
        statement = statement.where(Notification.is_read == False)
        
    count_statement = select(func.count()).select_from(statement.subquery())
    count = session.exec(count_statement).one()
    
    # Calculate unread count regardless of filters
    unread_count = session.exec(
        select(func.count()).select_from(Notification).where(Notification.user_id == current_user.id).where(Notification.is_read == False)
    ).one()
    
    skip = (page - 1) * page_size
    notifications = session.exec(statement.offset(skip).limit(page_size)).all()
    
    return {
        "data": notifications,
        "count": count,
        "unreadCount": unread_count
    }

@router.patch("/{notification_id}/read", response_model=NotificationPublic)
def mark_notification_as_read(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    notification_id: uuid.UUID
) -> Any:
    """
    Mark a specific notification as read.
    """
    notification = session.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this notification")
    
    notification.is_read = True
    session.add(notification)
    session.commit()
    session.refresh(notification)
    return notification

@router.patch("/read-all")
def mark_all_notifications_as_read(
    *,
    session: SessionDep,
    current_user: CurrentUser
) -> Any:
    """
    Mark all notifications for the current user as read.
    """
    statement = select(Notification).where(Notification.user_id == current_user.id).where(Notification.is_read == False)
    notifications = session.exec(statement).all()
    
    for notification in notifications:
        notification.is_read = True
        session.add(notification)
        
    session.commit()
    return {"message": f"Marked {len(notifications)} notifications as read"}

@router.delete("/{notification_id}")
def delete_notification(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    notification_id: uuid.UUID
) -> Any:
    """
    Delete a specific notification.
    """
    notification = session.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    if notification.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to access this notification")
    
    session.delete(notification)
    session.commit()
    return {"message": "Notification deleted"}
