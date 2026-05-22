from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api import deps
from app.models import Due, DueCreate, DueUpdate, DuePublic, Message, User
from app.utils.notifications import create_notification

router = APIRouter()

@router.get("", response_model=list[DuePublic])
def read_dues(
    session: Session = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 100,
) -> Any:
    """
    Retrieve dues.
    """
    dues = session.exec(select(Due).offset(skip).limit(limit)).all()
    return dues

@router.post("", response_model=DuePublic)
def create_due(
    *,
    session: Session = Depends(deps.get_db),
    due_in: DueCreate,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new due.
    """
    due = Due.model_validate(due_in)
    session.add(due)
    session.commit()
    session.refresh(due)
    
    try:
        # Notify all active users about the new due
        users = session.exec(select(User).where(User.status == "active")).all()
        formatted_date = due.due_date.strftime("%b %d, %Y") if due.due_date else "the deadline"
        
        for user in users:
            create_notification(
                session=session,
                user_id=user.id,
                title="New Due Available",
                description=f"A new due '{due.title}' for ₦{float(due.amount):,.2f} has been added. Please check your dashboard and pay by {formatted_date}.",
                notification_type="warning",
                metadata={"type": "new_due", "due_id": str(due.id)}
            )
    except Exception as e:
        # Log error but don't fail the due creation
        import logging
        logging.getLogger(__name__).error(f"Failed to create due notifications: {e}")
        
    return due

@router.put("/{id}", response_model=DuePublic)
def update_due(
    *,
    session: Session = Depends(deps.get_db),
    id: uuid.UUID,
    due_in: DueUpdate,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update a due.
    """
    due = session.get(Due, id)
    if not due:
        raise HTTPException(status_code=404, detail="Due not found")
    
    update_data = due_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(due, key, value)
    
    session.add(due)
    session.commit()
    session.refresh(due)
    return due

@router.delete("/{id}", response_model=Message)
def delete_due(
    *,
    session: Session = Depends(deps.get_db),
    id: uuid.UUID,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Delete a due.
    """
    due = session.get(Due, id)
    if not due:
        raise HTTPException(status_code=404, detail="Due not found")
    
    session.delete(due)
    session.commit()
    return Message(message="Due deleted successfully")
