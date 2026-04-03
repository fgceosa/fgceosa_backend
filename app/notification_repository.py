import uuid
from datetime import datetime, timezone
from typing import List, Optional, Tuple

from sqlmodel import Session, select, func, desc

from app.models import Notification


def create_notification(
    *,
    session: Session,
    user_id: uuid.UUID,
    title: str,
    description: str,
    type: str = "general",
    metadata: Optional[dict] = None,
    commit: bool = True
) -> Notification:
    """Create a new notification for a user"""
    db_obj = Notification(
        user_id=user_id,
        title=title,
        description=description,
        type=type,
        metadata_json=metadata or {}
    )
    session.add(db_obj)
    if commit:
        session.commit()
        session.refresh(db_obj)
    return db_obj


def get_user_notifications(
    *, session: Session, user_id: uuid.UUID, skip: int = 0, limit: int = 20, unread_only: bool = False
) -> Tuple[List[Notification], int, int]:
    """Get notifications for a user with total count and unread count"""
    # Base query
    statement = select(Notification).where(Notification.user_id == user_id)
    
    # Unread count
    unread_statement = select(func.count()).select_from(Notification).where(
        Notification.user_id == user_id, 
        Notification.is_read == False
    )
    unread_count = session.exec(unread_statement).one()
    
    # Filter by unread if requested
    if unread_only:
        statement = statement.where(Notification.is_read == False)
    
    # Order by newest first
    statement = statement.order_by(desc(Notification.created_at))
    
    # Count total (filtered)
    count_statement = select(func.count()).select_from(statement.subquery())
    total = session.exec(count_statement).one()
    
    # Apply limit/skip
    db_objs = session.exec(statement.offset(skip).limit(limit)).all()
    
    return db_objs, total, unread_count


def mark_as_read(*, session: Session, notification_id: uuid.UUID, user_id: uuid.UUID) -> Optional[Notification]:
    """Mark a specific notification as read"""
    db_obj = session.get(Notification, notification_id)
    if not db_obj or db_obj.user_id != user_id:
        return None
    
    db_obj.is_read = True
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)
    return db_obj


def mark_all_as_read(*, session: Session, user_id: uuid.UUID) -> int:
    """Mark all unread notifications for a user as read"""
    statement = select(Notification).where(
        Notification.user_id == user_id,
        Notification.is_read == False
    )
    unread_notifications = session.exec(statement).all()
    
    count = 0
    for notification in unread_notifications:
        notification.is_read = True
        session.add(notification)
        count += 1
    
    if count > 0:
        session.commit()
    
    return count


def delete_notification(*, session: Session, notification_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    """Delete a notification"""
    db_obj = session.get(Notification, notification_id)
    if not db_obj or db_obj.user_id != user_id:
        return False
    
    session.delete(db_obj)
    session.commit()
    return True
