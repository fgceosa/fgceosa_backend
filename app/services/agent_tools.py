"""
Agent Tools Framework

This module defines the tool system for autonomous copilot agents.
Tools allow agents to retrieve documents, search the web, call APIs, and perform actions.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional, Callable
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from sqlmodel import Session, select, func, or_
from sqlalchemy import text

logger = logging.getLogger(__name__)


class ToolParameter(BaseModel):
    """Definition of a tool parameter"""
    name: str
    type: str  # "string", "number", "boolean", "object", "array"
    description: str
    required: bool = True
    enum: Optional[List[str]] = None


class ToolDefinition(BaseModel):
    """Definition of an agent tool"""
    name: str
    description: str
    parameters: List[ToolParameter]
    capability_required: Optional[str] = None  # e.g., "web-search", "api-integration"


class ToolResult(BaseModel):
    """Result from tool execution"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentTool:
    """Base class for agent tools"""
    
    def __init__(self, name: str, description: str, capability_required: Optional[str] = None):
        self.name = name
        self.description = description
        self.capability_required = capability_required
    
    def get_definition(self) -> ToolDefinition:
        """Return the tool definition for the AI model"""
        raise NotImplementedError
    
    async def execute(self, **kwargs) -> ToolResult:
        """Execute the tool with given parameters"""
        raise NotImplementedError
    
    def is_enabled(self, copilot_capabilities: List[str]) -> bool:
        """Check if this tool is enabled based on copilot capabilities"""
        if not self.capability_required:
            return True
        return self.capability_required in copilot_capabilities


