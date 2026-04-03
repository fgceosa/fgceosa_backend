"""
Copilot Document API routes for RAG (Retrieval-Augmented Generation)
"""
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, BackgroundTasks
from sqlmodel import Session, select, func, col

from app.api.deps import CurrentUser, get_copilot_db, get_db
from app.copilot.models import (
    Copilot,
    CopilotDocument,
    CopilotDocumentChunk,
)
from app.copilot.schemas import (
    DocumentPublic,
    DocumentsPublic,
    DocumentUpdate,
    DocumentSearchRequest,
    DocumentSearchResponse,
    DocumentSearchResult,
    DocumentUploadResponse,
    DocumentProcessingStatus,
)
from app.services.copilot_service import copilot_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/copilots", tags=["Copilot Documents"])


# ==================== Document Upload ====================

@router.post("/{copilot_id}/documents/upload", response_model=DocumentUploadResponse)
async def upload_document(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    background_tasks: BackgroundTasks,
    copilot_id: uuid.UUID,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    description: str | None = Form(None),
) -> Any:
    """
    Upload a document to a copilot's knowledge base.

    Supported file types: PDF, DOCX, TXT, MD, CSV
    The document will be processed asynchronously:
    1. Upload to R2 storage
    2. Extract text content
    3. Chunk text semantically
    4. Generate embeddings via RequestyAI
    5. Store in pgvector for retrieval
    """
    # Verify copilot exists and user has access
    copilot = session.get(Copilot, copilot_id)
    if not copilot:
        raise HTTPException(status_code=404, detail="Copilot not found")

    # Verify user has access to the copilot (view/chat access)
    # This allows org_members to upload documents for chat analysis
    try:
        await copilot_service.get_copilot(session, main_session, copilot_id, current_user)
    except HTTPException as e:
        # If it's a 403 from get_copilot, use a more descriptive message for upload context
        if e.status_code == 403:
            raise HTTPException(
                status_code=403, 
                detail="You do not have permission to upload documents to this copilot"
            )
        raise e


    # Validate file type
    allowed_types = {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "text/plain": "txt",
        "text/markdown": "md",
        "text/csv": "csv",
        "application/vnd.ms-excel": "xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
        # Image types
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/jpg": "jpg",
        "image/gif": "gif",
        "image/webp": "webp",
    }

    content_type = file.content_type or "application/octet-stream"
    if content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: {content_type}. Supported: PDF, DOCX, TXT, MD, CSV, XLS, XLSX, PNG, JPG, GIF, WEBP"
        )

    file_type = allowed_types[content_type]

    # Read file content
    file_content = await file.read()
    file_size = len(file_content)

    # Validate file size (max 50MB)
    max_size = 50 * 1024 * 1024
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size is 50MB, got {file_size / (1024*1024):.2f}MB"
        )

    # Generate unique filename
    original_filename = file.filename or "document"
    unique_filename = f"{uuid.uuid4()}.{file_type}"

    # Step 1: Upload to R2 (Synchronous to ensure availability in chat)
    from app.copilot.rag.storage import upload_to_r2
    content_type_map = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "md": "text/markdown",
        "csv": "text/csv",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "webp": "image/webp",
    }
    content_type = content_type_map.get(file_type, f"application/{file_type}")
    
    file_url = await upload_to_r2(
        file_content=file_content,
        filename=unique_filename,
        content_type=content_type,
    )

    # Create document record (pending status)
    document = CopilotDocument(
        copilot_id=copilot_id,
        uploaded_by=current_user.id,
        filename=unique_filename,
        original_filename=original_filename,
        file_type=file_type,
        file_size=file_size,
        file_url=file_url,
        status="pending",
        title=title or original_filename,
        description=description,
    )
    session.add(document)
    session.commit()
    session.refresh(document)

    # Queue background processing task
    background_tasks.add_task(
        process_document_task,
        document_id=document.id,
        file_content=file_content,
        file_type=file_type,
    )

    return DocumentUploadResponse(
        id=document.id,
        filename=original_filename,
        status="pending",
        message="Document uploaded successfully. Processing started."
    )


