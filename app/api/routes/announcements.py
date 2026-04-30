import uuid
import logging
from typing import Any, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, func, desc

from app.api.deps import (
    CurrentUser,
    SessionDep,
    RequiresPermission,
)
from app.models import (
    Announcement,
    AnnouncementView,
    Message,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/announcements", tags=["announcements"])

class AnnouncementCreateRequest(BaseModel):
    title: str
    content: str
    category: str = "General"
    status: str = "Sent"
    priority: str = "Normal"
    image: str | None = None
    is_important: bool = False
    is_pinned: bool = False
    scheduled_at: datetime | None = None
    is_active: bool = True

class AnnouncementUpdateRequest(BaseModel):
    title: str | None = None
    content: str | None = None
    category: str | None = None
    status: str | None = None
    priority: str | None = None
    image: str | None = None
    is_important: bool | None = None
    is_pinned: bool | None = None
    scheduled_at: datetime | None = None
    is_active: bool | None = None

@router.post("", dependencies=[Depends(RequiresPermission("announcement:manage"))])
def create_announcement(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    data: AnnouncementCreateRequest
) -> Any:
    announcement = Announcement(
        title=data.title,
        content=data.content,
        category=data.category,
        status=data.status,
        priority=data.priority,
        image=data.image,
        is_important=data.is_important,
        is_pinned=data.is_pinned,
        scheduled_at=data.scheduled_at,
        is_active=data.is_active,
        created_by_id=current_user.id
    )
    session.add(announcement)
    session.commit()
    session.refresh(announcement)
    return announcement

from app.utils.permissions import user_has_any_role

@router.get("")
def read_announcements(
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 100,
    active_only: bool = True,
    category: str | None = None,
    priority: str | None = None,
    status: str | None = None
) -> Any:
    # Get current user permissions using utility
    is_admin = user_has_any_role(session, current_user, ["super_admin", "admin"])
    
    statement = select(Announcement)
    
    # Non-admins only see active and "Sent" announcements
    if not is_admin:
        statement = statement.where(Announcement.is_active == True)
        statement = statement.where(Announcement.status == "Sent")
    else:
        # Admins can filter by active_only and status
        if active_only:
            statement = statement.where(Announcement.is_active == True)
        if status:
            statement = statement.where(Announcement.status == status)

    if category:
        statement = statement.where(Announcement.category == category)
    if priority:
        statement = statement.where(Announcement.priority == priority)
    
    statement = statement.order_by(desc(Announcement.is_pinned), desc(Announcement.created_at)).offset(skip).limit(limit)
    return session.exec(statement).all()

@router.put("/{announcement_id}", dependencies=[Depends(RequiresPermission("announcement:manage"))])
def update_announcement(
    *,
    session: SessionDep,
    announcement_id: uuid.UUID,
    data: AnnouncementUpdateRequest
) -> Any:
    announcement = session.get(Announcement, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(announcement, field, value)
    
    session.add(announcement)
    session.commit()
    session.refresh(announcement)
    return announcement

@router.post("/{announcement_id}/view")
def record_announcement_view(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    announcement_id: uuid.UUID
) -> Any:
    announcement = session.get(Announcement, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    
    # Check if this user has already viewed this announcement
    view_record = session.get(AnnouncementView, (announcement_id, current_user.id))
    
    if not view_record:
        # Create new view record
        view_record = AnnouncementView(
            announcement_id=announcement_id,
            user_id=current_user.id
        )
        session.add(view_record)
        
        # Increment unique view count
        announcement.views += 1
        session.add(announcement)
        session.commit()
        return Message(message="Unique view recorded")
    
    return Message(message="View already recorded")

@router.delete("/{announcement_id}", dependencies=[Depends(RequiresPermission("announcement:manage"))])
def delete_announcement(
    *, session: SessionDep, announcement_id: uuid.UUID
) -> Any:
    announcement = session.get(Announcement, announcement_id)
    if not announcement:
        raise HTTPException(status_code=404, detail="Announcement not found")
    session.delete(announcement)
    session.commit()
    return Message(message="Announcement deleted")