class RetrieveDocumentsTool(AgentTool):
    """Tool for retrieving relevant documents from the copilot's knowledge base"""
    
    def __init__(self, session: Session, copilot_id: uuid.UUID):
        super().__init__(
            name="retrieve_documents",
            description="Search the knowledge base for information in uploaded documents. ALWAYS use this tool if the user's request involves specific documents, data, or files they have provided to you.",
            capability_required=None  # Always available if documents exist
        )
        self.session = session
        self.copilot_id = copilot_id
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The search query to find relevant document chunks",
                    required=True
                ),
                ToolParameter(
                    name="document_title",
                    type="string",
                    description="Optional: Filter search to a specific document title (e.g., 'ai engineering plan.pdf')",
                    required=False
                ),
                ToolParameter(
                    name="top_k",
                    type="number",
                    description="Number of relevant chunks to retrieve (default: 8)",
                    required=False
                )
            ]
        )
    
    async def execute(self, query: str, document_title: Optional[str] = None, top_k: int = 8) -> ToolResult:
        """Execute document retrieval"""
        try:
            from app.copilot.models import CopilotDocument, CopilotDocumentChunk
            from app.copilot.rag.embeddings import generate_embeddings
            from sqlalchemy import or_, func
            
            # Fetch all completed documents for this copilot to help with matching
            all_docs_stmt = select(CopilotDocument).where(
                CopilotDocument.copilot_id == self.copilot_id,
                CopilotDocument.status == 'completed'
            )
            all_docs = list(self.session.exec(all_docs_stmt).all())
            
            if not all_docs:
                return ToolResult(
                    success=False,
                    error="Your knowledge base is currently empty. Please upload documents first."
                )

            # If document_title is missing, try to detect it from the query
            if not document_title:
                query_lower = query.lower()
                for doc in all_docs:
                    doc_id_str = str(doc.id).lower()
                    doc_title_lower = (doc.title or "").lower()
                    doc_filename_lower = (doc.original_filename or "").lower()
                    
                    if (doc_title_lower and doc_title_lower in query_lower) or \
                       (doc_filename_lower and doc_filename_lower in query_lower) or \
                       (doc_id_str in query_lower):
                        document_title = doc.title or doc.original_filename
                        logger.info(f"[RAG] Auto-detected document filter: {document_title}")
                        break

            # Verify if the requested document exists
            target_doc = None
            if document_title:
                doc_title_lower = document_title.lower()
                for doc in all_docs:
                    if (doc.title and doc.title.lower() == doc_title_lower) or \
                       (doc.original_filename and doc.original_filename.lower() == doc_title_lower) or \
                       (doc.filename and doc.filename.lower() == doc_title_lower):
                        target_doc = doc
                        break
                
                if not target_doc:
                    return ToolResult(
                        success=False,
                        error=f"Document '{document_title}' not found in your knowledge base."
                    )

            # Generate query embedding
            query_embedding, _ = await generate_embeddings(query)
            
            # Use a slightly more permissive threshold if searching within a specific document
            threshold = 0.10 if target_doc else 0.15
            
            # Perform vector search
            # We use proper parameter binding for security and robustness
            search_params = {
                "copilot_id": self.copilot_id,
                "embedding": query_embedding,
                "threshold": threshold,
                "limit": top_k
            }
            
            filter_clause = "AND d.copilot_id = :copilot_id"
            if target_doc:
                filter_clause += " AND d.id = :doc_id"
                search_params["doc_id"] = target_doc.id
            
            raw_query = text(f"""
                SELECT
                    d.title as document_title,
                    d.original_filename,
                    c.content,
                    1 - (c.embedding <=> CAST(:embedding AS vector)) as similarity_score,
                    c.chunk_index,
                    c.page_number
                FROM copilot.copilot_document_chunk c
                JOIN copilot.copilot_document d ON c.document_id = d.id
                WHERE d.status = 'completed'
                  {filter_clause}
                  AND 1 - (c.embedding <=> CAST(:embedding AS vector)) >= :threshold
                ORDER BY c.embedding <=> CAST(:embedding AS vector)
                LIMIT :limit
            """)
            
            result = self.session.exec(raw_query, params=search_params)
            chunks = list(result.all())
            
            # Fallback: If no semantic results and we're looking at a specific document,
            # or if the query contains generic "overview" keywords, return the first few chunks
            overview_keywords = ["overview", "about", "tell me", "summary", "what is", "contents", "details", "explain", "describe", "plan"]
            is_overview_query = any(word in query.lower() for word in overview_keywords)
            
            if not chunks and target_doc and (is_overview_query or len(query.split()) < 4):
                logger.info(f"[RAG] Semantic search failed, falling back to sequential chunks for {target_doc.title}")
                fallback_query = text("""
                    SELECT
                        d.title as document_title,
                        d.original_filename,
                        c.content,
                        0.05 as similarity_score,
                        c.chunk_index,
                        c.page_number
                    FROM copilot.copilot_document_chunk c
                    JOIN copilot.copilot_document d ON c.document_id = d.id
                    WHERE d.id = :doc_id
                    ORDER BY c.chunk_index ASC
                    LIMIT 5
                """)
                result = self.session.exec(fallback_query, params={"doc_id": target_doc.id})
                chunks = list(result.all())

            if not chunks:
                msg = "No relevant information found."
                if target_doc:
                    msg = f"I couldn't find relevant details in '{target_doc.title}' for your specific query."
                return ToolResult(
                    success=True,
                    data=[],
                    metadata={"message": msg}
                )
            
            # Format results
            documents = []
            for chunk in chunks:
                documents.append({
                    "document_title": chunk.document_title or chunk.original_filename,
                    "content": chunk.content,
                    "similarity_score": float(chunk.similarity_score),
                    "chunk_index": getattr(chunk, "chunk_index", 0),
                    "page_number": getattr(chunk, "page_number", None)
                })
            
            return ToolResult(
                success=True,
                data=documents,
                metadata={
                    "total_chunks": len(documents),
                    "query": query,
                    "document_filtered": target_doc.title if target_doc else None
                }
            )
            
        except Exception as e:
            self.session.rollback()
            logger.error(f"Document retrieval failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Failed to retrieve documents: {str(e)}"
            )