async def process_document_task(
    document_id: uuid.UUID,
    file_content: bytes,
    file_type: str,
) -> None:
    """
    Background task to process uploaded document.

    This task:
    1. Uploads file to R2 storage
    2. Extracts text content
    3. Chunks the text
    4. Generates embeddings
    5. Stores chunks with embeddings in pgvector
    """
    from app.core.db import copilot_engine
    from sqlmodel import Session
    from app.copilot.rag.extractor import extract_text
    from app.copilot.rag.chunker import chunk_text
    from app.copilot.rag.embeddings import generate_embeddings

    with Session(copilot_engine) as session:
        document = session.get(CopilotDocument, document_id)
        if not document:
            return

        try:
            document.status = "processing"
            document.processing_started_at = datetime.now(timezone.utc)
            session.add(document)
            session.commit()

            # Step 1: Upload to R2 (Already done in main route)
            pass

            # Step 2: Extract text
            text_content = await extract_text(file_content, file_type)

            if not text_content or not text_content.strip():
                document.status = "completed"
                document.processing_completed_at = datetime.now(timezone.utc)
                document.error_message = "Warning: No text content found in file."
                document.total_chunks = 0
                document.total_tokens = 0
                session.add(document)
                session.commit()
                logger.info(f"[RAG] Document {document_id} processed: No content to index")
                return

            # Auto-generate description if missing and it's not an image
            if not document.description and text_content.strip() and file_type.lower() not in ["png", "jpg", "jpeg", "gif", "webp"]:
                try:
                    from app.services.requesty_ai import requesty_service
                    summary_result = await requesty_service.generate_response(
                        messages=[{
                            "role": "system",
                            "content": "Summarize this document in ONE short sentence (max 20 words) for use as a search description. Focus on what it contains. Be concise."
                        }, {
                            "role": "user",
                            "content": text_content[:4000]
                        }],
                        model="openai/gpt-4o-mini",
                        max_tokens=60
                    )
                    document.description = summary_result["content"].strip().strip('"')
                    logger.info(f"[RAG] Auto-generated description for {document_id}")
                except Exception as sum_e:
                    logger.warning(f"Failed to auto-summarize document {document_id}: {sum_e}")
                    # Fallback to snippet
                    document.description = (text_content[:150].strip() + "...") if len(text_content) > 150 else text_content

            # Step 3: Chunk text
            chunks = chunk_text(text_content, chunk_size=1000, overlap=200)

            # Step 4 & 5: Generate embeddings and store chunks
            total_tokens = 0
            for i, chunk in enumerate(chunks):
                # Generate embedding
                embedding, tokens = await generate_embeddings(chunk["content"])
                total_tokens += tokens

                # Create chunk record
                doc_chunk = CopilotDocumentChunk(
                    document_id=document_id,
                    chunk_index=i,
                    content=chunk["content"],
                    embedding=embedding,
                    start_char=chunk.get("start_char"),
                    end_char=chunk.get("end_char"),
                    page_number=chunk.get("page_number"),
                    section=chunk.get("section"),
                    token_count=tokens,
                    metadata=chunk.get("metadata", {}),
                )
                session.add(doc_chunk)

            # Update document stats
            document.total_chunks = len(chunks)
            document.total_tokens = total_tokens
            document.status = "completed"
            document.processing_completed_at = datetime.now(timezone.utc)

            session.add(document)
            session.commit()

        except Exception as e:
            document.status = "failed"
            document.error_message = str(e)[:1000]
            session.add(document)
            session.commit()
            # Log error but don't crash backend
            print(f"Error processing document {document_id}: {e}") 


# ==================== Document List & CRUD ====================

