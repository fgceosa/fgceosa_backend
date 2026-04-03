"""
Database Query Tool for Copilot Agents
Executes read-only SQL queries against configured databases
"""
import time
from typing import Any

from app.copilot.tools.base import BaseTool, ToolResult, register_tool


@register_tool
class DatabaseQueryTool(BaseTool):
    """
    Tool for executing database queries.
    By default, only allows read-only (SELECT) queries for safety.
    """

    name = "database_query"
    description = """Execute a SQL query against the database.
    Use this tool to retrieve data from database tables.
    By default, only SELECT queries are allowed for safety.
    Returns query results as a list of row dictionaries."""

    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "SQL query to execute (SELECT only by default)",
            },
            "params": {
                "type": "object",
                "description": "Query parameters for parameterized queries",
                "default": {},
            },
        },
        "required": ["query"],
    }

    # Dangerous SQL keywords to block
    BLOCKED_KEYWORDS = [
        "DROP", "DELETE", "TRUNCATE", "ALTER", "CREATE", "INSERT", "UPDATE",
        "GRANT", "REVOKE", "EXEC", "EXECUTE", "MERGE", "CALL",
    ]

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.read_only = config.get("read_only", True) if config else True
        self.allowed_tables = config.get("allowed_tables", []) if config else []
        self.max_rows = config.get("max_rows", 100) if config else 100

    def _is_safe_query(self, query: str) -> tuple[bool, str | None]:
        """
        Check if query is safe to execute.
        """
        query_upper = query.upper().strip()

        # Must start with SELECT for read-only mode
        if self.read_only and not query_upper.startswith("SELECT"):
            return False, "Only SELECT queries are allowed"

        # Block dangerous keywords
        for keyword in self.BLOCKED_KEYWORDS:
            if keyword in query_upper:
                return False, f"Query contains blocked keyword: {keyword}"

        # Check for comment-based SQL injection attempts
        if "--" in query or "/*" in query:
            return False, "SQL comments are not allowed"

        return True, None

    async def execute(
        self,
        query: str,
        params: dict | None = None,
        **kwargs,
    ) -> ToolResult:
        """
        Execute a database query.
        """
        start_time = time.time()

        # Validate query safety
        is_safe, error = self._is_safe_query(query)
        if not is_safe:
            return ToolResult(
                success=False,
                error=error,
            )

        try:
            from sqlalchemy import text
            from app.core.db import copilot_engine

            # Add LIMIT if not present
            if "LIMIT" not in query.upper():
                query = f"{query} LIMIT {self.max_rows}"

            with copilot_engine.connect() as connection:
                result = connection.execute(text(query), params or {})

                # Get column names
                columns = list(result.keys())

                # Fetch rows
                rows = []
                for row in result:
                    rows.append(dict(zip(columns, row)))

            execution_time = int((time.time() - start_time) * 1000)

            return ToolResult(
                success=True,
                data={
                    "rows": rows,
                    "row_count": len(rows),
                    "columns": columns,
                },
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"Database query failed: {str(e)}",
                execution_time_ms=execution_time,
            )
