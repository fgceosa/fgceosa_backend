"""
AI Engine Router

Provides OpenAI-compatible API endpoints for:
- Chat completions (/v1/chat/completions)
- Embeddings (/v1/embeddings)
- Content moderation (/v1/moderations)

Each endpoint:
1. Authenticates the user via Qorebit API key (JWT)
2. Checks available credits
3. Forwards request to RequestyAI
4. Deducts credits based on usage
5. Logs the request
6. Returns the response
"""
import logging
import time
import uuid
import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from decimal import Decimal

from fastapi import APIRouter, HTTPException, status, Body, Header, Request
from pydantic import BaseModel, Field
from sqlmodel import select

from app.api.deps import CurrentUser, CurrentUserFlexible, SessionDep
from app.services.requesty_ai_client import (
    requesty_ai_client,
    RequestyAIException,
    RequestyAITimeoutException,
    RequestyAIRateLimitException,
    RequestyAIInvalidRequestException,
)
from app.credit_repository import (
    check_sufficient_credits,
    process_ai_request_usage,
)
from app.models import APIKey, Project, OrganizationMember, Workspace

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai/v1", tags=["ai-engine"])


# ==================== Pydantic Models ====================

class ChatMessage(BaseModel):
    """Chat message structure"""
    role: str = Field(..., description="Role: system, user, or assistant")
    content: str = Field(..., description="Message content")
    name: Optional[str] = Field(None, description="Optional name of the message author")


class ChatCompletionRequest(BaseModel):
    """Chat completion request body"""
    messages: list[ChatMessage] = Field(..., description="Array of messages")
    model: str = Field(default="gpt-3.5-turbo", description="Model to use")
    temperature: Optional[float] = Field(default=None, ge=0, le=2, description="Sampling temperature")
    max_tokens: Optional[int] = Field(None, description="Maximum tokens to generate")
    top_p: Optional[float] = Field(default=None, ge=0, le=1, description="Nucleus sampling parameter")
    n: Optional[int] = Field(default=None, description="Number of completions to generate")
    stream: Optional[bool] = Field(default=None, description="Stream responses")
    stop: Optional[list[str] | str] = Field(None, description="Stop sequences")
    presence_penalty: Optional[float] = Field(default=None, ge=-2, le=2)
    frequency_penalty: Optional[float] = Field(default=None, ge=-2, le=2)
    user: Optional[str] = Field(None, description="Unique user identifier")


class EmbeddingRequest(BaseModel):
    """Embedding request body"""
    input: str | list[str] = Field(..., description="Text to embed")
    model: str = Field(default="text-embedding-ada-002", description="Model to use")
    encoding_format: Optional[str] = Field(default="float", description="Encoding format")
    user: Optional[str] = Field(None, description="Unique user identifier")


class ModerationRequest(BaseModel):
    """Moderation request body"""
    input: str | list[str] = Field(..., description="Text to moderate")
    model: Optional[str] = Field(default="text-moderation-latest", description="Model to use")


# ==================== Helper Functions ====================

# Models that are currently offered for free
FREE_MODELS = {
    "openai/gpt-4o-mini",
    "openai/gpt-5-mini",
    "openai/gpt-5-nano",
    "deepseek/deepseek-chat",
    "deepseek/deepseek-reasoner",
    "alibaba/qwen-turbo",
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "google/gemini-2.5-flash",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-7b-instruct:free",
}

def is_model_free(model_id: str) -> bool:
    """Check if a model ID is in the free list or contains ':free' suffix"""
    if not model_id:
        return False
    return model_id.lower() in FREE_MODELS or ":free" in model_id.lower()

def handle_requesty_ai_error(error: Exception, endpoint: str) -> None:
    """
    Convert RequestyAI exceptions to HTTP exceptions
    """
    if isinstance(error, RequestyAITimeoutException):
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=f"Request to AI provider timed out: {str(error)}"
        )
    elif isinstance(error, RequestyAIRateLimitException):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"AI provider rate limit exceeded: {str(error)}"
        )
    elif isinstance(error, RequestyAIInvalidRequestException):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid request to AI provider: {str(error)}"
        )
    elif isinstance(error, RequestyAIException):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"AI provider error: {str(error)}"
        )
    else:
        logger.error(f"Unexpected error in {endpoint}: {str(error)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(error)}"
        )