@router.get("/{copilot_id}/documents", response_model=DocumentsPublic)
async def list_documents(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: str | None = Query(None, description="Filter by status"),
) -> Any:
    """
    List documents in a copilot's knowledge base.
    """
    # Verify copilot access
    copilot = session.get(Copilot, copilot_id)
    if not copilot:
        raise HTTPException(status_code=404, detail="Copilot not found")

    is_owner = copilot.created_by == current_user.id
    is_public = copilot.visibility == "public"
    
    if not is_owner and not is_public and not current_user.is_superuser:
        # Check org access
        org_id, org_role, _ = await copilot_service._get_user_context(main_session, current_user)
        is_org_admin = (org_id and copilot.organization_id == org_id and 
                        org_role in ["org_super_admin", "org_admin"])
        
        if not is_org_admin:
            raise HTTPException(status_code=403, detail="Access denied")

    statement = select(CopilotDocument).where(CopilotDocument.copilot_id == copilot_id)

    if status:
        statement = statement.where(CopilotDocument.status == status)

    count_statement = select(func.count()).select_from(statement.subquery())
    total = session.exec(count_statement).one()

    statement = statement.order_by(col(CopilotDocument.created_at).desc()).offset(skip).limit(limit)
    documents = session.exec(statement).all()

    # Convert to Pydantic models to avoid SQLAlchemy metadata conflict
    doc_list = [
        DocumentPublic(
            id=doc.id,
            copilot_id=doc.copilot_id,
            uploaded_by=doc.uploaded_by,
            filename=doc.filename,
            original_filename=doc.original_filename,
            file_type=doc.file_type,
            file_size=doc.file_size,
            file_url=doc.file_url,
            status=doc.status,
            error_message=doc.error_message,
            title=doc.title,
            description=doc.description,
            document_metadata=doc.document_metadata or {},
            total_chunks=doc.total_chunks,
            total_tokens=doc.total_tokens,
            processing_started_at=doc.processing_started_at,
            processing_completed_at=doc.processing_completed_at,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )
        for doc in documents
    ]

    return DocumentsPublic(documents=doc_list, total=total)


