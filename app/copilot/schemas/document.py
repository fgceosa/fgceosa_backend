"""
Document and RAG Pydantic Schemas for API request/response
"""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import ConfigDict, Field
from sqlmodel import SQLModel


class DocumentCreate(SQLModel):
    """Schema for creating a document"""
    copilot_id: uuid.UUID
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=1000)
    metadata: dict = Field(default_factory=dict)


class DocumentUpdate(SQLModel):
    """Schema for updating a document"""
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=1000)
    metadata: dict | None = None


class DocumentPublic(SQLModel):
    """Public schema for document response"""
    id: uuid.UUID
    copilot_id: uuid.UUID = Field(alias="copilotId")
    uploaded_by: uuid.UUID = Field(alias="uploadedBy")
    filename: str
    original_filename: str = Field(alias="originalFilename")
    file_type: str = Field(alias="fileType")
    file_size: int = Field(alias="fileSize")
    file_url: str = Field(alias="fileUrl")
    status: str
    error_message: str | None = Field(default=None, alias="errorMessage")
    title: str | None = None
    description: str | None = None
    document_metadata: dict = Field(default_factory=dict, alias="metadata")
    total_chunks: int = Field(default=0, alias="totalChunks")
    total_tokens: int = Field(default=0, alias="totalTokens")
    processing_started_at: datetime | None = Field(default=None, alias="processingStartedAt")
    processing_completed_at: datetime | None = Field(default=None, alias="processingCompletedAt")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentsPublic(SQLModel):
    """Schema for paginated documents list"""
    documents: list[DocumentPublic]
    total: int


class DocumentChunkPublic(SQLModel):
    """Public schema for document chunk response"""
    id: uuid.UUID
    document_id: uuid.UUID = Field(alias="documentId")
    chunk_index: int = Field(alias="chunkIndex")
    content: str
    start_char: int | None = Field(default=None, alias="startChar")
    end_char: int | None = Field(default=None, alias="endChar")
    page_number: int | None = Field(default=None, alias="pageNumber")
    section: str | None = None
    chunk_metadata: dict = Field(default_factory=dict, alias="metadata")
    token_count: int = Field(default=0, alias="tokenCount")
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentSearchRequest(SQLModel):
    """Schema for document search request"""
    query: str = Field(min_length=1, max_length=1000)
    copilot_id: uuid.UUID | None = Field(default=None, alias="copilotId")
    document_ids: list[uuid.UUID] | None = Field(default=None, alias="documentIds")
    top_k: int = Field(default=5, ge=1, le=50, alias="topK")
    similarity_threshold: float = Field(default=0.7, ge=0, le=1, alias="similarityThreshold")
    include_metadata: bool = Field(default=True, alias="includeMetadata")


class DocumentSearchResult(SQLModel):
    """Schema for document search result"""
    chunk_id: uuid.UUID = Field(alias="chunkId")
    document_id: uuid.UUID = Field(alias="documentId")
    document_title: str | None = Field(default=None, alias="documentTitle")
    content: str
    similarity_score: float = Field(alias="similarityScore")
    page_number: int | None = Field(default=None, alias="pageNumber")
    section: str | None = None
    chunk_metadata: dict = Field(default_factory=dict, alias="metadata")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentSearchResponse(SQLModel):
    """Schema for document search response"""
    results: list[DocumentSearchResult]
    query: str
    total_results: int = Field(alias="totalResults")
    search_time_ms: int = Field(alias="searchTimeMs")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class DocumentUploadResponse(SQLModel):
    """Schema for document upload response"""
    id: uuid.UUID
    filename: str
    status: str
    message: str


class DocumentProcessingStatus(SQLModel):
    """Schema for document processing status"""
    id: uuid.UUID
    status: str
    progress: float  # 0.0 to 1.0
    total_chunks: int = Field(alias="totalChunks")
    processed_chunks: int = Field(alias="processedChunks")
    error_message: str | None = Field(alias="errorMessage")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)
