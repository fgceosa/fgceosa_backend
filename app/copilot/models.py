"""
Copilot Hub Database Models

This module defines the database models for the multi-agent copilot platform.
Uses SQLModel (SQLAlchemy + Pydantic) for ORM and pgvector for embeddings.
"""

import uuid
from typing import Optional
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from sqlmodel import Field, Relationship, SQLModel, Column
from sqlalchemy import JSON, Text
from pgvector.sqlalchemy import Vector


# ==================== Enums ====================

class CopilotCategory(str, Enum):
    """Copilot category enum"""
    CODING = "coding"
    WRITING = "writing"
    RESEARCH = "research"
    DATA_ANALYSIS = "data-analysis"
    CUSTOMER_SUPPORT = "customer-support"
    SALES = "sales"
    MARKETING = "marketing"
    LEGAL = "legal"
    HR = "hr"
    GENERAL = "general"
    CUSTOM = "custom"


class CopilotStatus(str, Enum):
    """Copilot status enum"""
    DRAFT = "draft"
    ACTIVE = "active"
    INACTIVE = "inactive"
    DISABLED = "disabled"


class CopilotVisibility(str, Enum):
    """Copilot visibility enum"""
    PUBLIC = "public"
    PRIVATE = "private"
    WORKSPACE = "workspace"


class CopilotCapability(str, Enum):
    """Copilot capability enum"""
    WEB_SEARCH = "web-search"
    CODE_EXECUTION = "code-execution"
    FILE_UPLOAD = "file-upload"
    IMAGE_GENERATION = "image-generation"
    VOICE_INPUT = "voice-input"
    API_INTEGRATION = "api-integration"
    MEMORY = "memory"
    FUNCTION_CALLING = "function-calling"
    VISION = "vision"