@router.get("/{copilot_id}/documents/{document_id}", response_model=DocumentPublic)
async def get_document(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Any:
    """
    Get a specific document.
    """
    document = session.get(CopilotDocument, document_id)

    if not document or document.copilot_id != copilot_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify copilot access
    copilot = session.get(Copilot, copilot_id)
    is_owner = copilot.created_by == current_user.id
    is_public = copilot.visibility == "public"
    
    if not is_owner and not is_public and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    return document


@router.get("/{copilot_id}/documents/{document_id}/status", response_model=DocumentProcessingStatus)
async def get_document_status(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    document_id: uuid.UUID,
) -> Any:
    """
    Get document processing status.
    """
    document = session.get(CopilotDocument, document_id)

    if not document or document.copilot_id != copilot_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Count processed chunks
    processed_chunks = 0
    if document.status == "processing":
        count_statement = select(func.count()).select_from(CopilotDocumentChunk).where(
            CopilotDocumentChunk.document_id == document_id
        )
        processed_chunks = session.exec(count_statement).one()

    # Calculate progress
    progress = 0.0
    if document.status == "completed":
        progress = 1.0
    elif document.status == "processing" and document.total_chunks > 0:
        progress = processed_chunks / document.total_chunks

    return DocumentProcessingStatus(
        id=document.id,
        status=document.status,
        progress=progress,
        total_chunks=document.total_chunks,
        processed_chunks=processed_chunks,
        error_message=document.error_message,
    )


@router.patch("/{copilot_id}/documents/{document_id}", response_model=DocumentPublic)
async def update_document(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    document_id: uuid.UUID,
    document_in: DocumentUpdate,
) -> Any:
    """
    Update document metadata.
    """
    document = session.get(CopilotDocument, document_id)

    if not document or document.copilot_id != copilot_id:
        raise HTTPException(status_code=404, detail="Document not found")

    if document.uploaded_by != current_user.id and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only the uploader or an admin can update this document")

    update_data = document_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(document, field, value)

    document.updated_at = datetime.now(timezone.utc)
    session.add(document)
    session.commit()
    session.refresh(document)

    return document


@router.delete("/{copilot_id}/documents/{document_id}", status_code=204)
async def delete_document(
    *,
    session: Session = Depends(get_copilot_db),
    main_session: Session = Depends(get_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    document_id: uuid.UUID,
) -> None:

    """
    Delete a document and all its chunks.
    """
    document = session.get(CopilotDocument, document_id)

    if not document or document.copilot_id != copilot_id:
        raise HTTPException(status_code=404, detail="Document not found")

    # Verify copilot access
    copilot = session.get(Copilot, copilot_id)
    if not copilot:
         raise HTTPException(status_code=404, detail="Copilot not found")

    # Permission check: Uploader, Copilot Owner, Organization Admin, or Platform Superuser
    is_uploader = document.uploaded_by == current_user.id
    is_copilot_owner = copilot.created_by == current_user.id
    is_superuser = current_user.is_superuser

    # Org check logic
    is_org_admin = False
    org_id, org_role, _ = await copilot_service._get_user_context(main_session, current_user)
    if org_id and copilot.organization_id == org_id:
        is_org_admin = org_role in ["org_super_admin", "org_admin"]

    if not (is_uploader or is_copilot_owner or is_superuser or is_org_admin):
        raise HTTPException(
            status_code=403, 
            detail="Unauthorized: You do not have permission to delete this document. Only the uploader or an admin can manage knowledge base documents."
        )

    # Step 1: Delete file from R2 storage
    try:
        from app.copilot.rag.storage import delete_from_r2
        await delete_from_r2(document.filename)
    except Exception as e:
        logger.error(f"Failed to delete file from R2 storage: {str(e)}")
        # We continue even if R2 fails, to ensure DB record can be cleaned up

    # Step 2: Delete from Database
    try:
        session.delete(document)
        session.commit()
    except Exception as e:
        session.rollback()
        logger.error(f"Database error while deleting document {document_id}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal Server Error: Failed to remove document from database. {str(e)}"
        )



# ==================== Document Search (RAG) ====================

@router.post("/{copilot_id}/documents/search", response_model=DocumentSearchResponse)
async def search_documents(
    *,
    session: Session = Depends(get_copilot_db),
    current_user: CurrentUser,
    copilot_id: uuid.UUID,
    search_request: DocumentSearchRequest,
) -> Any:
    """
    Semantic search across copilot documents using vector similarity.

    This endpoint:
    1. Generates embedding for the query
    2. Performs cosine similarity search against document chunks
    3. Returns top-k most relevant chunks with metadata
    """
    import time

    start_time = time.time()

    # Verify copilot access
    copilot = session.get(Copilot, copilot_id)
    if not copilot:
        raise HTTPException(status_code=404, detail="Copilot not found")

    is_owner = copilot.created_by == current_user.id
    is_public = copilot.visibility == "public"
    
    if not is_owner and not is_public and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Access denied")

    # Generate query embedding
    from app.copilot.rag.embeddings import generate_embeddings
    query_embedding, _ = await generate_embeddings(search_request.query)

    # Build search query using pgvector
    from sqlalchemy import text

    # Filter by specific documents if provided
    document_filter = ""
    params = {
        "copilot_id": str(copilot_id),
        "embedding": query_embedding,
        "limit": search_request.top_k,
        "threshold": search_request.similarity_threshold,
    }

    if search_request.document_ids:
        document_filter = "AND d.id = ANY(:document_ids)"
        params["document_ids"] = [str(doc_id) for doc_id in search_request.document_ids]

    # Vector similarity search query
    search_query = text(f"""
        SELECT
            c.id as chunk_id,
            c.document_id,
            d.title as document_title,
            c.content,
            1 - (c.embedding <=> CAST(:embedding AS vector)) as similarity_score,
            c.page_number,
            c.section,
            c.metadata
        FROM copilot_document_chunk c
        JOIN copilot_document d ON c.document_id = d.id
        WHERE d.copilot_id = :copilot_id
          AND d.status = 'completed'
          {document_filter}
          AND 1 - (c.embedding <=> CAST(:embedding AS vector)) >= :threshold
        ORDER BY c.embedding <=> CAST(:embedding AS vector)
        LIMIT :limit
    """)

    result = session.exec(search_query, params=params)
    rows = result.fetchall()

    search_time_ms = int((time.time() - start_time) * 1000)

    results = [
        DocumentSearchResult(
            chunk_id=row.chunk_id,
            document_id=row.document_id,
            document_title=row.document_title,
            content=row.content,
            similarity_score=float(row.similarity_score),
            page_number=row.page_number,
            section=row.section,
            metadata=row.metadata or {},
        )
        for row in rows
    ]

    return DocumentSearchResponse(
        results=results,
        query=search_request.query,
        total_results=len(results),
        search_time_ms=search_time_ms,
    )
