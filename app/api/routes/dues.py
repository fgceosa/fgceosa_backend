from typing import Any
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api import deps
from app.models import Due, DueCreate, DueUpdate, DuePublic, Message

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
