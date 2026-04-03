"""
Organization Model Library Router
Handles organization-specific model library management.
Allows org admins to enable/disable models for their workspace and set defaults.
"""
from typing import Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, and_, or_
from sqlmodel import select
from sqlalchemy.orm import joinedload
from datetime import datetime, timedelta, timezone
from app.api.deps import SessionDep, CurrentUser
from app.models import (
    AIModel, OrganizationModel, OrganizationMember,
    User
)
from pydantic import BaseModel

router = APIRouter(prefix="/organizations", tags=["organization-models"])


class OrgModelPublic(BaseModel):
    """Organization-specific model view"""
    id: str
    name: str
    slug: str
    provider: str
    providerSlug: str | None
    description: str
    contextSize: str
    inputPrice: float
    outputPrice: float
    capabilities: list[str]
    status: str
    availability: str
    category: str | None
    bestUseCases: list[str]
    tokenLimits: dict
    compliance: dict
    lifecycle: dict
    lastUpdated: datetime
    # Organization-specific fields
    isEnabled: bool
    isDefault: bool
    isWorkspaceDefault: bool
    usageCount: int


class ToggleModelRequest(BaseModel):
    isEnabled: bool


def get_user_organization_id(session: SessionDep, user: User) -> UUID | None:
    """Get the organization ID for the current user if they are an org member"""
    # Platform super admins can define which organization context they are in
    # but for simplicity, we use their own organization membership if it exists.
    
    # Get user's organization membership
    stmt = select(OrganizationMember).where(
        OrganizationMember.user_id == user.id
    )
    org_member = session.exec(stmt).first()
    
    if not org_member:
        # If no explicit membership but is superuser, we might need a different logic
        # For now, we only allow access if they are a member of an organization.
        return None
        
    return org_member.organization_id


def map_to_org_model_public(
    model: AIModel,
    org_model: OrganizationModel | None,
    usage_count: int = 0
) -> OrgModelPublic:
    """Map AIModel + OrganizationModel to OrgModelPublic"""
    compliance = model.compliance or {}
    if "safetyTags" not in compliance:
        compliance["safetyTags"] = []
    if "piiHandling" not in compliance:
        compliance["piiHandling"] = False
    if "internalNotes" not in compliance:
        compliance["internalNotes"] = ""

    lifecycle = model.lifecycle or {}
    if "statusHistory" not in lifecycle:
        lifecycle["statusHistory"] = []

    is_enabled = org_model.is_enabled if org_model else False
    is_default = org_model.is_default if org_model else False

    return OrgModelPublic(
        id=str(model.id),
        name=model.name,
        slug=model.slug,
        provider=model.provider.name if model.provider else "Unknown",
        providerSlug=model.provider.slug if model.provider else None,
        description=model.description or "",
        contextSize=model.context_size or "Unknown",
        inputPrice=float(model.input_price) if model.input_price else 0.0,
        outputPrice=float(model.output_price) if model.output_price else 0.0,
        capabilities=model.capabilities or [],
        status=model.status or "Unknown",
        availability=model.availability or "Unknown",
        category=model.category,
        bestUseCases=model.best_use_cases or [],
        tokenLimits=model.token_limits or {"rpm": 0, "tpm": 0},
        compliance=compliance,
        lifecycle=lifecycle,
        lastUpdated=model.updated_at,
        isEnabled=is_enabled,
        isDefault=is_default,
        isWorkspaceDefault=is_default,
        usageCount=usage_count
    )


@router.get("/models")
async def get_organization_models(
    session: SessionDep,
    current_user: CurrentUser,
    search: str | None = None
) -> Any:
    """
    Get all models for the organization with their enabled/disabled status.
    Only accessible to org_super_admin users.
    """
    org_id = get_user_organization_id(session, current_user)
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="Only organization administrators can access this endpoint"
        )
    
    # Get all models from the registry
    models_stmt = select(AIModel).options(joinedload(AIModel.provider))
    
    if search:
        models_stmt = models_stmt.where(
            or_(
                AIModel.name.ilike(f"%{search}%"),
                AIModel.slug.ilike(f"%{search}%"),
                AIModel.description.ilike(f"%{search}%")
            )
        )
    
    all_models = session.scalars(models_stmt).all()
    
    # Get organization-specific model settings
    org_models_stmt = select(OrganizationModel).where(
        OrganizationModel.organization_id == org_id
    )
    org_models = session.scalars(org_models_stmt).all()
    org_models_map = {str(om.model_id): om for om in org_models}
    
    # Map to response format
    results = []
    for model in all_models:
        org_model = org_models_map.get(str(model.id))
        # TODO: Calculate actual usage count from copilot configurations
        usage_count = 0
        results.append(map_to_org_model_public(model, org_model, usage_count))
    
    return {"models": results}


@router.get("/models/{model_id}")
async def get_organization_model(
    session: SessionDep,
    current_user: CurrentUser,
    model_id: UUID
) -> Any:
    """Get a single model with organization-specific settings"""
    org_id = get_user_organization_id(session, current_user)
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="Only organization administrators can access this endpoint"
        )
    
    # Get the model
    model = session.scalar(
        select(AIModel)
        .where(AIModel.id == model_id)
        .options(joinedload(AIModel.provider))
    )
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Get organization-specific settings
    org_model = session.scalar(
        select(OrganizationModel).where(
            and_(
                OrganizationModel.organization_id == org_id,
                OrganizationModel.model_id == model_id
            )
        )
    )
    
    # TODO: Calculate actual usage count
    usage_count = 0
    
    return map_to_org_model_public(model, org_model, usage_count)