class WebSearchTool(AgentTool):
    """Tool for searching the web for live information"""
    
    def __init__(self):
        super().__init__(
            name="web_search",
            description="Search the internet for real-time information, news, websites, and data. Use this tool if you don't have the answer in your knowledge base, including for tasks like finding flight details, company info, or external resources.",
            capability_required="web-search"
        )
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="query",
                    type="string",
                    description="The search query",
                    required=True
                ),
                ToolParameter(
                    name="max_results",
                    type="number",
                    description="Maximum number of results to return (default: 5)",
                    required=False
                )
            ],
            capability_required=self.capability_required
        )
    
    async def execute(self, query: str, max_results: int = 5) -> ToolResult:
        """Execute web search"""
        try:
            from app.services.web_search_service import web_search_service
            
            results = await web_search_service.search(query, max_results=max_results)
            
            return ToolResult(
                success=True,
                data=results,
                metadata={
                    "query": query,
                    "result_count": len(results)
                }
            )
            
        except Exception as e:
            logger.error(f"Web search failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Web search failed: {str(e)}"
            )


class FetchURLTool(AgentTool):
    """Tool for fetching content from a specific URL"""
    
    def __init__(self):
        super().__init__(
            name="fetch_url",
            description="Fetch and extract content from a specific URL. Use this to read web pages, articles, or online resources.",
            capability_required="web-search"
        )
    
    def get_definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="url",
                    type="string",
                    description="The URL to fetch",
                    required=True
                )
            ],
            capability_required=self.capability_required
        )
    
    async def execute(self, url: str) -> ToolResult:
        """Fetch URL content"""
        try:
            import httpx
            from bs4 import BeautifulSoup
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(url, follow_redirects=True)
                response.raise_for_status()
                
                # Extract text content
                soup = BeautifulSoup(response.text, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Get text
                text = soup.get_text()
                
                # Clean up whitespace
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)
                
                # Limit to first 10000 characters
                text = text[:10000]
                
                return ToolResult(
                    success=True,
                    data={
                        "url": url,
                        "content": text,
                        "title": soup.title.string if soup.title else None
                    },
                    metadata={
                        "content_length": len(text)
                    }
                )
                
        except Exception as e:
            logger.error(f"URL fetch failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Failed to fetch URL: {str(e)}"
            )


class ToolRegistry:
    """Registry for managing available agent tools"""
    
    def __init__(self):
        self._tools: Dict[str, AgentTool] = {}
    
    def register(self, tool: AgentTool):
        """Register a tool"""
        self._tools[tool.name] = tool
    
    def get_tool(self, name: str) -> Optional[AgentTool]:
        """Get a tool by name"""
        return self._tools.get(name)
    
    def get_enabled_tools(self, copilot_capabilities: List[str]) -> List[AgentTool]:
        """Get all enabled tools based on copilot capabilities"""
        return [
            tool for tool in self._tools.values()
            if tool.is_enabled(copilot_capabilities)
        ]
    
    def get_tool_definitions(self, copilot_capabilities: List[str]) -> List[Dict[str, Any]]:
        """Get OpenAI-compatible tool definitions for enabled tools"""
        enabled_tools = self.get_enabled_tools(copilot_capabilities)
        
        definitions = []
        for tool in enabled_tools:
            tool_def = tool.get_definition()
            
            # Convert to OpenAI function calling format
            parameters_schema = {
                "type": "object",
                "properties": {},
                "required": []
            }
            
            for param in tool_def.parameters:
                parameters_schema["properties"][param.name] = {
                    "type": param.type,
                    "description": param.description
                }
                if param.enum:
                    parameters_schema["properties"][param.name]["enum"] = param.enum
                
                if param.required:
                    parameters_schema["required"].append(param.name)
            
            definitions.append({
                "type": "function",
                "function": {
                    "name": tool_def.name,
                    "description": tool_def.description,
                    "parameters": parameters_schema
                }
            })
        
        return definitions


# Global tool registry instance
tool_registry = ToolRegistry()
