"""
Tool Pydantic Schemas for API request/response
"""

import uuid
from datetime import datetime
from typing import Optional, Any

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


class ToolCreate(SQLModel):
    """Schema for creating a tool"""
    copilot_id: uuid.UUID
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(min_length=1, max_length=1000)
    tool_type: str = Field(max_length=50)
    parameters_schema: dict  # OpenAI-style JSON Schema
    config: dict = Field(default_factory=dict)
    is_enabled: bool = Field(default=True)
    requires_confirmation: bool = Field(default=False)


class ToolUpdate(SQLModel):
    """Schema for updating a tool"""
    name: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, min_length=1, max_length=1000)
    parameters_schema: dict | None = None
    config: dict | None = None
    is_enabled: bool | None = None
    requires_confirmation: bool | None = None


class ToolPublic(SQLModel):
    """Public schema for tool response"""
    id: uuid.UUID
    copilot_id: uuid.UUID = Field(alias="copilotId")
    name: str
    description: str
    tool_type: str = Field(alias="toolType")
    parameters_schema: dict = Field(alias="parametersSchema")
    config: dict
    is_enabled: bool = Field(alias="isEnabled")
    requires_confirmation: bool = Field(alias="requiresConfirmation")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ToolsPublic(SQLModel):
    """Schema for paginated tools list"""
    tools: list[ToolPublic]
    total: int


class ToolExecutionCreate(SQLModel):
    """Schema for creating a tool execution"""
    tool_id: uuid.UUID
    conversation_id: uuid.UUID
    message_id: uuid.UUID | None = None
    input_params: dict


class ToolExecutionPublic(SQLModel):
    """Public schema for tool execution response"""
    id: uuid.UUID
    tool_id: uuid.UUID = Field(alias="toolId")
    conversation_id: uuid.UUID = Field(alias="conversationId")
    message_id: uuid.UUID | None = Field(alias="messageId")
    status: str
    input_params: dict = Field(alias="inputParams")
    output_result: dict | None = Field(alias="outputResult")
    error_message: str | None = Field(alias="errorMessage")
    started_at: datetime | None = Field(alias="startedAt")
    completed_at: datetime | None = Field(alias="completedAt")
    execution_time_ms: int | None = Field(alias="executionTimeMs")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class ToolExecutionsPublic(SQLModel):
    """Schema for paginated tool executions list"""
    executions: list[ToolExecutionPublic]
    total: int


# ==================== Built-in Tool Schemas ====================

class RAGSearchParams(SQLModel):
    """Parameters for RAG search tool"""
    query: str = Field(min_length=1, max_length=1000)
    top_k: int = Field(default=5, ge=1, le=20)
    similarity_threshold: float = Field(default=0.7, ge=0, le=1)


class HTTPRequestParams(SQLModel):
    """Parameters for HTTP request tool"""
    url: str = Field(min_length=1, max_length=2000)
    method: str = Field(default="GET", max_length=10)
    headers: dict = Field(default_factory=dict)
    body: Any = None
    timeout: int = Field(default=30, ge=1, le=120)


class HTTPRequestResult(SQLModel):
    """Result from HTTP request tool"""
    status_code: int
    headers: dict
    body: Any
    elapsed_ms: int


class DatabaseQueryParams(SQLModel):
    """Parameters for database query tool"""
    query: str = Field(min_length=1, max_length=5000)
    params: dict = Field(default_factory=dict)
    read_only: bool = Field(default=True)


class DatabaseQueryResult(SQLModel):
    """Result from database query tool"""
    rows: list[dict]
    row_count: int
    columns: list[str]


class EmailSendParams(SQLModel):
    """Parameters for email send tool"""
    to: list[str] = Field(min_length=1)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1)
    html_body: str | None = None
    cc: list[str] = Field(default_factory=list)
    bcc: list[str] = Field(default_factory=list)
    reply_to: str | None = None


class EmailSendResult(SQLModel):
    """Result from email send tool"""
    message_id: str
    success: bool
    error: str | None = None


class FileRetrievalParams(SQLModel):
    """Parameters for file retrieval tool"""
    file_id: uuid.UUID | None = None
    filename: str | None = None
    copilot_id: uuid.UUID | None = None


class FileRetrievalResult(SQLModel):
    """Result from file retrieval tool"""
    file_id: uuid.UUID
    filename: str
    content_type: str
    size: int
    download_url: str


class WebSearchParams(SQLModel):
    """Parameters for web search tool"""
    query: str = Field(min_length=1, max_length=500)
    num_results: int = Field(default=5, ge=1, le=20)


class WebSearchResult(SQLModel):
    """Result from web search tool"""
    results: list[dict]
    total_results: int


class CodeExecutionParams(SQLModel):
    """Parameters for code execution tool"""
    code: str = Field(min_length=1)
    language: str = Field(default="python", max_length=20)
    timeout: int = Field(default=30, ge=1, le=300)


class CodeExecutionResult(SQLModel):
    """Result from code execution tool"""
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: int