@router.post("/models/{model_id}/toggle")
async def toggle_organization_model(
    session: SessionDep,
    current_user: CurrentUser,
    model_id: UUID,
    request: ToggleModelRequest
) -> Any:
    """Enable or disable a model for the organization"""
    org_id = get_user_organization_id(session, current_user)
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="Only organization administrators can manage models"
        )
    
    # Verify model exists
    model = session.scalar(select(AIModel).where(AIModel.id == model_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Get or create organization model settings
    org_model = session.scalar(
        select(OrganizationModel).where(
            and_(
                OrganizationModel.organization_id == org_id,
                OrganizationModel.model_id == model_id
            )
        )
    )
    
    if org_model:
        org_model.is_enabled = request.isEnabled
        org_model.updated_at = datetime.now(timezone.utc)
    else:
        org_model = OrganizationModel(
            organization_id=org_id,
            model_id=model_id,
            is_enabled=request.isEnabled,
            is_default=False
        )
        session.add(org_model)
    
    session.commit()
    session.refresh(org_model)
    
    return {
        "success": True,
        "model": {
            "id": str(model_id),
            "isEnabled": org_model.is_enabled
        }
    }


@router.post("/models/{model_id}/set-default")
async def set_organization_default_model(
    session: SessionDep,
    current_user: CurrentUser,
    model_id: UUID
) -> Any:
    """Set a model as the default for the organization"""
    org_id = get_user_organization_id(session, current_user)
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="Only organization administrators can set default models"
        )
    
    # Verify model exists
    model = session.scalar(select(AIModel).where(AIModel.id == model_id))
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    # Get current default
    current_default = session.scalar(
        select(OrganizationModel).where(
            and_(
                OrganizationModel.organization_id == org_id,
                OrganizationModel.is_default == True
            )
        )
    )
    
    previous_default_id = str(current_default.model_id) if current_default else None
    
    # Remove default from current default
    if current_default:
        current_default.is_default = False
        current_default.updated_at = datetime.now(timezone.utc)
    
    # Get or create the new default
    org_model = session.scalar(
        select(OrganizationModel).where(
            and_(
                OrganizationModel.organization_id == org_id,
                OrganizationModel.model_id == model_id
            )
        )
    )
    
    if org_model:
        org_model.is_default = True
        org_model.is_enabled = True  # Auto-enable when setting as default
        org_model.updated_at = datetime.now(timezone.utc)
    else:
        org_model = OrganizationModel(
            organization_id=org_id,
            model_id=model_id,
            is_enabled=True,
            is_default=True
        )
        session.add(org_model)
    
    session.commit()
    
    return {
        "success": True,
        "previousDefaultId": previous_default_id
    }


@router.get("/analytics/models")
async def get_organization_model_analytics(
    session: SessionDep,
    current_user: CurrentUser
) -> Any:
    """Get analytics for organization model usage"""
    org_id = get_user_organization_id(session, current_user)
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="Only organization administrators can access analytics"
        )
    
    # 1. Get enabled models count
    enabled_count = session.scalar(
        select(func.count()).select_from(OrganizationModel).where(
            and_(
                OrganizationModel.organization_id == org_id,
                OrganizationModel.is_enabled == True
            )
        )
    ) or 0
    
    # 2. Get active models (used in last 30 days) and total spend
    from app.models import APIRequest, Project
    
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    # Subquery to get all project IDs for this organization
    project_ids_stmt = select(Project.id).where(Project.org_id == org_id)
    project_ids = session.exec(project_ids_stmt).all()
    
    if not project_ids:
        return {
            "totalSpend": 0.0,
            "spendChangePercentage": 0.0,
            "enabledCount": enabled_count,
            "activeCount": 0,
            "mostPopularModelName": "None"
        }

    # Query usage analytics
    usage_stmt = (
        select(
            func.sum(APIRequest.cost).label("total_cost"),
            func.count(func.distinct(APIRequest.model)).label("active_models"),
        )
        .where(APIRequest.project_id.in_(project_ids))
        .where(APIRequest.created_at >= thirty_days_ago)
    )
    usage_result = session.exec(usage_stmt).first()
    
    total_spend = float(usage_result.total_cost or 0.0)
    active_count = usage_result.active_models or 0
    
    # 3. Get most popular model
    popular_stmt = (
        select(APIRequest.model)
        .where(APIRequest.project_id.in_(project_ids))
        .where(APIRequest.created_at >= thirty_days_ago)
        .group_by(APIRequest.model)
        .order_by(func.count(APIRequest.id).desc())
        .limit(1)
    )
    most_popular_slug = session.exec(popular_stmt).first()
    
    most_popular_model_name = "None"
    if most_popular_slug:
        model_name_stmt = select(AIModel.name).where(AIModel.slug == most_popular_slug)
        most_popular_model_name = session.exec(model_name_stmt).first() or most_popular_slug

    # 4. Calculate spend change percentage (comparing to previous 30 days)
    previous_period_start = thirty_days_ago - timedelta(days=30)
    prev_usage_stmt = (
        select(func.sum(APIRequest.cost))
        .where(APIRequest.project_id.in_(project_ids))
        .where(and_(APIRequest.created_at >= previous_period_start, APIRequest.created_at < thirty_days_ago))
    )
    prev_total_spend = float(session.exec(prev_usage_stmt).first() or 0.0)
    
    spend_change_percentage = 0.0
    if prev_total_spend > 0:
        spend_change_percentage = ((total_spend - prev_total_spend) / prev_total_spend) * 100
    
    return {
        "totalSpend": round(total_spend, 2),
        "spendChangePercentage": round(spend_change_percentage, 1),
        "enabledCount": enabled_count,
        "activeCount": active_count,
        "mostPopularModelName": most_popular_model_name
    }
