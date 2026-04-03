"""
RAG Search Tool for Copilot Agents
Searches copilot knowledge base using vector similarity
"""
import time
import uuid
from typing import Any

from sqlmodel import Session

from app.copilot.tools.base import BaseTool, ToolResult, register_tool


@register_tool
class RAGSearchTool(BaseTool):
    """
    Tool for searching copilot's document knowledge base using RAG.
    Uses pgvector for semantic similarity search.
    """

    name = "rag_search"
    description = """Search the copilot's knowledge base for relevant information.
    Use this tool when you need to find specific information from uploaded documents,
    policies, or reference materials. Returns the most relevant text chunks."""

    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query to find relevant documents",
            },
            "top_k": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
            "similarity_threshold": {
                "type": "number",
                "description": "Minimum similarity score (0-1, default: 0.7)",
                "default": 0.7,
            },
        },
        "required": ["query"],
    }

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.copilot_id = config.get("copilot_id") if config else None
        self.session = config.get("session") if config else None

    async def execute(
        self,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.7,
        **kwargs,
    ) -> ToolResult:
        """
        Execute RAG search against the copilot's knowledge base.
        """
        start_time = time.time()

        if not self.copilot_id:
            return ToolResult(
                success=False,
                error="Copilot ID not configured for RAG search",
            )

        try:
            from app.copilot.rag.embeddings import generate_embeddings
            from app.core.db import copilot_engine
            from sqlalchemy import text

            # Generate query embedding
            query_embedding, _ = await generate_embeddings(query)

            # Use provided session or create new one
            if self.session:
                session = self.session
                # Vector similarity search
                search_query = text("""
                    SELECT
                        c.id as chunk_id,
                        c.document_id,
                        d.title as document_title,
                        c.content,
                        1 - (c.embedding <=> :embedding::vector) as similarity_score,
                        c.page_number,
                        c.section
                    FROM copilot_document_chunk c
                    JOIN copilot_document d ON c.document_id = d.id
                    WHERE d.copilot_id = :copilot_id
                      AND d.status = 'completed'
                      AND 1 - (c.embedding <=> :embedding::vector) >= :threshold
                    ORDER BY c.embedding <=> :embedding::vector
                    LIMIT :limit
                """)

                result = session.exec(
                    search_query,
                    params={
                        "copilot_id": str(self.copilot_id),
                        "embedding": query_embedding,
                        "threshold": similarity_threshold,
                        "limit": top_k,
                    }
                )
                rows = result.fetchall()
            else:
                with Session(copilot_engine) as session:
                    # Vector similarity search
                    search_query = text("""
                        SELECT
                            c.id as chunk_id,
                            c.document_id,
                            d.title as document_title,
                            c.content,
                            1 - (c.embedding <=> :embedding::vector) as similarity_score,
                            c.page_number,
                            c.section
                        FROM copilot_document_chunk c
                        JOIN copilot_document d ON c.document_id = d.id
                        WHERE d.copilot_id = :copilot_id
                          AND d.status = 'completed'
                          AND 1 - (c.embedding <=> :embedding::vector) >= :threshold
                        ORDER BY c.embedding <=> :embedding::vector
                        LIMIT :limit
                    """)

                    result = session.exec(
                        search_query,
                        params={
                            "copilot_id": str(self.copilot_id),
                            "embedding": query_embedding,
                            "threshold": similarity_threshold,
                            "limit": top_k,
                        }
                    )
                    rows = result.fetchall()

            # Format results
            results = []
            for row in rows:
                results.append({
                    "document_title": row.document_title,
                    "content": row.content,
                    "similarity": round(float(row.similarity_score), 4),
                    "page_number": row.page_number,
                    "section": row.section,
                })

            execution_time = int((time.time() - start_time) * 1000)

            if not results:
                return ToolResult(
                    success=True,
                    data={
                        "results": [],
                        "message": "No relevant documents found for the query.",
                    },
                    execution_time_ms=execution_time,
                )

            # Format as readable text for the agent
            formatted_text = f"Found {len(results)} relevant document(s):\n\n"
            for i, r in enumerate(results, 1):
                formatted_text += f"[{i}] {r['document_title']}"
                if r["page_number"]:
                    formatted_text += f" (Page {r['page_number']})"
                formatted_text += f"\nRelevance: {r['similarity']}\n"
                formatted_text += f"Content: {r['content'][:500]}...\n\n"

            return ToolResult(
                success=True,
                data={
                    "results": results,
                    "formatted": formatted_text,
                    "count": len(results),
                },
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"RAG search failed: {str(e)}",
                execution_time_ms=execution_time,
            )