class MessageRole(str, Enum):
    """Message role enum"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
    TOOL = "tool"


class ToolType(str, Enum):
    """Tool type enum"""
    RAG_SEARCH = "rag_search"
    HTTP_REQUEST = "http_request"
    DATABASE_QUERY = "database_query"
    EMAIL_SEND = "email_send"
    FILE_RETRIEVAL = "file_retrieval"
    CODE_EXECUTION = "code_execution"
    WEB_SEARCH = "web_search"
    CUSTOM = "custom"


class DocumentStatus(str, Enum):
    """Document processing status"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ExecutionStatus(str, Enum):
    """Execution status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ==================== Copilot Models ====================

class Copilot(SQLModel, table=True):
    """
    Main Copilot/Agent model.
    Represents an AI agent with specific instructions, model, and capabilities.
    """
    __tablename__ = "copilot"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

    # Basic Info
    name: str = Field(max_length=255, index=True)
    description: str = Field(default="", sa_column=Column(Text))
    avatar: str | None = Field(default=None, max_length=500)
    domain: str | None = Field(default=None, max_length=255)

    # Classification
    category: str = Field(default="general", max_length=50, index=True)
    status: str = Field(default="draft", max_length=20, index=True)
    visibility: str = Field(default="private", max_length=20, index=True)
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # AI Configuration
    model: str = Field(default="openai/gpt-4o-mini", max_length=100)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    top_p: float = Field(default=1.0, ge=0, le=1)
    frequency_penalty: float = Field(default=0.0, ge=-2, le=2)
    presence_penalty: float = Field(default=0.0, ge=-2, le=2)
    stop_sequences: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Prompts & Messages
    system_prompt: str = Field(default="", sa_column=Column(Text))
    welcome_message: str | None = Field(default=None, sa_column=Column(Text))
    suggested_prompts: list[str] = Field(default_factory=list, sa_column=Column(JSON))

    # Capabilities & Features
    capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    allow_file_uploads: bool = Field(default=False)
    allow_web_search: bool = Field(default=False)
    allow_code_execution: bool = Field(default=False)
    memory_enabled: bool = Field(default=True)
    memory_window_size: int = Field(default=10)

    # Tools Configuration
    tools_config: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Ownership (no foreign key - user/workspace in separate database)
    created_by: uuid.UUID = Field(nullable=False, index=True)
    organization_id: uuid.UUID | None = Field(default=None, nullable=True, index=True)
    workspace_id: uuid.UUID | None = Field(default=None, nullable=True, index=True) # Legacy, keeping for compatibility during migration

    # Stats
    usage_count: int = Field(default=0)
    rating: float | None = Field(default=None)
    is_featured: bool = Field(default=False)
    is_official: bool = Field(default=False)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    conversations: list["CopilotConversation"] = Relationship(back_populates="copilot", cascade_delete=True)
    documents: list["CopilotDocument"] = Relationship(back_populates="copilot", cascade_delete=True)
    tools: list["CopilotTool"] = Relationship(back_populates="copilot", cascade_delete=True)
    shares: list["CopilotShare"] = Relationship(back_populates="copilot", cascade_delete=True)
    activities: list["CopilotActivity"] = Relationship(cascade_delete=True)
    assigned_workspaces: list["CopilotWorkspace"] = Relationship(back_populates="copilot", cascade_delete=True)


class CopilotWorkspace(SQLModel, table=True):
    """
    Link table between Copilots and Workspaces.
    Copilots are organization-level but can be assigned to multiple internal workspaces.
    """
    __tablename__ = "copilot_workspace"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    copilot_id: uuid.UUID = Field(foreign_key="copilot.copilot.id", nullable=False, ondelete="CASCADE", index=True)
    workspace_id: uuid.UUID = Field(nullable=False, index=True) # No FK - workspace in separate database

    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    copilot: Copilot = Relationship(back_populates="assigned_workspaces")



class CopilotConversation(SQLModel, table=True):
    """
    Conversation/Thread model for copilot interactions.
    Groups messages together in a conversation context.
    """
    __tablename__ = "copilot_conversation"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    copilot_id: uuid.UUID = Field(foreign_key="copilot.copilot.id", nullable=False, ondelete="CASCADE", index=True)
    user_id: uuid.UUID = Field(nullable=False, index=True)  # No FK - user in separate database

    title: str = Field(default="New Conversation", max_length=500)
    is_active: bool = Field(default=True)

    # Context & Memory
    context: dict = Field(default_factory=dict, sa_column=Column(JSON))
    memory_summary: str | None = Field(default=None, sa_column=Column(Text))

    # Stats
    message_count: int = Field(default=0)
    total_tokens_used: int = Field(default=0)
    total_cost: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_message_at: datetime | None = Field(default=None)

    # Relationships
    copilot: Copilot = Relationship(back_populates="conversations")
    messages: list["CopilotMessage"] = Relationship(back_populates="conversation", cascade_delete=True)


class CopilotMessage(SQLModel, table=True):
    """
    Individual message in a copilot conversation.
    Supports user, assistant, system, and tool messages.
    """
    __tablename__ = "copilot_message"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    conversation_id: uuid.UUID = Field(foreign_key="copilot.copilot_conversation.id", nullable=False, ondelete="CASCADE", index=True)

    # Message Content
    role: str = Field(max_length=20, index=True)  # user, assistant, system, tool
    content: str = Field(sa_column=Column(Text))

    # Tool Calls (for function calling)
    tool_calls: list[dict] | None = Field(default=None, sa_column=Column(JSON))
    tool_call_id: str | None = Field(default=None, max_length=255)

    # Attachments
    attachments: list[dict] = Field(default_factory=list, sa_column=Column(JSON))

    # Message Metadata
    message_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))
    model_used: str | None = Field(default=None, max_length=100)
    tokens_used: int | None = Field(default=None)
    cost: Decimal | None = Field(default=None, max_digits=10, decimal_places=6)
    response_time_ms: int | None = Field(default=None)
    agent_steps: list[dict] | None = Field(default=None, sa_column=Column(JSON))

    # Feedback
    feedback_rating: int | None = Field(default=None)  # 1 = thumbs down, 2 = thumbs up
    feedback_comment: str | None = Field(default=None, max_length=1000)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    conversation: CopilotConversation = Relationship(back_populates="messages")


# ==================== Document & RAG Models ====================

class CopilotDocument(SQLModel, table=True):
    """
    Document model for RAG (Retrieval-Augmented Generation).
    Stores uploaded documents linked to copilots for knowledge retrieval.
    """
    __tablename__ = "copilot_document"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    copilot_id: uuid.UUID = Field(foreign_key="copilot.copilot.id", nullable=False, ondelete="CASCADE", index=True)
    uploaded_by: uuid.UUID = Field(nullable=False, index=True)  # No FK - user in separate database

    # File Info
    filename: str = Field(max_length=500)
    original_filename: str = Field(max_length=500)
    file_type: str = Field(max_length=100)  # pdf, docx, txt, etc.
    file_size: int = Field(default=0)  # Size in bytes
    file_url: str = Field(max_length=1000)  # R2 storage URL

    # Processing Status
    status: str = Field(default="pending", max_length=20, index=True)
    error_message: str | None = Field(default=None, max_length=1000)

    # Document Metadata
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=1000)
    document_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Processing Stats
    total_chunks: int = Field(default=0)
    total_tokens: int = Field(default=0)
    processing_started_at: datetime | None = Field(default=None)
    processing_completed_at: datetime | None = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    copilot: Copilot = Relationship(back_populates="documents")
    chunks: list["CopilotDocumentChunk"] = Relationship(back_populates="document", cascade_delete=True)


class CopilotDocumentChunk(SQLModel, table=True):
    """
    Document chunk model with vector embeddings for semantic search.
    Uses pgvector for similarity search.
    """
    __tablename__ = "copilot_document_chunk"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    document_id: uuid.UUID = Field(foreign_key="copilot.copilot_document.id", nullable=False, ondelete="CASCADE", index=True)

    # Chunk Content
    chunk_index: int = Field(default=0)
    content: str = Field(sa_column=Column(Text))

    # Vector Embedding (1536 dimensions for OpenAI ada-002)
    embedding: list[float] | None = Field(default=None, sa_column=Column(Vector(1536)))

    # Chunk Metadata
    start_char: int | None = Field(default=None)
    end_char: int | None = Field(default=None)
    page_number: int | None = Field(default=None)
    section: str | None = Field(default=None, max_length=255)
    chunk_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Token Info
    token_count: int = Field(default=0)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    document: CopilotDocument = Relationship(back_populates="chunks")


# ==================== Tool Models ====================

class CopilotTool(SQLModel, table=True):
    """
    Tool configuration for copilots.
    Defines available tools that the agent can use.
    """
    __tablename__ = "copilot_tool"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    copilot_id: uuid.UUID = Field(foreign_key="copilot.copilot.id", nullable=False, ondelete="CASCADE", index=True)

    # Tool Info
    name: str = Field(max_length=100, index=True)
    description: str = Field(max_length=1000)
    tool_type: str = Field(max_length=50, index=True)  # rag_search, http_request, etc.

    # OpenAI-style Tool Schema
    parameters_schema: dict = Field(sa_column=Column(JSON))  # JSON Schema for parameters

    # Tool Configuration
    config: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Access Control
    is_enabled: bool = Field(default=True)
    requires_confirmation: bool = Field(default=False)  # User must confirm before execution

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    copilot: Copilot = Relationship(back_populates="tools")
    executions: list["CopilotToolExecution"] = Relationship(back_populates="tool", cascade_delete=True)


class CopilotToolExecution(SQLModel, table=True):
    """
    Tool execution log.
    Records each tool invocation for debugging and auditing.
    """
    __tablename__ = "copilot_tool_execution"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    tool_id: uuid.UUID = Field(foreign_key="copilot.copilot_tool.id", nullable=False, ondelete="CASCADE", index=True)
    conversation_id: uuid.UUID = Field(foreign_key="copilot.copilot_conversation.id", nullable=False, ondelete="CASCADE", index=True)
    message_id: uuid.UUID | None = Field(default=None, foreign_key="copilot.copilot_message.id", nullable=True, ondelete="SET NULL")

    # Execution Details
    status: str = Field(default="pending", max_length=20, index=True)
    input_params: dict = Field(sa_column=Column(JSON))
    output_result: dict | None = Field(default=None, sa_column=Column(JSON))
    error_message: str | None = Field(default=None, max_length=2000)

    # Timing
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    execution_time_ms: int | None = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    tool: CopilotTool = Relationship(back_populates="executions")


# ==================== Agent Execution Models ====================

class CopilotExecution(SQLModel, table=True):
    """
    Long-running agent execution tracking.
    For async agent tasks via Celery.
    """
    __tablename__ = "copilot_execution"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    copilot_id: uuid.UUID = Field(foreign_key="copilot.copilot.id", nullable=False, ondelete="CASCADE", index=True)
    conversation_id: uuid.UUID = Field(foreign_key="copilot.copilot_conversation.id", nullable=False, ondelete="CASCADE", index=True)
    user_id: uuid.UUID = Field(nullable=False, index=True)  # No FK - user in separate database

    # Task Info
    celery_task_id: str | None = Field(default=None, max_length=255, index=True)
    status: str = Field(default="pending", max_length=20, index=True)

    # Input/Output
    input_message: str = Field(sa_column=Column(Text))
    output_response: str | None = Field(default=None, sa_column=Column(Text))

    # Execution Details
    model_used: str | None = Field(default=None, max_length=100)
    total_tokens: int = Field(default=0)
    total_cost: Decimal = Field(default=Decimal("0.0000"), max_digits=10, decimal_places=6)

    # Error Handling
    error_message: str | None = Field(default=None, max_length=2000)
    retry_count: int = Field(default=0)
    max_retries: int = Field(default=3)

    # Timing
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)
    execution_time_ms: int | None = Field(default=None)

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CopilotShare(SQLModel, table=True):
    """
    Model for tracking copilots shared with specific users.
    """
    __tablename__ = "copilot_share"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    copilot_id: uuid.UUID = Field(foreign_key="copilot.copilot.id", nullable=False, ondelete="CASCADE", index=True)
    user_id: uuid.UUID | None = Field(default=None, index=True) # Linked user if they exist
    email: str = Field(max_length=255, index=True) # Email of the user shared with
    message: str | None = Field(default=None, sa_column=Column(Text))
    
    # Permissions
    can_edit: bool = Field(default=False)
    can_chat: bool = Field(default=True)
    
    # Metadata
    shared_by: uuid.UUID = Field(nullable=False)
    shared_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    # Relationship
    copilot: "Copilot" = Relationship(back_populates="shares")


class ActivityType(str, Enum):
    """Activity type enum"""
    CREATED = "created"
    UPDATED = "updated"
    STATUS_CHANGED = "status_changed"
    SETTINGS_APPLIED = "settings_applied"
    DOCUMENT_ADDED = "document_added"
    DOCUMENT_REMOVED = "document_removed"
    SHARED = "shared"
    DUPLICATED = "duplicated"
    CONVERSATION_STARTED = "conversation_started"
    ERROR = "error"


class ActivityStatus(str, Enum):
    """Activity status enum"""
    SUCCESS = "success"
    FAILED = "failed"
    WARNING = "warning"
    INFO = "info"


class CopilotActivity(SQLModel, table=True):
    """
    Activity log for copilot events.
    Tracks all significant events for audit and activity feed.
    """
    __tablename__ = "copilot_activity"
    __table_args__ = {"schema": "copilot"}

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    copilot_id: uuid.UUID = Field(foreign_key="copilot.copilot.id", nullable=False, ondelete="CASCADE", index=True)
    user_id: uuid.UUID = Field(nullable=False, index=True)  # User who performed the action

    # Activity Info
    activity_type: str = Field(max_length=50, index=True)  # created, updated, etc.
    activity_status: str = Field(max_length=20, index=True)  # success, failed, etc.
    title: str = Field(max_length=255)  # Human-readable title
    description: str | None = Field(default=None, max_length=1000)  # Additional details
    source: str | None = Field(default=None, max_length=255)  # Where the action was performed

    # Activity Metadata
    activity_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))  # Additional context
    unique_id: str | None = Field(default=None, max_length=50)  # Short unique identifier for display

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
