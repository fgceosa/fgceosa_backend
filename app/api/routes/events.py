import uuid
import logging
from typing import Any, List, Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import select, func, desc

from app.api.deps import (
    CurrentUser,
    OptionalCurrentUser,
    SessionDep,
    RequiresPermission,
)
from app.models import (
    Event,
    Message,
    EventRegistration,
    EventRegistrationCreate,
    EventRegistrationPublic,
    UserPublic,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/events", tags=["events"])

class EventCreateRequest(BaseModel):
    title: str
    description: str
    date: datetime
    time: str = "12:00 PM"
    location: str | None = None
    capacity: int = 100
    category: str = "General"
    status: str = "Upcoming"
    image: str| None = None
    is_online: bool = False
    meeting_link: str | None = None

class EventUpdateRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    date: datetime | None = None
    time: str | None = None
    location: str | None = None
    capacity: int | None = None
    category: str | None = None
    status: str | None = None
    image: str | None = None
    total_registered: int | None = None
    is_online: bool | None = None
    meeting_link: str | None = None

class EventPublic(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    date: datetime
    time: str
    location: str | None
    status: str
    image: str | None
    total_registered: int
    capacity: int
    category: str
    is_online: bool
    meeting_link: str | None
    is_registered: bool = False
    created_at: datetime
    created_by_id: uuid.UUID

@router.post("", response_model=EventPublic, dependencies=[Depends(RequiresPermission("event:manage"))])
def create_event(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    data: EventCreateRequest
) -> Any:
    event = Event(**data.dict(), created_by_id=current_user.id)
    session.add(event)
    session.commit()
    session.refresh(event)
    return event

@router.get("", response_model=List[EventPublic])
def read_events(
    session: SessionDep,
    current_user: OptionalCurrentUser = None,
    skip: int = 0,
    limit: int = 100
) -> Any:
    statement = select(Event).order_by(Event.date.asc()).offset(skip).limit(limit)
    events = session.exec(statement).all()
    
    registered_event_ids = set()
    if current_user:
        # Get all registrations for this user to avoid N+1
        event_ids = [e.id for e in events]
        registrations = session.exec(
            select(EventRegistration.event_id)
            .where(
                EventRegistration.user_id == current_user.id,
                EventRegistration.event_id.in_(event_ids)
            )
        ).all()
        registered_event_ids = set(registrations)
    
    return [
        EventPublic(
            id=e.id,
            title=e.title,
            description=e.description,
            date=e.date,
            time=e.time,
            location=e.location,
            status=e.status,
            image=e.image,
            total_registered=e.total_registered,
            capacity=e.capacity,
            category=e.category,
            is_online=e.is_online,
            meeting_link=e.meeting_link,
            is_registered=e.id in registered_event_ids,
            created_at=e.created_at,
            created_by_id=e.created_by_id,
        )
        for e in events
    ]

@router.get("/{event_id}", response_model=EventPublic)
def read_event(
    *,
    session: SessionDep,
    current_user: OptionalCurrentUser = None,
    event_id: uuid.UUID
) -> Any:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    is_reg = False
    if current_user:
        registration = session.exec(
            select(EventRegistration)
            .where(
                EventRegistration.event_id == event_id,
                EventRegistration.user_id == current_user.id
            )
        ).first()
        is_reg = registration is not None
        
    return EventPublic(
        id=event.id,
        title=event.title,
        description=event.description,
        date=event.date,
        time=event.time,
        location=event.location,
        status=event.status,
        image=event.image,
        total_registered=event.total_registered,
        capacity=event.capacity,
        category=event.category,
        is_online=event.is_online,
        meeting_link=event.meeting_link,
        is_registered=is_reg,
        created_at=event.created_at,
        created_by_id=event.created_by_id,
    )

@router.put("/{event_id}", response_model=EventPublic, dependencies=[Depends(RequiresPermission("event:manage"))])
def update_event(
    *,
    session: SessionDep,
    event_id: uuid.UUID,
    data: EventUpdateRequest
) -> Any:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    update_data = data.dict(exclude_unset=True)
    for key, value in update_data.items():
        setattr(event, key, value)
        
    session.add(event)
    session.commit()
    session.refresh(event)
    return event

@router.delete("/{event_id}", dependencies=[Depends(RequiresPermission("event:manage"))])
def delete_event(
    *, session: SessionDep, event_id: uuid.UUID
) -> Any:
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    session.delete(event)
    session.commit()
    return Message(message="Event deleted")


@router.post("/{event_id}/register", response_model=EventRegistrationPublic)
def register_for_event(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    event_id: uuid.UUID,
    data: Optional[EventRegistrationCreate] = None
) -> Any:
    """
    Register the current user for an event.
    """
    event = session.get(Event, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    
    if event.status.lower() == "past":
        raise HTTPException(status_code=400, detail="Cannot register for a past event")

    # Check if already registered
    existing_reg = session.exec(
        select(EventRegistration).where(
            EventRegistration.event_id == event_id,
            EventRegistration.user_id == current_user.id
        )
    ).first()
    
    if existing_reg:
        raise HTTPException(status_code=400, detail="You are already registered for this event")

    # Check capacity
    requested_attendees = data.attendees_count if data else 1
    if event.total_registered + requested_attendees > event.capacity:
        raise HTTPException(status_code=400, detail=f"Event only has {event.capacity - event.total_registered} spots remaining")

    registration = EventRegistration(
        event_id=event_id,
        user_id=current_user.id,
        notes=data.notes if data else None,
        attendees_count=data.attendees_count if data else 1
    )
    
    # Increment event registration count
    event.total_registered += registration.attendees_count
    
    session.add(registration)
    session.add(event)
    session.commit()
    session.refresh(registration)
    
    # Notify Admin if needed (optional)
    
    return registration


@router.get(
    "/{event_id}/registrants", 
    response_model=List[EventRegistrationPublic],
    dependencies=[Depends(RequiresPermission("event:manage"))]
)
def get_event_registrants(
    *,
    session: SessionDep,
    event_id: uuid.UUID
) -> Any:
    """
    Get list of registered members for an event (Admin only).
    """
    from sqlalchemy.orm import selectinload
    statement = select(EventRegistration).where(EventRegistration.event_id == event_id).options(selectinload(EventRegistration.user))
    registrations = session.exec(statement).all()
    
    # Enrich with user data
    output = []
    for reg in registrations:
        public_reg = EventRegistrationPublic(
            id=reg.id,
            event_id=reg.event_id,
            user_id=reg.user_id,
            registration_date=reg.registration_date,
            notes=reg.notes,
            attendees_count=reg.attendees_count,
            status=reg.status,
            user=UserPublic.from_user(reg.user)
        )
        output.append(public_reg)
        
    return output


@router.get("/my-registrations", response_model=List[EventPublic])
def get_my_event_registrations(
    *,
    session: SessionDep,
    current_user: CurrentUser
) -> Any:
    """
    Get list of events the current user is registered for.
    """
    statement = (
        select(Event)
        .join(EventRegistration, Event.id == EventRegistration.event_id)
        .where(EventRegistration.user_id == current_user.id)
        .order_by(desc(Event.date))
    )
    return session.exec(statement).all()
