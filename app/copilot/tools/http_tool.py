"""
HTTP Request Tool for Copilot Agents
Makes external HTTP API calls
"""
import time
from typing import Any

import httpx

from app.copilot.tools.base import BaseTool, ToolResult, register_tool


@register_tool
class HTTPRequestTool(BaseTool):
    """
    Tool for making HTTP requests to external APIs.
    Supports GET, POST, PUT, DELETE methods.
    """

    name = "http_request"
    description = """Make an HTTP request to an external API.
    Use this tool to fetch data from APIs, submit forms, or interact with web services.
    Supports GET, POST, PUT, DELETE methods with custom headers and body."""

    parameters_schema = {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to send the request to",
            },
            "method": {
                "type": "string",
                "description": "HTTP method (GET, POST, PUT, DELETE)",
                "enum": ["GET", "POST", "PUT", "DELETE"],
                "default": "GET",
            },
            "headers": {
                "type": "object",
                "description": "HTTP headers to send with the request",
                "default": {},
            },
            "body": {
                "type": "object",
                "description": "Request body (for POST/PUT)",
            },
            "timeout": {
                "type": "integer",
                "description": "Request timeout in seconds (default: 30)",
                "default": 30,
            },
        },
        "required": ["url"],
    }

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # Allowed domains (security measure)
        self.allowed_domains = config.get("allowed_domains", []) if config else []
        # Default headers
        self.default_headers = config.get("default_headers", {}) if config else {}

    async def execute(
        self,
        url: str,
        method: str = "GET",
        headers: dict | None = None,
        body: Any = None,
        timeout: int = 30,
        **kwargs,
    ) -> ToolResult:
        """
        Execute an HTTP request.
        """
        start_time = time.time()

        # Security: Check allowed domains if configured
        if self.allowed_domains:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            if parsed.netloc not in self.allowed_domains:
                return ToolResult(
                    success=False,
                    error=f"Domain not allowed: {parsed.netloc}",
                )

        try:
            # Merge headers
            request_headers = {**self.default_headers}
            if headers:
                request_headers.update(headers)

            # Make request
            async with httpx.AsyncClient(timeout=timeout) as client:
                if method.upper() == "GET":
                    response = await client.get(url, headers=request_headers)
                elif method.upper() == "POST":
                    response = await client.post(url, json=body, headers=request_headers)
                elif method.upper() == "PUT":
                    response = await client.put(url, json=body, headers=request_headers)
                elif method.upper() == "DELETE":
                    response = await client.delete(url, headers=request_headers)
                else:
                    return ToolResult(
                        success=False,
                        error=f"Unsupported HTTP method: {method}",
                    )

            execution_time = int((time.time() - start_time) * 1000)

            # Try to parse JSON response
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text[:5000]  # Limit text response

            # Check for success status codes
            is_success = 200 <= response.status_code < 300

            return ToolResult(
                success=is_success,
                data={
                    "status_code": response.status_code,
                    "headers": dict(response.headers),
                    "body": response_body,
                },
                error=None if is_success else f"HTTP {response.status_code}",
                execution_time_ms=execution_time,
            )

        except httpx.TimeoutException:
            execution_time = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"Request timed out after {timeout} seconds",
                execution_time_ms=execution_time,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"HTTP request failed: {str(e)}",
                execution_time_ms=execution_time,
            )
