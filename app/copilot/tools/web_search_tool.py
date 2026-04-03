"""
Web Search Tool for Copilot Agents
Performs web searches using configured search API
"""
import time
from typing import Any

import httpx

from app.core.config import settings
from app.copilot.tools.base import BaseTool, ToolResult, register_tool


@register_tool
class WebSearchTool(BaseTool):
    """
    Tool for performing web searches.
    Uses Tavily API for search capabilities.
    """

    name = "web_search"
    description = """Search the web for current information.
    Use this tool when you need up-to-date information, news, or facts
    that may not be in the knowledge base. Returns relevant search results."""

    parameters_schema = {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "num_results": {
                "type": "integer",
                "description": "Number of results to return (default: 5)",
                "default": 5,
            },
        },
        "required": ["query"],
    }

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.api_key = config.get("tavily_api_key") if config else None
        if not self.api_key:
            self.api_key = getattr(settings, "TAVILY_API_KEY", None)

    async def execute(
        self,
        query: str,
        num_results: int = 5,
        **kwargs,
    ) -> ToolResult:
        """
        Execute a web search.
        """
        start_time = time.time()

        if not self.api_key:
            return ToolResult(
                success=False,
                error="Web search API key not configured",
            )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": self.api_key,
                        "query": query,
                        "max_results": num_results,
                        "include_answer": True,
                        "include_raw_content": False,
                    },
                )

            execution_time = int((time.time() - start_time) * 1000)

            if response.status_code != 200:
                return ToolResult(
                    success=False,
                    error=f"Search API returned status {response.status_code}",
                    execution_time_ms=execution_time,
                )

            data = response.json()

            # Format results
            results = []
            for item in data.get("results", []):
                results.append({
                    "title": item.get("title"),
                    "url": item.get("url"),
                    "content": item.get("content"),
                    "score": item.get("score"),
                })

            # Format as readable text
            formatted_text = f"Web search results for: {query}\n\n"
            if data.get("answer"):
                formatted_text += f"Summary: {data['answer']}\n\n"

            for i, r in enumerate(results, 1):
                formatted_text += f"[{i}] {r['title']}\n"
                formatted_text += f"URL: {r['url']}\n"
                formatted_text += f"{r['content'][:300]}...\n\n"

            return ToolResult(
                success=True,
                data={
                    "results": results,
                    "answer": data.get("answer"),
                    "formatted": formatted_text,
                    "count": len(results),
                },
                execution_time_ms=execution_time,
            )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"Web search failed: {str(e)}",
                execution_time_ms=execution_time,
            )
