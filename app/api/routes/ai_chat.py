"""
AI Chat API routes (Refactored)
"""
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session

from app.api.deps import CurrentUser, get_db
from app.models import (
    AIChatCreate,
    AIChatUpdate,
    AIChatPublic,
    AIChatListPublic,
    AIChatsPublic,
    AIChatSendMessage,
    AIChatMessageResponse,
    AIChatMessagePublic,
)
from app import chat_repository
from app.services.chat_service import chat_service
from app.api.middleware.rate_limit import rate_limiter

router = APIRouter(prefix="/ai-chat", tags=["AI Chat"])


@router.post("", response_model=AIChatPublic, status_code=201)
async def create_chat(
    *,
    session: Session = Depends(get_db),
    current_user: CurrentUser,
    chat_in: AIChatCreate,
) -> Any:
    """Create a new AI chat conversation."""
    chat = chat_repository.create_chat(
        session=session,
        user_id=current_user.id,
        title=chat_in.title or "New Chat"
    )
    
    return AIChatPublic(
        id=chat.id,
        user_id=chat.user_id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=[]
    )


@router.get("", response_model=AIChatsPublic)
async def list_chats(
    *,
    session: Session = Depends(get_db),
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
) -> Any:
    """Get all AI chats for the current user."""
    count = chat_repository.get_chat_count_by_user_id(session, current_user.id)
    chats = chat_repository.get_chats_by_user_id(session, current_user.id, skip, limit)
    
    chat_list = []
    for chat in chats:
        last_msg = chat_repository.get_last_message_by_chat_id(session, chat.id)
        preview = None
        if last_msg:
            content = last_msg.content
            preview = (content[:100] + "...") if len(content) > 100 else content
        
        chat_list.append(AIChatListPublic(
            id=chat.id,
            user_id=chat.user_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            last_message_preview=preview
        ))
    
    return AIChatsPublic(data=chat_list, count=count)


@router.get("/search", response_model=AIChatsPublic)
async def search_chats(
    *,
    session: Session = Depends(get_db),
    current_user: CurrentUser,
    q: str = Query(..., min_length=1),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
) -> Any:
    """Search AI chats by title or message content."""
    query_lower = q.lower()
    # Repository search could be optimized here
    all_chats = chat_repository.get_chats_by_user_id(session, current_user.id, limit=1000)
    
    matching_chats = []
    for chat in all_chats:
        if query_lower in chat.title.lower():
            matching_chats.append(chat)
            continue
        
        messages = chat_repository.get_messages_by_chat_id(session, chat.id)
        if any(query_lower in msg.content.lower() for msg in messages):
            matching_chats.append(chat)
    
    matching_chats.sort(key=lambda c: c.updated_at, reverse=True)
    total_count = len(matching_chats)
    paginated_chats = matching_chats[skip:skip + limit]
    
    chat_list = []
    for chat in paginated_chats:
        last_msg = chat_repository.get_last_message_by_chat_id(session, chat.id)
        preview = None
        if last_msg:
            content = last_msg.content
            preview = (content[:100] + "...") if len(content) > 100 else content
            
        chat_list.append(AIChatListPublic(
            id=chat.id,
            user_id=chat.user_id,
            title=chat.title,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
            last_message_preview=preview
        ))
    
    return AIChatsPublic(data=chat_list, count=total_count)


@router.get("/{chat_id}", response_model=AIChatPublic)
async def get_chat(
    *,
    session: Session = Depends(get_db),
    current_user: CurrentUser,
    chat_id: UUID,
) -> Any:
    """Get a specific AI chat with all its messages."""
    chat = chat_repository.get_chat_by_id(session, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    messages = chat_repository.get_messages_by_chat_id(session, chat_id)
    
    return AIChatPublic(
        id=chat.id,
        user_id=chat.user_id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=[AIChatMessagePublic.model_validate(msg) for msg in messages]
    )


@router.patch("/{chat_id}", response_model=AIChatPublic)
async def update_chat(
    *,
    session: Session = Depends(get_db),
    current_user: CurrentUser,
    chat_id: UUID,
    chat_in: AIChatUpdate,
) -> Any:
    """Update a chat's title."""
    chat = chat_repository.get_chat_by_id(session, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat = chat_repository.update_chat_title(session, chat, chat_in.title)
    messages = chat_repository.get_messages_by_chat_id(session, chat_id)
    
    return AIChatPublic(
        id=chat.id,
        user_id=chat.user_id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=[AIChatMessagePublic.model_validate(msg) for msg in messages]
    )


@router.delete("/{chat_id}", status_code=204)
async def delete_chat(
    *,
    session: Session = Depends(get_db),
    current_user: CurrentUser,
    chat_id: UUID,
) -> None:
    """Delete an AI chat conversation."""
    chat = chat_repository.get_chat_by_id(session, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    chat_repository.delete_chat(session, chat)


@router.put("/{chat_id}/messages/{message_id}", response_model=AIChatMessageResponse)
async def update_message(
    *,
    session: Session = Depends(get_db),
    current_user: CurrentUser,
    chat_id: UUID,
    message_id: UUID,
    message_in: AIChatSendMessage,
    _: bool = Depends(rate_limiter),
) -> Any:
    """Update a previous message, truncate the chat from that point, and get a new AI response."""
    # 1. Verify chat ownership
    chat = chat_repository.get_chat_by_id(session, chat_id, current_user.id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    
    # 2. Verify message exists and belongs to this chat
    message = chat_repository.get_message_by_id(session, message_id)
    if not message or message.chat_id != chat_id:
        raise HTTPException(status_code=404, detail="Message not found")
        
    # 3. Truncate conversation: Delete this message and everything that follows it
    # We delete the message itself because process_user_message will create a new one with the updated content.
    chat_repository.delete_messages_after_id(session, chat_id, message_id, include_self=True)
    
    # 4. Request a new response from the AI
    # This will create a new user message and a new assistant message.
    return await chat_service.process_user_message(
        session=session,
        user_id=current_user.id,
        chat_id=chat_id,
        message_content=message_in.message,
        model=message_in.model
    )


@router.post("/{chat_id}/messages", response_model=AIChatMessageResponse)
async def send_message(
    *,
    session: Session = Depends(get_db),
    current_user: CurrentUser,
    chat_id: UUID,
    message_in: AIChatSendMessage,
    _: bool = Depends(rate_limiter),
) -> Any:
    """Send a message to an AI chat and get a response."""
    return await chat_service.process_user_message(
        session=session,
        user_id=current_user.id,
        chat_id=chat_id,
        message_content=message_in.message,
        model=message_in.model
    )
