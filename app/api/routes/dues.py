from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlmodel import Session, select
import logging

from app.api import deps
from app.models import Due, DueCreate, DueUpdate, DuePublic, Message, User
from app.utils.notifications import create_notification
from app.core.db import engine
from sqlmodel import Session as SQLSession

router = APIRouter()

def process_due_notifications_background(user_data: list, due_id: str, title: str, amount: float, formatted_date: str):
    """Background task to send in-app and email notifications to all members."""
    from app.services.email_service import email_service
    amount_str = f"{amount:,.2f}"
    
    with SQLSession(engine) as db_session:
        for uid, email, name in user_data:
            # 1. In-app notification
            try:
                create_notification(
                    session=db_session,
                    user_id=uid,
                    title="New Due Available",
                    description=f"A new due '{title}' for ₦{amount_str} has been added. Please check your dashboard and pay by {formatted_date}.",
                    notification_type="warning",
                    metadata={"type": "new_due", "due_id": str(due_id)}
                )
                db_session.commit()
            except Exception as e:
                logging.getLogger(__name__).error(f"In-app notification failed for user {uid}: {e}")
            
            # 2. Email notification
            if email:
                try:
                    email_service.send_new_due_notification(
                        email_to=email,
                        username=name or "Member",
                        due_title=title,
                        due_amount=amount_str,
                        formatted_date=formatted_date,
                    )
                except Exception as e:
                    logging.getLogger(__name__).error(f"Due email failed for {email}: {e}")

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
    background_tasks: BackgroundTasks,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Create new due and notify all active members.
    """
    due = Due.model_validate(due_in)
    session.add(due)
    session.commit()
    session.refresh(due)
    
    try:
        # Fetch active users and pass necessary data to background task
        users = session.exec(select(User).where(User.status == "active")).all()
        user_data = [(u.id, u.email, u.full_name) for u in users]
        formatted_date = due.due_date.strftime("%b %d, %Y") if due.due_date else "the deadline"
        
        background_tasks.add_task(
            process_due_notifications_background,
            user_data=user_data,
            due_id=str(due.id),
            title=due.title,
            amount=float(due.amount),
            formatted_date=formatted_date
        )
    except Exception as e:
        logging.getLogger(__name__).error(f"Failed to queue due notifications: {e}")
        
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
