"""
Copilot Pydantic Schemas for API request/response
"""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


class CopilotCreate(SQLModel):
    """Schema for creating a copilot"""
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")
    category: str = Field(default="general", max_length=50)
    domain: str | None = Field(default=None, max_length=255)
    visibility: str = Field(default="private", max_length=20)
    model: str = Field(default="gpt-4o", max_length=100)
    system_prompt: str = Field(default="")
    welcome_message: str | None = Field(default=None)
    suggested_prompts: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    temperature: float = Field(default=0.7, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=1, le=128000)
    top_p: float = Field(default=1.0, ge=0, le=1)
    frequency_penalty: float = Field(default=0.0, ge=-2, le=2)
    presence_penalty: float = Field(default=0.0, ge=-2, le=2)
    stop_sequences: list[str] = Field(default_factory=list)
    workspace_id: uuid.UUID | None = Field(default=None)
    is_featured: bool = Field(default=False)
    is_official: bool = Field(default=False)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CopilotUpdate(SQLModel):
    """Schema for updating a copilot"""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    category: str | None = Field(default=None, max_length=50)
    domain: str | None = Field(default=None, max_length=255)
    visibility: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=20)
    model: str | None = Field(default=None, max_length=100)
    system_prompt: str | None = None
    welcome_message: str | None = None
    suggested_prompts: list[str] | None = None
    capabilities: list[str] | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=128000)
    top_p: float | None = Field(default=None, ge=0, le=1)
    frequency_penalty: float | None = Field(default=None, ge=-2, le=2)
    presence_penalty: float | None = Field(default=None, ge=-2, le=2)
    stop_sequences: list[str] | None = None
    tags: list[str] | None = None
    allow_file_uploads: bool | None = None
    allow_web_search: bool | None = None
    allow_code_execution: bool | None = None
    memory_enabled: bool | None = None
    memory_window_size: int | None = None
    avatar: str | None = Field(default=None, max_length=500)
    is_featured: bool | None = None
    is_official: bool | None = None


class CopilotPublic(SQLModel):
    """Public schema for copilot response"""
    id: uuid.UUID
    name: str
    description: str
    avatar: str | None
    category: str
    domain: str | None
    status: str
    visibility: str
    model: str
    temperature: float
    max_tokens: int = Field(alias="maxTokens")
    system_prompt: str = Field(alias="systemPrompt")
    welcome_message: str | None = Field(alias="welcomeMessage")
    suggested_prompts: list[str] = Field(alias="suggestedPrompts")
    capabilities: list[str]
    tags: list[str]
    created_by: uuid.UUID = Field(alias="createdBy")
    created_by_name: str | None = Field(default=None, alias="createdByName")
    created_by_username: str | None = Field(default=None, alias="createdByUsername")
    organization_id: uuid.UUID | None = Field(default=None, alias="organizationId")
    workspace_id: uuid.UUID | None = Field(default=None, alias="workspaceId")
    assigned_workspaces_ids: list[uuid.UUID] = Field(default_factory=list, alias="assignedWorkspacesIds")
    usage_count: int = Field(alias="usageCount")
    rating: float | None
    is_featured: bool = Field(alias="isFeatured")
    is_official: bool = Field(alias="isOfficial")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CopilotsPublic(SQLModel):
    """Schema for paginated copilots list"""
    copilots: list[CopilotPublic]
    total: int


class CopilotSettings(SQLModel):
    """Detailed copilot settings schema"""
    id: uuid.UUID
    copilot_id: uuid.UUID = Field(alias="copilotId")
    domain: str | None = None
    model: str
    temperature: float
    max_tokens: int = Field(alias="maxTokens")
    top_p: float = Field(alias="topP")
    frequency_penalty: float = Field(alias="frequencyPenalty")
    presence_penalty: float = Field(alias="presencePenalty")
    stop_sequences: list[str] = Field(alias="stopSequences")
    system_prompt: str = Field(alias="systemPrompt")
    welcome_message: str = Field(alias="welcomeMessage")
    suggested_prompts: list[str] = Field(alias="suggestedPrompts")
    capabilities: list[str]
    allow_file_uploads: bool = Field(alias="allowFileUploads")
    allow_web_search: bool = Field(alias="allowWebSearch")
    allow_code_execution: bool = Field(alias="allowCodeExecution")
    memory_enabled: bool = Field(alias="memoryEnabled")
    memory_window_size: int = Field(alias="memoryWindowSize")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CopilotFilters(SQLModel):
    """Schema for filtering copilots"""
    category: str | None = None
    status: str | None = None
    visibility: str | None = None
    search: str | None = None
    tags: list[str] | None = None
    is_featured: bool | None = None
    is_official: bool | None = None
    workspace_id: uuid.UUID | None = None


class ShareCopilotRequest(SQLModel):
    """Schema for sharing a copilot"""
    emails: list[str] = Field(min_length=1)
    message: str | None = Field(default=None)


class CopilotSuggestionsResponse(SQLModel):
    """Schema for dynamic suggestions response"""
    suggestions: list[str]
    source: str  # 'manual', 'dynamic', or 'mixed'


class CopilotWorkspaceAssignment(SQLModel):
    """Schema for assigning a copilot to workspaces"""
    workspace_ids: list[uuid.UUID] = Field(alias="workspaceIds")

    model_config = ConfigDict(populate_by_name=True)


class CopilotAnalytics(SQLModel):
    """Schema for copilot analytics"""
    total_chats: int = Field(alias="totalChats")
    success_rate: float = Field(alias="successRate")
    avg_response_time: float = Field(alias="avgResponseTime")
    total_tokens: int = Field(alias="totalTokens")
    total_cost: float = Field(alias="totalCost")

    model_config = ConfigDict(populate_by_name=True)


class CopilotActivityEvent(SQLModel):
    """Schema for a single copilot activity event"""
    id: uuid.UUID
    activity_type: str = Field(alias="activityType")
    activity_status: str = Field(alias="activityStatus")
    title: str
    description: str | None = None
    source: str | None = None
    unique_id: str | None = Field(default=None, alias="uniqueId")
    metadata: dict = Field(default_factory=dict)
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CopilotActivityResponse(SQLModel):
    """Schema for copilot activity list"""
    activities: list[CopilotActivityEvent]
    total: int
