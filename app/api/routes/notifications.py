from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api import deps
from app.notification_repository import (
    get_user_notifications,
    mark_as_read,
    mark_all_as_read,
    delete_notification
)
from app.models import NotificationPublic, NotificationsPublic, Message

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", response_model=NotificationsPublic)
def read_notifications(
    session: deps.SessionDep,
    current_user: deps.CurrentUser,
    skip: int = 0,
    limit: int = 20,
    unread_only: bool = False,
) -> Any:
    """Retrieve notifications."""
    db_objs, total, unread_count = get_user_notifications(
        session=session,
        user_id=current_user.id,
        skip=skip,
        limit=limit,
        unread_only=unread_only
    )
    
    # Map to public schema with metadata handling
    notifications_public = []
    for obj in db_objs:
        notifications_public.append(
            NotificationPublic(
                id=obj.id,
                userId=obj.user_id,
                title=obj.title,
                description=obj.description,
                type=obj.type,
                isRead=obj.is_read,
                createdAt=obj.created_at,
                metadata=obj.metadata_json
            )
        )
    
    return NotificationsPublic(
        data=notifications_public,
        count=total,
        unreadCount=unread_count
    )


@router.patch("/{id}/read", response_model=NotificationPublic)
def mark_notification_read(
    *,
    session: deps.SessionDep,
    id: uuid.UUID,
    current_user: deps.CurrentUser,
) -> Any:
    """Mark a notification as read."""
    notification = mark_as_read(session=session, notification_id=id, user_id=current_user.id)
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
    
    return NotificationPublic(
        id=notification.id,
        userId=notification.user_id,
        title=notification.title,
        description=notification.description,
        type=notification.type,
        isRead=notification.is_read,
        createdAt=notification.created_at,
        metadata=notification.metadata_json
    )


@router.patch("/read-all", response_model=Message)
def mark_all_notifications_read(
    session: deps.SessionDep,
    current_user: deps.CurrentUser,
) -> Any:
    """Mark all notifications as read."""
    count = mark_all_as_read(session=session, user_id=current_user.id)
    return Message(message=f"Successfully marked {count} notifications as read")


@router.delete("/{id}", response_model=Message)
def delete_user_notification(
    *,
    session: deps.SessionDep,
    id: uuid.UUID,
    current_user: deps.CurrentUser,
) -> Any:
    """Delete a notification."""
    success = delete_notification(session=session, notification_id=id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Notification not found")
    return Message(message="Notification deleted successfully")
