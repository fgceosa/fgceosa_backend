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
    db_settings = session.get(SystemSettings, 1)
    if not db_settings:
        # Create default settings if they don't exist
        db_settings = SystemSettings(id=1)
        session.add(db_settings)
        session.commit()
        session.refresh(db_settings)
        
    from app.core.config import settings as app_settings
    
    return SystemSettingsPublic(
        association_name=db_settings.association_name,
        association_logo=db_settings.association_logo,
        contact_email=db_settings.contact_email,
        contact_phone=db_settings.contact_phone,
        address=db_settings.address,
        currency=db_settings.currency,
        payment_enabled=db_settings.payment_enabled,
        paystack_public_key=db_settings.paystack_public_key or app_settings.PAYSTACK_PUBLIC_KEY,
        paystack_secret_key=db_settings.paystack_secret_key or app_settings.PAYSTACK_SECRET_KEY,
        tax_percentage=db_settings.tax_percentage,
        invoice_footer_note=db_settings.invoice_footer_note,
        default_member_status=db_settings.default_member_status,
        allow_self_registration=db_settings.allow_self_registration,
        enable_email_notifications=db_settings.enable_email_notifications,
        timezone=db_settings.timezone,
        date_format=db_settings.date_format,
        bank_name=db_settings.bank_name,
        account_number=db_settings.account_number,
        account_name=db_settings.account_name
    )

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
