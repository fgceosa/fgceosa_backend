"""
Email Sending Tool for Copilot Agents
Sends emails via Postmark API
"""
import time
from typing import Any

import httpx

from app.core.config import settings
from app.copilot.tools.base import BaseTool, ToolResult, register_tool


@register_tool
class EmailSendTool(BaseTool):
    """
    Tool for sending emails via Postmark.
    """

    name = "email_send"
    description = """Send an email to specified recipients.
    Use this tool to send notifications, reports, or other emails.
    Supports HTML content, CC, BCC, and reply-to fields."""

    parameters_schema = {
        "type": "object",
        "properties": {
            "to": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of recipient email addresses",
            },
            "subject": {
                "type": "string",
                "description": "Email subject line",
            },
            "body": {
                "type": "string",
                "description": "Plain text email body",
            },
            "html_body": {
                "type": "string",
                "description": "HTML email body (optional)",
            },
            "cc": {
                "type": "array",
                "items": {"type": "string"},
                "description": "CC recipients (optional)",
            },
            "bcc": {
                "type": "array",
                "items": {"type": "string"},
                "description": "BCC recipients (optional)",
            },
            "reply_to": {
                "type": "string",
                "description": "Reply-to email address (optional)",
            },
        },
        "required": ["to", "subject", "body"],
    }

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.from_email = config.get("from_email", settings.EMAILS_FROM_EMAIL) if config else settings.EMAILS_FROM_EMAIL
        self.from_name = config.get("from_name", settings.EMAILS_FROM_NAME) if config else settings.EMAILS_FROM_NAME
        self.postmark_token = config.get("postmark_token", settings.POSTMARK_API_TOKEN) if config else settings.POSTMARK_API_TOKEN

    async def execute(
        self,
        to: list[str],
        subject: str,
        body: str,
        html_body: str | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
        reply_to: str | None = None,
        **kwargs,
    ) -> ToolResult:
        """
        Send an email via Postmark API.
        """
        start_time = time.time()

        if not self.postmark_token:
            return ToolResult(
                success=False,
                error="Postmark API token not configured",
            )

        try:
            # Build Postmark payload
            payload = {
                "From": f"{self.from_name} <{self.from_email}>",
                "To": ", ".join(to),
                "Subject": subject,
                "TextBody": body,
            }

            if html_body:
                payload["HtmlBody"] = html_body

            if cc:
                payload["Cc"] = ", ".join(cc)

            if bcc:
                payload["Bcc"] = ", ".join(bcc)

            if reply_to:
                payload["ReplyTo"] = reply_to

            # Send via Postmark
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    "https://api.postmarkapp.com/email",
                    json=payload,
                    headers={
                        "Accept": "application/json",
                        "Content-Type": "application/json",
                        "X-Postmark-Server-Token": self.postmark_token,
                    },
                )

            execution_time = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                return ToolResult(
                    success=True,
                    data={
                        "message_id": data.get("MessageID"),
                        "submitted_at": data.get("SubmittedAt"),
                        "to": to,
                    },
                    execution_time_ms=execution_time,
                )
            else:
                error_data = response.json()
                return ToolResult(
                    success=False,
                    error=f"Email send failed: {error_data.get('Message', 'Unknown error')}",
                    execution_time_ms=execution_time,
                )

        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return ToolResult(
                success=False,
                error=f"Email send failed: {str(e)}",
                execution_time_ms=execution_time,
            )
