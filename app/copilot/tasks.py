"""
Celery Tasks for Copilot Hub
Async task execution for agents, document processing, and embeddings
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from celery import shared_task
from sqlmodel import Session

from app.core.db import copilot_engine


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def execute_agent_task(
    self,
    execution_id: str,
    copilot_id: str,
    conversation_id: str,
    user_id: str,
    message: str,
) -> dict:
    """
    Execute an agent task asynchronously.

    This task handles long-running agent executions that may involve
    multiple tool calls and LLM interactions.

    Args:
        execution_id: UUID of the CopilotExecution record
        copilot_id: UUID of the Copilot
        conversation_id: UUID of the CopilotConversation
        user_id: UUID of the user
        message: User message to process

    Returns:
        Dict with execution results
    """
    import asyncio
    from app.copilot.models import (
        Copilot,
        CopilotConversation,
        CopilotExecution,
        CopilotMessage,
    )
    from app.copilot.runtime.executor import AgentExecutor, ExecutionContext
    from app.copilot.runtime.tool_handler import ToolHandler

    with Session(copilot_engine) as session:
        # Get execution record
        execution = session.get(CopilotExecution, uuid.UUID(execution_id))
        if not execution:
            return {"error": "Execution not found"}

        try:
            # Update status
            execution.status = "running"
            execution.started_at = datetime.now(timezone.utc)
            session.add(execution)
            session.commit()

            # Get copilot and conversation
            copilot = session.get(Copilot, uuid.UUID(copilot_id))
            conversation = session.get(CopilotConversation, uuid.UUID(conversation_id))

            if not copilot or not conversation:
                raise ValueError("Copilot or conversation not found")

            # Initialize tools
            tool_handler = ToolHandler(
                copilot=copilot,
                session=session,
                user_id=uuid.UUID(user_id),
            )
            tools = tool_handler.initialize_tools()

            # Create execution context
            context = ExecutionContext(
                copilot=copilot,
                conversation=conversation,
                user_id=uuid.UUID(user_id),
                session=session,
                tools=tools,
                max_iterations=10,
            )

            # Create executor and run
            executor = AgentExecutor(context)

            # Run async executor in sync context
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(executor.execute(message))
            finally:
                loop.close()

            # Save assistant message
            assistant_message = CopilotMessage(
                conversation_id=conversation.id,
                role="assistant",
                content=result.content,
                tool_calls=result.tool_calls if result.tool_calls else None,
                model_used=result.model_used,
                tokens_used=result.tokens_used,
                cost=result.cost,
                response_time_ms=result.response_time_ms,
            )
            session.add(assistant_message)

            # Update execution record
            execution.status = "completed"
            execution.output_response = result.content
            execution.model_used = result.model_used
            execution.total_tokens = result.tokens_used
            execution.total_cost = result.cost
            execution.completed_at = datetime.now(timezone.utc)
            execution.execution_time_ms = result.response_time_ms

            # Update conversation stats
            conversation.message_count += 2  # User + assistant
            conversation.total_tokens_used += result.tokens_used
            conversation.total_cost += result.cost
            conversation.last_message_at = datetime.now(timezone.utc)
            conversation.updated_at = datetime.now(timezone.utc)

            # Update copilot usage
            copilot.usage_count += 1

            session.add(execution)
            session.add(conversation)
            session.add(copilot)
            session.commit()

            return {
                "status": "completed",
                "message_id": str(assistant_message.id),
                "content": result.content,
                "tokens_used": result.tokens_used,
                "cost": float(result.cost),
                "response_time_ms": result.response_time_ms,
            }

        except Exception as e:
            # Update execution with error
            execution.status = "failed"
            execution.error_message = str(e)[:2000]
            execution.retry_count += 1
            session.add(execution)
            session.commit()

            # Retry if under limit
            if execution.retry_count < execution.max_retries:
                raise self.retry(exc=e)

            return {
                "status": "failed",
                "error": str(e),
            }


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_document_task(
    self,
    document_id: str,
    file_content_base64: str | None = None,
    file_type: str = "txt",
) -> dict:
    """
    Process an uploaded document asynchronously.

    This task:
    1. Uploads file to R2 storage (if content provided)
    2. Extracts text content
    3. Chunks the text
    4. Generates embeddings
    5. Stores chunks in pgvector

    Args:
        document_id: UUID of the CopilotDocument
        file_content_base64: Base64 encoded file content (optional if already in R2)
        file_type: File type (pdf, docx, txt, etc.)

    Returns:
        Dict with processing results
    """
    import asyncio
    import base64
    import logging
    from app.copilot.models import CopilotDocument, CopilotDocumentChunk

    logger = logging.getLogger(__name__)
    logger.info(f"[CELERY] Starting processing for document {document_id}")

    with Session(copilot_engine) as session:
        document = session.get(CopilotDocument, uuid.UUID(document_id))
        if not document:
            logger.error(f"[CELERY] Document {document_id} not found in database")
            return {"error": "Document not found"}

        try:
            # Update status
            document.status = "processing"
            document.processing_started_at = datetime.now(timezone.utc)
            session.add(document)
            session.commit()


            # Decode file content
            file_content = None
            if file_content_base64:
                file_content = base64.b64decode(file_content_base64)

            # Run async processing
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result = loop.run_until_complete(
                    _process_document_async(session, document, file_content, file_type)
                )
            finally:
                loop.close()

            return result

        except Exception as e:
            document.status = "failed"
            document.error_message = str(e)[:1000]
            session.add(document)
            session.commit()

            raise self.retry(exc=e)


async def _process_document_async(
    session: Session,
    document,
    file_content: bytes | None,
    file_type: str,
) -> dict:
    """Async helper for document processing."""
    from app.copilot.rag.storage import upload_to_r2, download_from_r2
    from app.copilot.rag.extractor import extract_text
    from app.copilot.rag.chunker import chunk_text
    from app.copilot.rag.embeddings import generate_embeddings
    from app.copilot.models import CopilotDocumentChunk

    # Step 1: Handle File Storage
    if file_content is None:
        # If content not provided, download from R2 (assumes already uploaded)
        if not document.filename:
             raise ValueError("Filename required to download from R2")
        file_content = await download_from_r2(document.filename)
    else:
        # Upload to R2
        file_url = await upload_to_r2(
            file_content=file_content,
            filename=document.filename,
            content_type=f"application/{file_type}",
        )
        document.file_url = file_url

    # Step 2: Extract text
    text_content = await extract_text(file_content, file_type)
    
    if not text_content or not text_content.strip():
        document.status = "completed"
        document.processing_completed_at = datetime.now(timezone.utc)
        document.error_message = "Warning: No text content extracted from file."
        document.total_chunks = 0
        document.total_tokens = 0
        session.add(document)
        session.commit()
        return {
            "status": "completed",
            "total_chunks": 0,
            "total_tokens": 0,
            "warning": "No text content extracted"
        }

    # Step 3: Chunk text
    chunks = chunk_text(text_content, chunk_size=1000, overlap=200)

    # Step 4 & 5: Generate embeddings and store
    total_tokens = 0
    for i, chunk in enumerate(chunks):
        embedding, tokens = await generate_embeddings(chunk["content"])
        total_tokens += tokens

        doc_chunk = CopilotDocumentChunk(
            document_id=document.id,
            chunk_index=i,
            content=chunk["content"],
            embedding=embedding,
            start_char=chunk.get("start_char"),
            end_char=chunk.get("end_char"),
            page_number=chunk.get("page_number"),
            section=chunk.get("section"),
            token_count=tokens,
            chunk_metadata=chunk.get("metadata", {}),
        )
        session.add(doc_chunk)

    # Update document
    document.total_chunks = len(chunks)
    document.total_tokens = total_tokens
    document.status = "completed"
    document.processing_completed_at = datetime.now(timezone.utc)
    session.add(document)
    session.commit()

    return {
        "status": "completed",
        "total_chunks": len(chunks),
        "total_tokens": total_tokens,
    }


@shared_task(bind=True, max_retries=3, default_retry_delay=10)
def generate_embeddings_task(
    self,
    texts: list[str],
    document_id: str | None = None,
) -> dict:
    """
    Generate embeddings for a batch of texts.

    Args:
        texts: List of text strings to embed
        document_id: Optional document ID for context

    Returns:
        Dict with embedding results
    """
    import asyncio
    from app.copilot.rag.embeddings import generate_batch_embeddings

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            results = loop.run_until_complete(generate_batch_embeddings(texts))
        finally:
            loop.close()

        return {
            "status": "completed",
            "count": len(results),
            "total_tokens": sum(tokens for _, tokens in results),
        }

    except Exception as e:
        raise self.retry(exc=e)
