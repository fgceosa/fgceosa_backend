from typing import Any
from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select

from app.api import deps
from app.models import SystemSettings, SystemSettingsUpdate, SystemSettingsPublic, Message

router = APIRouter()

@router.get("", response_model=SystemSettingsPublic)
def read_system_settings(
    session: Session = Depends(deps.get_db),
) -> Any:
    """
    Get system settings.
    """
    settings = session.get(SystemSettings, 1)
    if not settings:
        # Create default settings if they don't exist
        settings = SystemSettings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    return settings

@router.put("", response_model=SystemSettingsPublic)
def update_system_settings(
    *,
    session: Session = Depends(deps.get_db),
    settings_in: SystemSettingsUpdate,
    current_user = Depends(deps.get_current_active_superuser),
) -> Any:
    """
    Update system settings.
    """
    settings = session.get(SystemSettings, 1)
    if not settings:
        settings = SystemSettings(id=1)
        session.add(settings)
        session.commit()
        session.refresh(settings)
    
    update_data = settings_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)
    
    session.add(settings)
    session.commit()
    session.refresh(settings)
    return settings
