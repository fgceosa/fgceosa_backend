"""
Conversation and Message Pydantic Schemas for API request/response
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


class ConversationCreate(SQLModel):
    """Schema for creating a conversation"""
    copilot_id: uuid.UUID
    title: str | None = Field(default="New Conversation", max_length=500)
    context: dict = Field(default_factory=dict)


class ConversationUpdate(SQLModel):
    """Schema for updating a conversation"""
    title: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None
    context: dict | None = None
    memory_summary: str | None = None


class ConversationPublic(SQLModel):
    """Public schema for conversation response"""
    id: uuid.UUID
    copilot_id: uuid.UUID = Field(alias="copilotId")
    user_id: uuid.UUID = Field(alias="userId")
    title: str
    is_active: bool = Field(alias="isActive")
    context: dict
    memory_summary: str | None = Field(alias="memorySummary")
    message_count: int = Field(alias="messageCount")
    total_tokens_used: int = Field(alias="totalTokensUsed")
    total_cost: Decimal = Field(alias="totalCost")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    last_message_at: datetime | None = Field(alias="lastMessageAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ConversationsPublic(SQLModel):
    """Schema for paginated conversations list"""
    conversations: list[ConversationPublic]
    total: int


class MessageCreate(SQLModel):
    """Schema for creating a message"""
    role: str = Field(max_length=20)
    content: str
    tool_calls: list[dict] | None = None
    tool_call_id: str | None = None
    attachments: list[dict] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class MessageUpdate(SQLModel):
    """Schema for updating a message"""
    content: str = Field(min_length=1)


class MessagePublic(SQLModel):
    """Public schema for message response"""
    id: uuid.UUID
    conversation_id: uuid.UUID = Field(alias="conversationId")
    role: str
    content: str
    tool_calls: list[dict] | None = Field(default=None, alias="toolCalls")
    tool_call_id: str | None = Field(default=None, alias="toolCallId")
    attachments: list[dict] = Field(default_factory=list)
    message_metadata: dict = Field(default_factory=dict, alias="metadata")
    model_used: str | None = Field(default=None, alias="modelUsed")
    tokens_used: int | None = Field(default=None, alias="tokensUsed")
    cost: Decimal | None = None
    response_time_ms: int | None = Field(default=None, alias="responseTimeMs")
    feedback_rating: int | None = Field(default=None, alias="feedbackRating")
    feedback_comment: str | None = Field(default=None, alias="feedbackComment")
    agent_steps: list[dict] | None = Field(default=None, alias="agentSteps")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessagesPublic(SQLModel):
    """Schema for paginated messages list"""
    messages: list[MessagePublic]
    total: int


class SendMessageRequest(SQLModel):
    """Schema for sending a message to a copilot"""
    conversation_id: uuid.UUID | None = Field(default=None, alias="conversationId")
    content: str = Field(min_length=1)
    attachments: list[dict] = Field(default_factory=list)
    stream: bool = Field(default=True)
    context: dict = Field(default_factory=dict)
    workspace_id: uuid.UUID | None = Field(default=None, alias="workspaceId")
    admin_preview: bool = Field(default=False, alias="adminPreview")


    model_config = ConfigDict(populate_by_name=True)


class SendMessageResponse(SQLModel):
    """Schema for message response"""
    conversation_id: uuid.UUID = Field(alias="conversationId")
    user_id: uuid.UUID = Field(alias="userId")
    message_id: uuid.UUID = Field(alias="messageId")
    response_id: uuid.UUID = Field(alias="responseId")
    content: str
    tool_calls: list[dict] | None = Field(alias="toolCalls")
    model_used: str = Field(alias="modelUsed")
    tokens_used: int = Field(alias="tokensUsed")
    cost: Decimal
    response_time_ms: int = Field(alias="responseTimeMs")
    agent_steps: list[dict] | None = Field(default=None, alias="agentSteps")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class MessageFeedback(SQLModel):
    """Schema for message feedback"""
    rating: int = Field(ge=1, le=2)  # 1 = thumbs down, 2 = thumbs up
    comment: str | None = Field(default=None, max_length=1000)


class StreamChunk(SQLModel):
    """Schema for streaming response chunk"""
    type: str  # "content", "tool_call", "done", "error"
    content: str | None = None
    tool_call: dict | None = None
    message_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    error: str | None = None
