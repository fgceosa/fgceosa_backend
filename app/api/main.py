from fastapi import APIRouter

from app.api.routes import (
    ai_chat,
    ai_engine,
    api_keys,
    api_usage,
    credits,
    dashboard,
    email_test,
    login,
    private,
    projects,
    shared_credits,
    team,
    user_dashboard,
    users,
    utils,
    workspace,
    workspace_credit_sharing,
    copilot,
    copilot_documents,
    google_drive,
    notifications,
    api_providers,
    organization_models,
    admin_revenue,
    bulk_credits,
    roles_permissions,
    security,
    audit_logs,
    platform_settings,
    help_center,
    organizations,
    organization_credits,
    platform_organizations,
)
from app.core.config import settings

api_router = APIRouter()
api_router.include_router(login.router)
api_router.include_router(users.router)
api_router.include_router(utils.router)
api_router.include_router(user_dashboard.router)
# api_router.include_router(dashboard.router)  # Deprecated in favor of user_dashboard with admin logic
api_router.include_router(ai_chat.router)
api_router.include_router(ai_engine.router)  # AI Engine endpoints
api_router.include_router(api_keys.router)  # API Keys management
api_router.include_router(credits.router)  # Credit top-up and management
api_router.include_router(shared_credits.router)
api_router.include_router(team.router)
api_router.include_router(projects.router)
api_router.include_router(api_usage.router)
api_router.include_router(workspace.router)  # Workspace management
api_router.include_router(workspace_credit_sharing.router)  # Workspace credit sharing
api_router.include_router(copilot.router)  # Copilot Hub - AI Agents
api_router.include_router(copilot_documents.router)  # Copilot Documents & RAG
api_router.include_router(google_drive.router)  # Google Drive Integration
api_router.include_router(notifications.router)  # User Notifications
api_router.include_router(api_providers.router, tags=["model-registry"]) # Model Library Frontend
api_router.include_router(organization_models.router, tags=["organization-models"]) # Organization Model Management
api_router.include_router(admin_revenue.router) # Revenue Analytics
api_router.include_router(bulk_credits.router) # Bulk Credits & Programs
api_router.include_router(roles_permissions.router, prefix="/roles", tags=["roles-permissions"]) # Roles & Permissions Management
api_router.include_router(security.router, prefix="/security", tags=["security"])
api_router.include_router(audit_logs.router)
api_router.include_router(platform_settings.router, prefix="/admin/platform-settings", tags=["platform-settings"])
api_router.include_router(help_center.router, prefix="/help-center", tags=["help-center"])
api_router.include_router(organizations.router)
api_router.include_router(organization_credits.router)
api_router.include_router(platform_organizations.router)




if settings.ENVIRONMENT == "local":
    api_router.include_router(private.router)
    # Email testing endpoints (only in local environment)
    api_router.include_router(email_test.router, prefix="/email", tags=["email"])