# ==================== Endpoints ====================

@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    request_body: ChatCompletionRequest,
    current_user: CurrentUserFlexible,
    session: SessionDep,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_organization_id: Optional[uuid.UUID] = Header(None, alias="X-Organization-Id"),
    x_project_id: Optional[uuid.UUID] = Header(None, alias="X-Project-Id"),
) -> Dict[str, Any]:
    """
    Create a chat completion using RequestyAI

    This endpoint:
    1. Validates the user's authentication (via JWT or API Key)
    2. Checks available credits
    3. Forwards the request to RequestyAI
    4. Deducts credits based on token usage
    5. Logs the request
    6. Returns the response

    Authentication:
    - Web App: Authorization: Bearer <JWT_TOKEN>
    - External Apps: Authorization: Bearer qb_live_XXXXXXXX

    Compatible with OpenAI Chat Completions API format.
    """
    start_time = time.time()

    # Identifiers for tracking and credit deduction
    project_id = x_project_id
    api_key_record = None
    organization_id = x_organization_id
    
    # 1. Detect Context from API Key if used
    api_key_str = None
    if authorization:
        api_key_str = authorization.replace("Bearer ", "").strip()
    elif x_api_key:
        api_key_str = x_api_key.strip()
    
    if api_key_str and api_key_str.startswith("qb_live_"):
        # Hash the API key
        key_hash = hashlib.sha256(api_key_str.encode()).hexdigest()

        # Find the API key record
        api_key_stmt = select(APIKey).where(APIKey.key_hash == key_hash)
        api_key_record = session.exec(api_key_stmt).first()

        if api_key_record:
            # Priority 1: Project explicitly linked to this API key (only if x_project_id not provided)
            if not project_id:
                project_stmt = select(Project).where(Project.api_key_id == api_key_record.id)
                project = session.exec(project_stmt).first()
                if project:
                    project_id = project.id
                    if not organization_id:
                        organization_id = project.org_id
                
            # Priority 2: If no org linked to project, or no project, use API key owner's active org (if Admin)
            if not organization_id:
                member_stmt = select(OrganizationMember).where(
                    OrganizationMember.user_id == api_key_record.user_id,
                    OrganizationMember.status == "active"
                ).limit(1)
                member = session.exec(member_stmt).first()
                if member and member.role in ["org_super_admin", "org_admin"]:
                    organization_id = member.organization_id
            
            if organization_id:
                logger.info(f"Resolved organization_id: {organization_id} from API key")
            if project_id:
                logger.info(f"Resolved project_id: {project_id} from API key")

    # 1b. Fallback for JWT users
    # Notice: We no longer auto-resolve organization_id for admins here.
    # Users should use their personal wallet by default. 
    # Organization wallet is used if provided in X-Organization-Id header (e.g. via Org Workspaces).

    # 1c. Resolve Workspace (for usage breakdown)
    workspace_id = None
    if organization_id:
        # Try to find a workspace for this org
        # If project_id provided, we could try to find workspace linked to it, 
        # but for now let's just use the first/default workspace of the org
        ws_stmt = select(Workspace).where(Workspace.organization_id == organization_id).order_by(Workspace.created_at)
        workspace = session.exec(ws_stmt).first()
        if workspace:
            workspace_id = workspace.id
            logger.debug(f"Defaulted to workspace_id: {workspace_id} for org: {organization_id}")

    # 2. Check if model is free or requires credits
    is_free = is_model_free(request_body.model)
    
    # 3. Perform credit check (only if not a free model)
    if not is_free:
        check_sufficient_credits(
            session=session,
            user_id=current_user.id,
            organization_id=organization_id,
            estimated_cost=Decimal("0.01")
        )
    else:
        logger.info(f"Skipping credit check for free model: {request_body.model}")

    # Prepare payload for RequestyAI
    from app.services.requesty_ai import requesty_service
    
    # Normalize the model name before sending to RequestyAI
    normalized_model = requesty_service._normalize_model(request_body.model)
    payload = request_body.model_dump(exclude_none=True)
    payload["model"] = normalized_model

    try:
        # Forward request to RequestyAI
        logger.info(f"User {current_user.email} requesting chat completion with model {normalized_model}")
        response = await requesty_ai_client.chat_completion(payload)

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Extract usage information
        usage = response.get("usage", {})
        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        model_used = response.get("model", request_body.model)

        # Calculate cost using REQUESTED model (not response model)
        # RequestyAI returns versioned names like "gpt-5-2025-08-07"
        # but we need to use the original requested model for pricing
        cost = requesty_ai_client.calculate_cost_from_usage(
            model=normalized_model,  # Use requested model for accurate pricing
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        # Process usage: deduct credits and log request
        transaction, api_request = process_ai_request_usage(
            session=session,
            user_id=current_user.id,
            project_id=project_id,  # Use project linked to API key, or None for default
            model=model_used,
            endpoint="/ai/v1/chat/completions",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            response_time_ms=response_time_ms,
            organization_id=organization_id,  # Deduct from org wallet
            workspace_id=workspace_id,  # Assign to workspace for breakdown
            ip_address=request.client.host,
            origin=request.headers.get("origin") or request.headers.get("referer"),
        )

        # Update API key usage statistics if request was made via API key
        if api_key_record:
            api_key_record.total_requests += 1
            api_key_record.total_cost += cost
            api_key_record.last_used_at = datetime.now(timezone.utc)
            session.add(api_key_record)
            session.commit()
            logger.info(f"Updated API key {api_key_record.id} usage: requests={api_key_record.total_requests}, cost=${api_key_record.total_cost}")

        logger.info(
            f"Chat completion successful. User: {current_user.email}, "
            f"Tokens: {prompt_tokens + completion_tokens}, Cost: ${cost:.4f}"
        )

        # Return the RequestyAI response as-is (OpenAI compatible)
        return response

    except (RequestyAIException, RequestyAITimeoutException,
            RequestyAIRateLimitException, RequestyAIInvalidRequestException) as e:
        handle_requesty_ai_error(e, "/chat/completions")

    except Exception as e:
        handle_requesty_ai_error(e, "/chat/completions")


@router.post("/embeddings")
async def create_embeddings(
    request: Request,
    request_body: EmbeddingRequest,
    current_user: CurrentUserFlexible,
    session: SessionDep,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_organization_id: Optional[uuid.UUID] = Header(None, alias="X-Organization-Id"),
    x_project_id: Optional[uuid.UUID] = Header(None, alias="X-Project-Id"),
) -> Dict[str, Any]:
    """
    Create embeddings using RequestyAI

    This endpoint:
    1. Validates the user's authentication (via JWT or API Key)
    2. Checks available credits
    3. Forwards the request to RequestyAI
    4. Deducts credits based on usage
    5. Logs the request
    6. Returns the response

    Authentication:
    - Web App: Authorization: Bearer <JWT_TOKEN>
    - External Apps: Authorization: Bearer qb_live_XXXXXXXX

    Compatible with OpenAI Embeddings API format.
    """
    start_time = time.time()

    # Identifiers for tracking and credit deduction
    project_id = x_project_id
    api_key_record = None
    organization_id = x_organization_id
    
    # 1. Detect Context from API Key
    api_key_str = None
    if authorization:
        api_key_str = authorization.replace("Bearer ", "").strip()
    elif x_api_key:
        api_key_str = x_api_key.strip()
        
    if api_key_str and api_key_str.startswith("qb_live_"):
        key_hash = hashlib.sha256(api_key_str.encode()).hexdigest()

        api_key_stmt = select(APIKey).where(APIKey.key_hash == key_hash)
        api_key_record = session.exec(api_key_stmt).first()

        if api_key_record:
            # Priority 1: Project explicitly linked to this API key (only if x_project_id not provided)
            if not project_id:
                project_stmt = select(Project).where(Project.api_key_id == api_key_record.id)
                project = session.exec(project_stmt).first()
                if project:
                    project_id = project.id
                    if not organization_id:
                        organization_id = project.org_id
                
            if not organization_id:
                member_stmt = select(OrganizationMember).where(
                    OrganizationMember.user_id == api_key_record.user_id,
                    OrganizationMember.status == "active"
                ).limit(1)
                member = session.exec(member_stmt).first()
                if member:
                    organization_id = member.organization_id
            
            if organization_id:
                logger.info(f"Resolved organization_id: {organization_id} from API key (Embeddings)")
            if project_id:
                logger.info(f"Resolved project_id: {project_id} from API key (Embeddings)")
    
    # 1b. Context Fallback
    # Notice: We no longer auto-resolve organization_id for JWT users here.
    # Users should use their personal wallet by default.

    # Resolve Workspace
    workspace_id = None
    if organization_id:
        ws_stmt = select(Workspace).where(Workspace.organization_id == organization_id).order_by(Workspace.created_at)
        workspace = session.exec(ws_stmt).first()
        if workspace:
            workspace_id = workspace.id
            

    # 2. Check if model is free
    is_free = is_model_free(request_body.model)
    
    # 3. Perform credit check
    if not is_free:
        check_sufficient_credits(
            session=session,
            user_id=current_user.id,
            organization_id=organization_id,
            estimated_cost=Decimal("0.01")
        )

    # Prepare payload for RequestyAI
    payload = request_body.model_dump(exclude_none=True)

    try:
        # Forward request to RequestyAI
        logger.info(f"User {current_user.email} requesting embeddings with model {request_body.model}")
        response = await requesty_ai_client.create_embeddings(payload)

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Extract usage information
        usage = response.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        model_used = response.get("model", request_body.model)

        # For embeddings, all tokens are "prompt tokens"
        prompt_tokens = total_tokens
        completion_tokens = 0

        # Calculate cost
        cost = requesty_ai_client.calculate_cost_from_usage(
            model=model_used,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens
        )

        # Process usage
        transaction, api_request = process_ai_request_usage(
            session=session,
            user_id=current_user.id,
            project_id=project_id, # Use project ID if available
            model=model_used,
            endpoint="/ai/v1/embeddings",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost=cost,
            response_time_ms=response_time_ms,
            organization_id=organization_id, # Deduct from org wallet
            workspace_id=workspace_id,  # Assign to workspace
            ip_address=request.client.host,
            origin=request.headers.get("origin") or request.headers.get("referer"),
        )

        # Update API key usage statistics if request was made via API key
        if api_key_record:
            api_key_record.total_requests += 1
            api_key_record.total_cost += cost
            api_key_record.last_used_at = datetime.now(timezone.utc)
            session.add(api_key_record)
            session.commit()
            logger.info(f"Updated API key {api_key_record.id} usage: requests={api_key_record.total_requests}, cost=${api_key_record.total_cost}")

        logger.info(
            f"Embeddings created. User: {current_user.email}, "
            f"Tokens: {total_tokens}, Cost: ${cost:.4f}"
        )

        # Return the RequestyAI response
        return response

    except (RequestyAIException, RequestyAITimeoutException,
            RequestyAIRateLimitException, RequestyAIInvalidRequestException) as e:
        handle_requesty_ai_error(e, "/embeddings")

    except Exception as e:
        handle_requesty_ai_error(e, "/embeddings")


@router.post("/moderations")
async def moderate_content(
    request: Request,
    request_body: ModerationRequest,
    current_user: CurrentUserFlexible,
    session: SessionDep,
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_organization_id: Optional[uuid.UUID] = Header(None, alias="X-Organization-Id"),
    x_project_id: Optional[uuid.UUID] = Header(None, alias="X-Project-Id"),
) -> Dict[str, Any]:
    """
    Moderate content using RequestyAI

    This endpoint:
    1. Validates the user's authentication (via JWT or API Key)
    2. Checks available credits (minimal cost)
    3. Forwards the request to RequestyAI
    4. Deducts credits based on usage
    5. Logs the request
    6. Returns the response

    Authentication:
    - Web App: Authorization: Bearer <JWT_TOKEN>
    - External Apps: Authorization: Bearer qb_live_XXXXXXXX

    Compatible with OpenAI Moderations API format.
    """
    start_time = time.time()

    # Identifiers
    project_id = x_project_id
    api_key_record = None
    organization_id = x_organization_id
    
    # Context Detection
    api_key_str = None
    if authorization:
        api_key_str = authorization.replace("Bearer ", "").strip()
    elif x_api_key:
        api_key_str = x_api_key.strip()
        
    if api_key_str and api_key_str.startswith("qb_live_"):
        key_hash = hashlib.sha256(api_key_str.encode()).hexdigest()

        api_key_stmt = select(APIKey).where(APIKey.key_hash == key_hash)
        api_key_record = session.exec(api_key_stmt).first()

        if api_key_record:
            # Priority 1: Project explicitly linked to this API key (only if x_project_id not provided)
            if not project_id:
                project_stmt = select(Project).where(Project.api_key_id == api_key_record.id)
                project = session.exec(project_stmt).first()
                if project:
                    project_id = project.id
                    if not organization_id:
                        organization_id = project.org_id
                
            if not organization_id:
                member_stmt = select(OrganizationMember).where(
                    OrganizationMember.user_id == api_key_record.user_id,
                    OrganizationMember.status == "active"
                ).limit(1)
                member = session.exec(member_stmt).first()
                if member:
                    organization_id = member.organization_id

            if organization_id:
                logger.info(f"Resolved organization_id: {organization_id} from API key (Moderations)")
            if project_id:
                logger.info(f"Resolved project_id: {project_id} from API key (Moderations)")

    # Fallback for JWT users
    # Notice: We no longer auto-resolve organization_id here.

    # Resolve Workspace
    workspace_id = None
    if organization_id:
        ws_stmt = select(Workspace).where(Workspace.organization_id == organization_id).order_by(Workspace.created_at)
        workspace = session.exec(ws_stmt).first()
        if workspace:
            workspace_id = workspace.id
            

    # Check credits (moderation is usually free/cheap, but still check if not free model)
    is_free = is_model_free(request_body.model or "text-moderation-latest")
    if not is_free:
        check_sufficient_credits(
            session=session,
            user_id=current_user.id,
            organization_id=organization_id,
            estimated_cost=Decimal("0.001")
        )

    # Prepare payload for RequestyAI
    payload = request_body.model_dump(exclude_none=True)

    try:
        # Forward request to RequestyAI
        logger.info(f"User {current_user.email} requesting content moderation")
        response = await requesty_ai_client.moderate_content(payload)

        # Calculate response time
        response_time_ms = int((time.time() - start_time) * 1000)

        # Moderation usually doesn't return usage, estimate based on input
        input_text = request_body.input
        if isinstance(input_text, list):
            estimated_tokens = sum(len(text.split()) for text in input_text)
        else:
            estimated_tokens = len(input_text.split())

        model_used = request_body.model or "text-moderation-latest"

        # Use minimal cost for moderation
        cost = Decimal("0.001")  # Fixed minimal cost

        # Process usage
        transaction, api_request = process_ai_request_usage(
            session=session,
            user_id=current_user.id,
            project_id=project_id, # Use project ID if available
            model=model_used,
            endpoint="/ai/v1/moderations",
            prompt_tokens=estimated_tokens,
            completion_tokens=0,
            cost=cost,
            response_time_ms=response_time_ms,
            organization_id=organization_id, # Deduct from org wallet
            workspace_id=workspace_id,  # Assign to workspace
            ip_address=request.client.host,
            origin=request.headers.get("origin") or request.headers.get("referer"),
        )

        # Update API key usage statistics if request was made via API key
        if api_key_record:
            api_key_record.total_requests += 1
            api_key_record.total_cost += cost
            api_key_record.last_used_at = datetime.now(timezone.utc)
            session.add(api_key_record)
            session.commit()
            logger.info(f"Updated API key {api_key_record.id} usage: requests={api_key_record.total_requests}, cost=${api_key_record.total_cost}")

        logger.info(
            f"Moderation completed. User: {current_user.email}, "
            f"Cost: ${cost:.4f}"
        )

        # Return the RequestyAI response
        return response

    except (RequestyAIException, RequestyAITimeoutException,
            RequestyAIRateLimitException, RequestyAIInvalidRequestException) as e:
        handle_requesty_ai_error(e, "/moderations")

    except Exception as e:
        handle_requesty_ai_error(e, "/moderations")


# ==================== Models List ====================

@router.get("/models")
async def list_models() -> Dict[str, Any]:
    """
    List all available AI models

    Returns models available through RequestyAI with pricing information.
    No authentication required - this is a public endpoint.
    """

    models = [
        # ============ FREE MODELS (No Credit Deduction) ============
        {
            "id": "openai/gpt-5-mini",
            "name": "GPT-5 Mini",
            "provider": "OpenAI",
            "description": "🎁 FREE - 2026 Flagship Mini - Ultra-fast and smart.",
            "context_length": 128000,
            "pricing": {"input": 0.00, "output": 0.00},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": True,
        },
        {
            "id": "openai/gpt-4o-mini",
            "name": "GPT-4o Mini",
            "provider": "OpenAI",
            "description": "🎁 FREE - Extremely fast classic model.",
            "context_length": 128000,
            "pricing": {"input": 0.00, "output": 0.00},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": True,
        },
        {
            "id": "deepseek/deepseek-chat",
            "name": "DeepSeek Chat",
            "provider": "DeepSeek",
            "description": "🎁 FREE - Flagship Chinese LLM.",
            "context_length": 64000,
            "pricing": {"input": 0.00, "output": 0.00},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": True,
        },

        # ============ PAID MODELS (Requires Credits) ============
        {
            "id": "openai/gpt-5",
            "name": "GPT-5",
            "provider": "OpenAI",
            "description": "2026 Ultimate Intelligence - The peak of LLM performance.",
            "context_length": 128000,
            "pricing": {"input": 5.00, "output": 15.00},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": False,
        },
        {
            "id": "openai/o1",
            "name": "O1 Flagship",
            "provider": "OpenAI",
            "description": "Advanced reasoning model for complex logical tasks.",
            "context_length": 128000,
            "pricing": {"input": 15.00, "output": 60.00},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": False,
        },
        {
            "id": "anthropic/claude-sonnet-4",
            "name": "Claude 4 Sonnet",
            "provider": "Anthropic",
            "description": "Anthropic's 2026 flagship for creative and logic tasks.",
            "context_length": 250000,
            "pricing": {"input": 3.00, "output": 15.00},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": False,
        },
        {
            "id": "anthropic/claude-haiku-4-5",
            "name": "Claude 4.5 Haiku",
            "provider": "Anthropic",
            "description": "Near-instant response for data extraction and high volume.",
            "context_length": 200000,
            "pricing": {"input": 0.25, "output": 1.25},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": False,
        },
        {
            "id": "google/gemini-pro-2.5",
            "name": "Gemini 2.5 Pro",
            "provider": "Google",
            "description": "Google's 2026 powerhouse with massive 2M context window.",
            "context_length": 2000000,
            "pricing": {"input": 1.25, "output": 5.00},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": False,
        },
        {
            "id": "google/gemini-pro-1.5",
            "name": "Gemini 1.5 Pro",
            "provider": "Google",
            "description": "High context model for extensive data analysis.",
            "context_length": 1000000,
            "pricing": {"input": 1.25, "output": 5.00},
            "supports_streaming": True,
            "supports_functions": True,
            "is_free": False,
        }
    ]

    return {
        "models": models,
        "total": len(models),
        "currency": "USD",
        "pricing_unit": "per 1M tokens",
    }


# ==================== Health Check ====================

@router.get("/health")
async def health_check(current_user: CurrentUserFlexible, session: SessionDep) -> Dict[str, Any]:
    """
    Check AI Engine health and user's credit balance

    Authentication:
    - Web App: Authorization: Bearer <JWT_TOKEN>
    - External Apps: Authorization: Bearer qb_live_XXXXXXXX

    Returns:
        Status and user's current credit balance
    """
    from app.credit_repository import get_user_credit_balance

    balance = get_user_credit_balance(session=session, user_id=current_user.id)

    return {
        "status": "healthy",
        "service": "AI Engine",
        "user": current_user.email,
        "credit_balance": float(balance),
    }
