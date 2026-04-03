from datetime import datetime, timezone
from typing import Any
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select, SQLModel
from pydantic import ConfigDict, Field

from app.api.deps import get_current_active_superuser, SessionDep
from app.models import PlatformSettings, PlatformSettingsUpdate
from sqlmodel import SQLModel

router = APIRouter()

# Default Settings
DEFAULT_SETTINGS = {
    "general": {
        "platformName": 'Qorebit Enterprise',
        "defaultRegion": 'ng-lagos',
        "timezone": 'africa/lagos',
        "language": 'en-us',
        "systemStatus": 'active',
    },
    "notifications": {
        "emailNotifications": True,
        "criticalSystemAlerts": True,
        "fraudAlerts": True,
        "usageThresholdAlerts": True,
        "adminActivityAlerts": True,
    },
    "payments": {
        "defaultMarkup": 15,
        "minCreditAmount": 1000,
        "nairaToCreditRate": 1650,
        "creditExpiryPolicy": 'none',
        "creditTransferLimits": 50000,
        "enablePayments": True,
    },
    "gateways": {
        "monnify": {
            "enabled": True,
            "publicKey": '',
            "secretKey": '',
            "webhookStatus": 'inactive'
        },
        "flutterwave": {
            "enabled": False,
            "publicKey": '',
            "secretKey": '',
            "webhookStatus": 'inactive'
        },
    },
    "email": {
        "smtpHost": '',
        "smtpPort": 587,
        "username": '',
        "fromEmail": 'noreply@qorebit.com',
        "deliveryStatus": 'inactive',
    },
    "security": {
        "require2FA": True,
        "sessionTimeout": 60,
        "maxLoginAttempts": 5,
        "passwordStrength": 'strong',
        "ipAllowlist": [],
    },
    "rate_limiting": {
        "globalRateLimit": 1000,
        "burstLimit": 50,
        "adminRateLimit": 100,
        "enableRateLimiting": True,
    },
    "integrations": {
        "mono": {
            "enabled": False,
            "apiKey": '',
            "status": 'inactive',
        },
        "postmark": {
            "enabled": False,
            "apiKey": '',
            "status": 'inactive',
        },
        "webhooks": [],
        "eventStreams": {
            "enabled": False,
            "provider": 'internal',
            "endpoint": '',
            "status": 'inactive'
        },
    },
    "compliance": {
        "dataResidency": 'ng',
        "retentionPolicy": {
            "auditLogs": 365,
            "modelLogs": 90,
            "userActivity": 180
        },
        "allowExports": True,
        "autoArchiving": True,
    }
}

# Response Schema with proper aliasing
class PlatformSettingsResponse(SQLModel):
    general: dict
    notifications: dict
    payments: dict
    gateways: dict
    email: dict
    security: dict
    rateLimiting: dict = Field(alias="rate_limiting")
    integrations: dict
    compliance: dict
    updatedAt: datetime = Field(alias="updated_at")

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

@router.get("/public")
def get_public_platform_settings(session: SessionDep) -> Any:
    """
    Get public platform settings (unauthenticated).
    Returns only general settings like platform name and status.
    """
    try:
        settings = session.exec(select(PlatformSettings)).first()
        
        default_general = DEFAULT_SETTINGS["general"]
        
        if not settings:
            return {"general": default_general}
            
        # Defensive programming: columns could be None if row was created partially
        general = settings.general or {}
        payments = settings.payments or {}
            
        return {
            "general": {
                "platformName": general.get("platformName", default_general["platformName"]),
                "systemStatus": general.get("systemStatus", default_general["systemStatus"]),
            },
            "payments": {
                "minCreditAmount": payments.get("minCreditAmount", DEFAULT_SETTINGS["payments"]["minCreditAmount"]),
                "nairaToCreditRate": payments.get("nairaToCreditRate", DEFAULT_SETTINGS["payments"]["nairaToCreditRate"]),
                "enablePayments": payments.get("enablePayments", DEFAULT_SETTINGS["payments"]["enablePayments"]),
            }
        }
    except Exception as e:
        # Log and return defaults if DB query fails
        print(f"⚠️ Error fetching platform settings: {e}")
        return {"general": DEFAULT_SETTINGS["general"]}

@router.get("", response_model=PlatformSettingsResponse, response_model_by_alias=True)
def get_platform_settings(
    session: SessionDep,
    current_user: Any = Depends(get_current_active_superuser),
) -> Any:
    """
    Get platform settings.
    If not initialized, initializes with defaults.
    """
    settings = session.exec(select(PlatformSettings)).first()
    
    if not settings:
        # Initialize with defaults
        settings = PlatformSettings(
            general=DEFAULT_SETTINGS["general"],
            notifications=DEFAULT_SETTINGS["notifications"],
            payments=DEFAULT_SETTINGS["payments"],
            gateways=DEFAULT_SETTINGS["gateways"],
            email=DEFAULT_SETTINGS["email"],
            security=DEFAULT_SETTINGS["security"],
            rate_limiting=DEFAULT_SETTINGS["rate_limiting"],
            integrations=DEFAULT_SETTINGS["integrations"],
            compliance=DEFAULT_SETTINGS["compliance"],
            updated_by=current_user.id
        )
        session.add(settings)
        session.commit()
        session.refresh(settings)
    else:
        # Ensure all sections from DEFAULT_SETTINGS are present
        # and all keys within those sections are also present
        changed = False
        for section, defaults in DEFAULT_SETTINGS.items():
            current_val = getattr(settings, section, None)
            if current_val is None:
                setattr(settings, section, defaults)
                changed = True
            elif isinstance(defaults, dict) and isinstance(current_val, dict):
                # Check for missing keys in the section
                for key, val in defaults.items():
                    if key not in current_val:
                        current_val[key] = val
                        changed = True
        
        if changed:
            session.add(settings)
            session.commit()
            session.refresh(settings)

    return settings

@router.patch("", response_model=PlatformSettingsResponse, response_model_by_alias=True)
def update_platform_settings(
    *,
    session: SessionDep,
    current_user: Any = Depends(get_current_active_superuser),
    settings_in: PlatformSettingsUpdate,
) -> Any:
    """
    Update platform settings.
    """
    settings = session.exec(select(PlatformSettings)).first()
    if not settings:
        raise HTTPException(status_code=404, detail="Settings not found")

    update_data = settings_in.model_dump(exclude_unset=True, by_alias=False)
    
    # Handle alias manually if needed, but 'by_alias=False' usually gives field name.
    # PlatformSettingsUpdate has 'rateLimiting' alias for 'rate_limiting' field?
    # Let's check PlatformSettingsUpdate definition in models.py
    # It has `rateLimiting = Field(alias="rate_limiting")`.
    # model_dump(by_alias=False) should return `rateLimiting`.
    # But our DB model expects `rate_limiting`.
    # So we need to map `rateLimiting` to `rate_limiting`.
    
    if "rateLimiting" in update_data:
        update_data["rate_limiting"] = update_data.pop("rateLimiting")
    
    # Strip updatedAt from each section dictionary to keep DB clean
    for field, value in update_data.items():
        if isinstance(value, dict):
            value.pop("updatedAt", None)
        setattr(settings, field, value)
    
    settings.updated_at = datetime.now(timezone.utc)
    settings.updated_by = current_user.id
    
    session.add(settings)
    session.commit()
    session.refresh(settings)
    
    return settings
