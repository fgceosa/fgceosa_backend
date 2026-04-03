
"""
API Providers Router
Handles fetching models and providers for the Model Library frontend page.
Also handles Model Registry management for HQ.
"""
from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func
from sqlalchemy.orm import joinedload
from app.api.deps import get_db, SessionDep, CurrentUser, get_current_active_superuser, RequiresPermission
from app.models import (
    AIModel, AIProvider, AIModelPublic, AIProviderPublic,
    AIModelsPublic, AIProvidersPublic, AIModelCreate, AIModelUpdate
)

router = APIRouter(prefix="/registry", tags=["model-registry"])

def map_ai_model_to_public(model: AIModel) -> AIModelPublic:
    """Helper to manually map AIModel to AIModelPublic schema"""
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

    return AIModelPublic(
        id=model.id,
        name=model.name,
        slug=model.slug,
        providerId=model.provider_id,
        provider=model.provider.name if model.provider else None,
        providerSlug=model.provider.slug if model.provider else None,
        description=model.description,
        contextSize=model.context_size,
        inputPrice=float(model.input_price),
        outputPrice=float(model.output_price),
        capabilities=model.capabilities or [],
        status=model.status,
        availability=model.availability,
        category=model.category,
        bestUseCases=model.best_use_cases or [],
        tokenLimits=model.token_limits or {"rpm": 0, "tpm": 0},
        compliance=compliance,
        lifecycle=lifecycle,
        lastUpdated=model.updated_at
    )

# ==================== Public Model Library Endpoints ====================

@router.get("/models", response_model=AIModelsPublic)
async def get_models(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100,
    category: str | None = None,
    provider_id: str | None = None
) -> Any:
    """Get all models for the library"""
    statement = select(AIModel).options(joinedload(AIModel.provider))
    if category:
        statement = statement.where(AIModel.category == category)
    if provider_id:
        try:
            p_id = UUID(provider_id)
            statement = statement.where(AIModel.provider_id == p_id)
        except (ValueError, AttributeError):
            pass
            
    models = session.scalars(statement.offset(skip).limit(limit)).all()
    count_statement = select(func.count()).select_from(AIModel)
    if category:
        count_statement = count_statement.where(AIModel.category == category)
    count = session.scalar(count_statement) or 0

    results = [map_ai_model_to_public(m) for m in models]
    return {"models": results, "total": count}


@router.get("/models/{model_id_or_slug}", response_model=AIModelPublic)
async def get_model(
    session: SessionDep,
    model_id_or_slug: str
) -> Any:
    """Get a single model by ID or slug"""
    try:
        m_id = UUID(model_id_or_slug)
        statement = select(AIModel).where(AIModel.id == m_id).options(joinedload(AIModel.provider))
    except (ValueError, AttributeError):
        statement = select(AIModel).where(AIModel.slug == model_id_or_slug).options(joinedload(AIModel.provider))
    
    model = session.scalar(statement)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    return map_ai_model_to_public(model)


@router.get("/providers", response_model=AIProvidersPublic)
async def get_providers(
    session: SessionDep,
    skip: int = 0,
    limit: int = 100
) -> Any:
    """Get all providers"""
    statement = select(AIProvider).offset(skip).limit(limit)
    providers = session.scalars(statement).all()
    count = session.scalar(select(func.count()).select_from(AIProvider)) or 0
    
    return {"providers": providers, "total": count}


# ==================== Model Registry (HQ Management) Endpoints ====================

@router.post("/register", response_model=AIModelPublic, dependencies=[Depends(get_current_active_superuser)])
async def register_model(
    session: SessionDep,
    model_in: AIModelCreate
) -> Any:
    """Register a new AI model in the global registry (HQ Only)"""
    existing = session.exec(select(AIModel).where(AIModel.slug == model_in.slug)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Model with this slug already exists")
    
    db_model = AIModel.model_validate(model_in)
    session.add(db_model)
    session.commit()
    session.refresh(db_model)
    
    # Reload with provider
    statement = select(AIModel).where(AIModel.id == db_model.id).options(joinedload(AIModel.provider))
    db_model = session.scalar(statement)
    
    return map_ai_model_to_public(db_model)


@router.patch("/update/{model_id}", response_model=AIModelPublic, dependencies=[Depends(get_current_active_superuser)])
async def update_model_registry(
    session: SessionDep,
    model_id: UUID,
    model_in: AIModelUpdate
) -> Any:
    """Update model registry details (HQ Only)"""
    db_model = session.scalar(select(AIModel).where(AIModel.id == model_id).options(joinedload(AIModel.provider)))
    if not db_model:
        raise HTTPException(status_code=404, detail="Model not found")
    
    update_data = model_in.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_model, key, value)
    
    session.add(db_model)
    session.commit()
    session.refresh(db_model)
    
    return map_ai_model_to_public(db_model)


@router.get("/analytics", dependencies=[Depends(get_current_active_superuser)])
async def get_registry_analytics(session: SessionDep) -> Any:
    """Get global registry analytics (HQ Only)"""
    total_models = session.scalar(select(func.count()).select_from(AIModel)) or 0
    approved = session.scalar(select(func.count()).select_from(AIModel).where(AIModel.status == "Approved")) or 0
    experimental = session.scalar(select(func.count()).select_from(AIModel).where(AIModel.status == "Experimental")) or 0
    deprecated = session.scalar(select(func.count()).select_from(AIModel).where(AIModel.status == "Deprecated")) or 0
    providers = session.scalar(select(func.count()).select_from(AIProvider)) or 0
    
    return {
        "totalModels": total_models,
        "approvedModels": approved,
        "restrictedModels": experimental, # Using experimental as restricted for now
        "deprecatedModels": deprecated,
        "activeProviders": providers
    }

@router.post("/sync-requesty", dependencies=[Depends(get_current_active_superuser)])
async def sync_with_requesty(session: SessionDep) -> Any:
    """Sync model registry with RequestyAI catalog (HQ Only)"""
    from app.services.requesty_sync import requesty_sync_service
    result = await requesty_sync_service.sync_models(session)
    if result.get("status") == "error":
        raise HTTPException(status_code=500, detail=result.get("message"))
    return result


@router.post("/test-connection/{model_id}", dependencies=[Depends(RequiresPermission("model:configure"))])
async def test_connection(
    session: SessionDep,
    model_id: UUID,
    current_user: CurrentUser,
) -> Any:
    """Test connectivity for a specific model (HQ Only)"""
    from app.services.requesty_ai_client import requesty_ai_client
    
    db_model = session.scalar(select(AIModel).where(AIModel.id == model_id))
    if not db_model:
        raise HTTPException(status_code=404, detail="Model not found")
        
    try:
        # We perform a minimal specific test to verify the model is reachable via the gateway
        # Using a very simple prompt to minimize cost and latency
        payload = {
            "model": db_model.slug,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 20  # Minimal generation, but >16 for some models
        }
        
        # We use the existing client which handles auth, routing, etc.
        # If this succeeds, the model is connected and authorized.
        await requesty_ai_client.chat_completion(payload)
        
        return {
            "status": "success", 
            "message": f"Successfully connected to {db_model.name} via {db_model.provider_id} provider.",
            "model": db_model.name
        }
        
    except Exception as e:
        # Capture the specific gateway error
        return {
            "status": "error",
            "message": str(e),
            "model": db_model.name
        }
