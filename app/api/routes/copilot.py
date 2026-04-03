
"""
Copilot Hub API routes
"""
import uuid
from typing import Any, Annotated, List

from fastapi import APIRouter, Depends, Query, HTTPException, Body
from sqlmodel import Session

from app.api.deps import (
    CurrentUser, get_db, get_copilot_db, 
    get_current_active_superuser, RequiresPermission, CopilotSessionDep,
    get_current_user
)
from app.models import User
from app.copilot.schemas import (
    CopilotCreate, CopilotUpdate, CopilotPublic, CopilotsPublic,
    ShareCopilotRequest, CopilotSuggestionsResponse, CopilotWorkspaceAssignment,
    ConversationCreate, ConversationUpdate, ConversationPublic, ConversationsPublic,
    MessagePublic, MessagesPublic, MessageUpdate, SendMessageRequest, SendMessageResponse, MessageFeedback
)
from app.services.copilot_service import copilot_service
from app.services.copilot_chat_service import copilot_chat_service
from app.utils.permissions import user_has_any_role

router = APIRouter(prefix="/copilots", tags=["Copilot Hub"])

# ==================== Copilot CRUD ====================

@router.post("", response_model=CopilotPublic, status_code=201)
async def create_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: User = Depends(RequiresPermission("copilot:create")),
    copilot_in: CopilotCreate,
) -> Any:
    """Create a new copilot/agent."""
    return await copilot_service.create_copilot(session, main_session, current_user, copilot_in)


@router.get("", response_model=CopilotsPublic)
async def list_copilots(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: str | None = Query(None),
    visibility: str | None = Query(None),
    search: str | None = Query(None),
    workspace_id: uuid.UUID | None = Query(None),
    is_featured: bool | None = Query(None),
) -> Any:
    """List copilots accessible to the current user."""
    filters = {
        "category": category,
        "visibility": visibility,
        "search": search,
        "workspace_id": workspace_id,
        "is_featured": is_featured
    }
    return await copilot_service.list_accessible_copilots(session, main_session, current_user, skip, limit, filters)

@router.get("/admin/list", response_model=CopilotsPublic)
async def list_all_copilots_admin(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: User = Depends(RequiresPermission("copilot:manage")),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    category: str | None = Query(None),
    visibility: str | None = Query(None),
    search: str | None = Query(None),
    workspace_id: uuid.UUID | None = Query(None),
    is_featured: bool | None = Query(None),
    status: str | None = Query(None),
) -> Any:
    """List ALL copilots (Admin only)."""
    filters = {
        "category": category,
        "visibility": visibility,
        "search": search,
        "workspace_id": workspace_id,
        "is_featured": is_featured,
        "status": status
    }
    return await copilot_service.list_all_copilots_admin(session, main_session, skip, limit, filters)

@router.get("/featured", response_model=CopilotsPublic)
async def list_featured_copilots(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=50),
) -> Any:
    """List featured, official and platform super admin created public copilots."""
    return await copilot_service.list_featured_copilots(session, main_session, skip, limit)

@router.get("/my", response_model=CopilotsPublic)
async def list_my_copilots(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
) -> Any:
    """List copilots created by the current user."""
    return await copilot_service.list_my_copilots(session, main_session, current_user, skip, limit)

@router.get("/{copilot_id}", response_model=CopilotPublic)
async def get_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
) -> Any:
    """Get a specific copilot by ID."""
    return await copilot_service.get_copilot(session, main_session, copilot_id, current_user)

@router.get("/{copilot_id}/generate-suggestions", response_model=CopilotSuggestionsResponse)
async def generate_copilot_suggestions(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
) -> Any:
    """Generate dynamic suggested prompts."""
    return await copilot_service.generate_suggestions(session, copilot_id, current_user)

@router.patch("/{copilot_id}", response_model=CopilotPublic)
async def update_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    copilot_id: uuid.UUID,
    copilot_in: CopilotUpdate,
) -> Any:
    """Update a copilot's configuration."""
    return await copilot_service.update_copilot(session, main_session, copilot_id, current_user, copilot_in)

@router.delete("/{copilot_id}", status_code=204)
async def delete_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    copilot_id: uuid.UUID,
) -> None:
    """Delete a copilot."""
    await copilot_service.delete_copilot(session, main_session, copilot_id, current_user)

@router.post("/{copilot_id}/duplicate", response_model=CopilotPublic, status_code=201)
async def duplicate_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    copilot_id: uuid.UUID,
) -> Any:
    """Duplicate a copilot."""
    return await copilot_service.duplicate_copilot(session, main_session, copilot_id, current_user)

@router.post("/{copilot_id}/activate", response_model=CopilotPublic)
async def activate_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
) -> Any:
    """Activate a copilot."""
    return await copilot_service.update_status(session, main_session, copilot_id, current_user, "active")

