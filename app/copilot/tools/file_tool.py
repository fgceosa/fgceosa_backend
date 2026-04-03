"""
File Retrieval Tool for Copilot Agents
Retrieves files from R2 storage
"""
import time
import uuid
from typing import Any

from app.copilot.tools.base import BaseTool, ToolResult, register_tool


@register_tool
class FileRetrievalTool(BaseTool):
    """
    Tool for retrieving files from the copilot's document storage.
    """

    name = "file_retrieval"
    description = """Retrieve a file from the copilot's document storage.
    Use this tool to get download URLs for uploaded documents.
    Can search by file ID or filename."""

    parameters_schema = {
        "type": "object",
        "properties": {
            "file_id": {
                "type": "string",
                "description": "UUID of the file to retrieve",
            },
            "filename": {
                "type": "string",
                "description": "Name of the file to search for",
            },
        },
        "required": [],  # At least one should be provided
    }

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.copilot_id = config.get("copilot_id") if config else None
        self.session = config.get("session") if config else None

    async def execute(
        self,
        file_id: str | None = None,
        filename: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """
        Retrieve file information and download URL.
        """
        start_time = time.time()

        if not file_id and not filename:
            return ToolResult(
                success=False,
                error="Either file_id or filename must be provided",
            )

        try:
            from sqlmodel import Session, select
            from app.copilot.models import CopilotDocument
            from app.copilot.rag.storage import generate_presigned_url
            from app.core.db import copilot_engine

            # Use provided session or create new one
            if self.session:
                session = self.session
                # Build query
                statement = select(CopilotDocument)

                if file_id:
                    statement = statement.where(CopilotDocument.id == uuid.UUID(file_id))
                elif filename:
                    statement = statement.where(
                        CopilotDocument.original_filename.ilike(f"%{filename}%")
                    )

                if self.copilot_id:
                    statement = statement.where(CopilotDocument.copilot_id == self.copilot_id)

                document = session.exec(statement).first()
            else:
                with Session(copilot_engine) as session:
                    # Build query
                    statement = select(CopilotDocument)

                    if file_id:
                        statement = statement.where(CopilotDocument.id == uuid.UUID(file_id))
                    elif filename:
                        statement = statement.where(
                            CopilotDocument.original_filename.ilike(f"%{filename}%")
                        )

                    if self.copilot_id:
                        statement = statement.where(CopilotDocument.copilot_id == self.copilot_id)

                    document = session.exec(statement).first()

            if not document:
                execution_time = int((time.time() - start_time) * 1000)
                return ToolResult(
                    success=False,
                    error="File not found",
                    execution_time_ms=execution_time,
                )

            # Generate presigned URL for download
            download_url = await generate_presigned_url(
                filename=document.filename,
                folder="copilot-documents",
                expiration=3600,  # 1 hour
            )

            execution_time = int((time.time() - start_time) * 1000)

            return ToolResult(
                success=True,
                data={
                    "file_id": str(document.id),
                    "filename": document.original_filename,
                    "file_type": document.file_type,
                    "file_size": document.file_size,
                    "download_url": download_url,
                    "title": document.title,
                    "description": document.description,
                    "status": document.status,
                },
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"File retrieval failed: {str(e)}",
                execution_time_ms=execution_time,
            )
