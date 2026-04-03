"""
Tool Handler - Manages tool initialization and execution for copilots
"""
import uuid
from typing import Optional

from sqlmodel import Session, select

from app.copilot.models import Copilot, CopilotTool
from app.copilot.tools.base import BaseTool, tool_registry
from app.copilot.tools.rag_tool import RAGSearchTool
from app.copilot.tools.http_tool import HTTPRequestTool
from app.copilot.tools.database_tool import DatabaseQueryTool
from app.copilot.tools.email_tool import EmailSendTool
from app.copilot.tools.file_tool import FileRetrievalTool
from app.copilot.tools.web_search_tool import WebSearchTool


class ToolHandler:
    """
    Handles tool initialization and management for a copilot.

    Tools can be:
    1. Built-in tools (RAG, HTTP, DB, Email, etc.)
    2. Custom tools defined in the database
    """

    # Map of built-in tool types to classes
    BUILTIN_TOOLS = {
        "rag_search": RAGSearchTool,
        "http_request": HTTPRequestTool,
        "database_query": DatabaseQueryTool,
        "email_send": EmailSendTool,
        "file_retrieval": FileRetrievalTool,
        "web_search": WebSearchTool,
    }

    def __init__(
        self,
        copilot: Copilot,
        session: Session,
        user_id: uuid.UUID,
    ):
        self.copilot = copilot
        self.session = session
        self.user_id = user_id
        self.tools: list[BaseTool] = []

    def initialize_tools(self) -> list[BaseTool]:
        """
        Initialize all tools available to the copilot.

        Returns list of instantiated tool objects.
        """
        self.tools = []

        # Add built-in tools based on capabilities
        self._add_builtin_tools()

        # Add custom tools from database
        self._add_custom_tools()

        return self.tools

    def _add_builtin_tools(self) -> None:
        """Add built-in tools based on copilot capabilities."""
        capabilities = self.copilot.capabilities or []

        # Base config for all tools
        base_config = {
            "copilot_id": self.copilot.id,
            "session": self.session,
        }

        # RAG Search - always available if documents exist
        if "memory" in capabilities or True:  # Default enabled
            self.tools.append(RAGSearchTool(config=base_config))

        # File Retrieval - always available
        self.tools.append(FileRetrievalTool(config=base_config))

        # Web Search
        if "web-search" in capabilities:
            self.tools.append(WebSearchTool())

        # HTTP Request
        if "api-integration" in capabilities:
            # Get allowed domains from copilot config
            allowed_domains = self.copilot.tools_config.get("http_allowed_domains", [])
            self.tools.append(HTTPRequestTool(config={
                "allowed_domains": allowed_domains,
            }))

        # Database Query
        if "function-calling" in capabilities:
            # Only allow read-only queries
            self.tools.append(DatabaseQueryTool(config={
                "read_only": True,
                "max_rows": 100,
            }))

        # Email Send
        # Check if email is configured in copilot tools_config
        if self.copilot.tools_config.get("email_enabled"):
            self.tools.append(EmailSendTool(config={
                "from_email": self.copilot.tools_config.get("email_from"),
                "from_name": self.copilot.tools_config.get("email_from_name"),
            }))

    def _add_custom_tools(self) -> None:
        """Add custom tools defined in the database."""
        statement = select(CopilotTool).where(
            CopilotTool.copilot_id == self.copilot.id,
            CopilotTool.is_enabled == True,
        )
        custom_tools = self.session.exec(statement).all()

        for db_tool in custom_tools:
            tool = CustomToolWrapper(
                tool_id=db_tool.id,
                name=db_tool.name,
                description=db_tool.description,
                parameters_schema=db_tool.parameters_schema,
                config=db_tool.config,
                requires_confirmation=db_tool.requires_confirmation,
            )
            self.tools.append(tool)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """Get a tool by name."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        return None

    def get_tool_schemas(self) -> list[dict]:
        """Get OpenAI-format schemas for all tools."""
        return [tool.get_openai_schema() for tool in self.tools]


class CustomToolWrapper(BaseTool):
    """
    Wrapper for custom tools defined in the database.

    Custom tools are HTTP-based by default - they make calls to
    configured endpoints when invoked.
    """

    def __init__(
        self,
        tool_id: uuid.UUID,
        name: str,
        description: str,
        parameters_schema: dict,
        config: dict,
        requires_confirmation: bool = False,
    ):
        super().__init__(config)
        self.tool_id = tool_id
        self.name = name
        self.description = description
        self.parameters_schema = parameters_schema
        self.requires_confirmation = requires_confirmation

    async def execute(self, **params) -> "ToolResult":
        """Execute the custom tool."""
        from app.copilot.tools.base import ToolResult
        import httpx
        import time

        start_time = time.time()

        # Custom tools are HTTP-based
        endpoint = self.config.get("endpoint")
        method = self.config.get("method", "POST")
        headers = self.config.get("headers", {})
        timeout = self.config.get("timeout", 30)

        if not endpoint:
            return ToolResult(
                success=False,
                error="Custom tool has no endpoint configured",
            )

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(endpoint, params=params, headers=headers)
                else:
                    response = await client.post(endpoint, json=params, headers=headers)

            execution_time = int((time.time() - start_time) * 1000)

            try:
                data = response.json()
            except Exception:
                data = response.text

            return ToolResult(
                success=200 <= response.status_code < 300,
                data=data,
                error=None if response.status_code < 400 else f"HTTP {response.status_code}",
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"Custom tool execution failed: {str(e)}",
                execution_time_ms=execution_time,
            )
