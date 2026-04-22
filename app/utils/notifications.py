import uuid
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
from sqlmodel import Session, select

from app.models import User, Notification, UserRole, Role

logger = logging.getLogger(__name__)

def create_notification(
    session: Session,
    user_id: uuid.UUID,
    title: str,
    description: str,
    notification_type: str = "info",
    metadata: Optional[Dict[str, Any]] = None
) -> Notification:
    """
    Create a notification for a specific user
    """
    notification = Notification(
        user_id=user_id,
        title=title,
        description=description,
        type=notification_type,
        metadata_json=metadata,
        created_at=datetime.now(timezone.utc)
    )
    session.add(notification)
    session.commit()
    session.refresh(notification)
    return notification

def notify_admins(
    session: Session,
    title: str,
    description: str,
    notification_type: str = "info",
    metadata: Optional[Dict[str, Any]] = None
) -> List[Notification]:
    """
    Create a notification for all users with admin or super_admin roles
    """
    # Find all admin users
    statement = (
        select(User)
        .join(UserRole, User.id == UserRole.user_id)
        .join(Role, UserRole.role_id == Role.id)
        .where(Role.name.in_(["admin", "super_admin"]))
    )
    admins = session.exec(statement).all()
    
    # Also include users with is_superuser=True
    superuser_statement = select(User).where(User.is_superuser == True)
    superusers = session.exec(superuser_statement).all()
    
    # Combine and de-duplicate
    all_admins = {u.id: u for u in list(admins) + list(superusers)}.values()
    
    notifications = []
    for admin in all_admins:
        try:
            notif = Notification(
                user_id=admin.id,
                title=title,
                description=description,
                type=notification_type,
                metadata_json=metadata,
                created_at=datetime.now(timezone.utc)
            )
            session.add(notif)
            notifications.append(notif)
        except Exception as e:
            logger.error(f"Failed to create notification for admin {admin.id}: {e}")
            
    if notifications:
        session.commit()
        for n in notifications:
            session.refresh(n)
            
    return notifications