@router.post("/{copilot_id}/pause", response_model=CopilotPublic)
async def pause_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
) -> Any:
    """Pause a copilot (set to inactive)."""
    return await copilot_service.update_status(session, main_session, copilot_id, current_user, "inactive")

@router.post("/{copilot_id}/disable", response_model=CopilotPublic)
async def disable_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
) -> Any:
    """Disable a copilot (Admin-only feel, but owner can also disable their own)."""
    return await copilot_service.update_status(session, main_session, copilot_id, current_user, "disabled")

@router.put("/{copilot_id}/workspaces", response_model=CopilotPublic)
@router.post("/{copilot_id}/workspaces", response_model=CopilotPublic)
async def assign_copilot_to_workspaces(
    *,
    session: CopilotSessionDep,
    main_session: Session = Depends(get_db),
    copilot_id: uuid.UUID,
    assignment: CopilotWorkspaceAssignment,
    current_user: User = Depends(get_current_user)
) -> Any:
    """Assign/Sync copilot to multiple workspaces."""
    return await copilot_service.assign_to_workspaces(
        session, main_session, copilot_id, current_user, assignment.workspace_ids
    )

# ==================== Copilot CRUD ==================== (continued)

@router.post("/{copilot_id}/share")
async def share_copilot(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    share_request: ShareCopilotRequest,
) -> Any:
    """Share copilot with other users via email."""
    return await copilot_service.share_copilot(session, main_session, copilot_id, current_user, share_request)


# ==================== Conversation Endpoints ====================

@router.post("/{copilot_id}/conversations", response_model=ConversationPublic, status_code=201)
async def create_conversation(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    conversation_in: ConversationCreate | None = None,
) -> Any:
    """Create a new conversation with a copilot."""
    return await copilot_chat_service.create_conversation(session, copilot_id, current_user, conversation_in)

@router.get("/{copilot_id}/conversations", response_model=ConversationsPublic)
async def list_conversations(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: bool | None = Query(None),
) -> Any:
    """List conversations for a copilot."""
    return await copilot_chat_service.list_conversations(session, copilot_id, current_user, skip, limit, is_active)

@router.get("/conversations/{conversation_id}", response_model=ConversationPublic)
async def get_conversation(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
) -> Any:
    """Get a specific conversation."""
    return await copilot_chat_service.get_conversation(session, conversation_id, current_user)

@router.patch("/conversations/{conversation_id}", response_model=ConversationPublic)
async def update_conversation(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    conversation_in: ConversationUpdate,
) -> Any:
    """Update a conversation."""
    return await copilot_chat_service.update_conversation(session, conversation_id, current_user, conversation_in)

@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
) -> None:
    """Delete a conversation."""
    await copilot_chat_service.delete_conversation(session, conversation_id, current_user)

# ==================== Message Endpoints ====================

@router.get("/conversations/{conversation_id}/messages", response_model=MessagesPublic)
async def list_messages(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
) -> Any:
    """List messages in a conversation."""
    return await copilot_chat_service.list_messages(session, conversation_id, current_user, skip, limit)

@router.post("/conversations/{conversation_id}/messages/{message_id}/feedback")
async def submit_message_feedback(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    feedback: MessageFeedback,
) -> dict:
    """Submit feedback for a message."""
    return await copilot_chat_service.submit_feedback(session, conversation_id, message_id, current_user, feedback)

@router.patch("/conversations/{conversation_id}/messages/{message_id}", response_model=MessagePublic)
async def update_message(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    message_in: MessageUpdate,
) -> Any:
    """Update a message's content."""
    return await copilot_chat_service.update_message(session, conversation_id, message_id, current_user, message_in.content)

@router.delete("/conversations/{conversation_id}/messages/{message_id}/after")
async def delete_messages_after(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
) -> dict:
    """Delete all messages in a conversation after a specific message."""
    return await copilot_chat_service.delete_messages_after(session, conversation_id, message_id, current_user)


# ==================== Chat Endpoint (Send Message) ====================

@router.post("/{copilot_id}/chat", response_model=SendMessageResponse)
async def send_message(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    message_in: SendMessageRequest,
) -> Any:
    """Send a message to a copilot and get a response."""
    return await copilot_chat_service.send_message(session, main_session, copilot_id, current_user, message_in)


# ==================== Analytics & Activity Endpoints ====================

@router.get("/{copilot_id}/analytics")
async def get_copilot_analytics(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: User = Depends(RequiresPermission("copilot:analytics")),
    copilot_id: uuid.UUID,
) -> dict:
    """Get analytics data for a copilot."""
    from app.services.copilot_analytics_service import copilot_analytics_service
    return await copilot_analytics_service.get_analytics(session, copilot_id, current_user)


@router.get("/{copilot_id}/activity")
async def get_copilot_activity(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
) -> dict:
    """Get recent activity for a copilot."""
    from app.services.copilot_analytics_service import copilot_analytics_service
    return await copilot_analytics_service.get_activity(session, copilot_id, current_user, skip, limit)
