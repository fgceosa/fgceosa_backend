from fastapi import APIRouter

from app.api.routes import (
    email_test,
    login,
    private,
    users,
    utils,
    roles_permissions,
    payments,
    announcements,
    events,
    dashboard,
    system_settings,
    dues,
    financials,
    notifications,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(notifications.router)
api_router.include_router(payments.router)
api_router.include_router(announcements.router)
api_router.include_router(events.router)
api_router.include_router(dashboard.router)
api_router.include_router(system_settings.router, prefix="/settings/system", tags=["system-settings"])
api_router.include_router(dues.router, prefix="/dues", tags=["dues"])
api_router.include_router(financials.router, prefix="/financials", tags=["financials"])
api_router.include_router(roles_permissions.router, prefix="/roles", tags=["roles-permissions"])


if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
    api_router.include_router(email_test.router, prefix="/email", tags=["email"])
