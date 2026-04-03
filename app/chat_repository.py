from typing import List, Optional
from uuid import UUID
from datetime import datetime, timezone
from sqlmodel import Session, select, func, col

import sqlalchemy as sa
from app.models import AIChat, AIChatMessage

def create_chat(session: Session, user_id: UUID, title: str = "New Chat") -> AIChat:
    """Create a new chat conversation."""
    chat = AIChat(
        user_id=user_id,
        title=title
    )
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat

def get_chat_by_id(session: Session, chat_id: UUID, user_id: UUID) -> Optional[AIChat]:
    """Get a chat by ID and user ID."""
    statement = select(AIChat).where(
        AIChat.id == chat_id,
        AIChat.user_id == user_id
    )
    return session.exec(statement).first()

def get_chats_by_user_id(
    session: Session, 
    user_id: UUID, 
    skip: int = 0, 
    limit: int = 100
) -> List[AIChat]:
    """Get all chats for a user, ordered by most recently updated."""
    statement = (
        select(AIChat)
        .where(AIChat.user_id == user_id)
        .order_by(col(AIChat.updated_at).desc())
        .offset(skip)
        .limit(limit)
    )
    return session.exec(statement).all()

def get_chat_count_by_user_id(session: Session, user_id: UUID) -> int:
    """Get the total count of chats for a user."""
    statement = select(func.count()).select_from(AIChat).where(
        AIChat.user_id == user_id
    )
    return session.exec(statement).one()

def get_messages_by_chat_id(session: Session, chat_id: UUID) -> List[AIChatMessage]:
    """Get all messages for a chat, ordered by creation time."""
    statement = (
        select(AIChatMessage)
        .where(AIChatMessage.chat_id == chat_id)
        .order_by(AIChatMessage.created_at)
    )
    return session.exec(statement).all()

def get_last_message_by_chat_id(session: Session, chat_id: UUID) -> Optional[AIChatMessage]:
    """Get the most recent message in a chat."""
    statement = (
        select(AIChatMessage)
        .where(AIChatMessage.chat_id == chat_id)
        .order_by(col(AIChatMessage.created_at).desc())
        .limit(1)
    )
    return session.exec(statement).first()

def get_message_by_id(session: Session, message_id: UUID) -> Optional[AIChatMessage]:
    """Get a chat message by its ID."""
    return session.get(AIChatMessage, message_id)

def update_chat_title(session: Session, chat: AIChat, title: str) -> AIChat:
    """Update a chat's title and updated_at timestamp."""
    chat.title = title
    chat.updated_at = datetime.now(timezone.utc)
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat

def update_chat_timestamp(session: Session, chat: AIChat) -> AIChat:
    """Update a chat's updated_at timestamp."""
    chat.updated_at = datetime.now(timezone.utc)
    session.add(chat)
    session.commit()
    session.refresh(chat)
    return chat

def delete_chat(session: Session, chat: AIChat) -> None:
    """Delete a chat and all its messages."""
    session.delete(chat)
    session.commit()

def create_message(
    session: Session, 
    chat_id: UUID, 
    role: str, 
    content: str,
    tokens_used: Optional[int] = None,
    model: Optional[str] = None
) -> AIChatMessage:
    """Create a new message in a chat."""
    message = AIChatMessage(
        chat_id=chat_id,
        role=role,
        content=content,
        tokens_used=tokens_used,
        model=model
    )
    session.add(message)
    session.commit()
    session.refresh(message)
    return message

def delete_messages_after_id(session: Session, chat_id: UUID, message_id: UUID, include_self: bool = False) -> None:
    """Delete all messages in a chat that were created after (and optionally including) a specific message."""
    # Get the target message to find its creation time
    target_msg = session.get(AIChatMessage, message_id)
    if not target_msg:
        return

    stmt = sa.delete(AIChatMessage).where(
        AIChatMessage.chat_id == chat_id
    )
    
    if include_self:
        stmt = stmt.where(AIChatMessage.created_at >= target_msg.created_at)
    else:
        stmt = stmt.where(AIChatMessage.created_at > target_msg.created_at)
        
    session.exec(stmt)
    session.commit()

def update_message_content(session: Session, message_id: UUID, new_content: str) -> Optional[AIChatMessage]:
    """Update the content of a specific message."""
    message = session.get(AIChatMessage, message_id)
    if not message:
        return None
    message.content = new_content
    session.add(message)
    session.commit()
    session.refresh(message)
    return message
