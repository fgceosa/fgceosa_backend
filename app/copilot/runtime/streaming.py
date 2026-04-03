"""
Streaming Handler for Server-Sent Events (SSE)
Handles real-time streaming of agent responses
"""
import json
import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

from fastapi import Response
from fastapi.responses import StreamingResponse
from sqlmodel import Session

from app.copilot.models import (
    Copilot,
    CopilotConversation,
    CopilotMessage,
)
from app.copilot.runtime.executor import AgentExecutor, ExecutionContext
from app.copilot.runtime.tool_handler import ToolHandler


class StreamingHandler:
    """
    Handler for streaming agent responses via Server-Sent Events.

    Provides real-time updates as the agent:
    - Generates text
    - Calls tools
    - Returns results
    """

    def __init__(
        self,
        copilot: Copilot,
        conversation: CopilotConversation,
        session: Session,
        user_id: uuid.UUID,
    ):
        self.copilot = copilot
        self.conversation = conversation
        self.session = session
        self.user_id = user_id

    async def stream_response(self, user_message: str) -> StreamingResponse:
        """
        Create a streaming response for the agent execution.

        Returns a FastAPI StreamingResponse with SSE format.
        """
        return StreamingResponse(
            self._generate_stream(user_message),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    async def _generate_stream(self, user_message: str) -> AsyncIterator[str]:
        """
        Generator that yields SSE-formatted events.
        """
        # Initialize tools
        tool_handler = ToolHandler(
            copilot=self.copilot,
            session=self.session,
            user_id=self.user_id,
        )
        tools = tool_handler.initialize_tools()

        # Create execution context
        context = ExecutionContext(
            copilot=self.copilot,
            conversation=self.conversation,
            user_id=self.user_id,
            session=self.session,
            tools=tools,
            max_iterations=10,
        )

        # Create executor
        executor = AgentExecutor(context)

        # Save user message first
        user_msg = CopilotMessage(
            conversation_id=self.conversation.id,
            role="user",
            content=user_message,
        )
        self.session.add(user_msg)
        self.session.commit()
        self.session.refresh(user_msg)

        # Yield user message event
        yield self._format_sse("user_message", {
            "message_id": str(user_msg.id),
            "content": user_message,
        })

        # Stream the execution
        full_content = ""
        all_tool_calls = []

        try:
            async for chunk in executor.execute_streaming(user_message):
                chunk_type = chunk.get("type")

                if chunk_type == "content":
                    content = chunk.get("content", "")
                    full_content += content
                    yield self._format_sse("content", {"text": content})

                elif chunk_type == "tool_call":
                    tool_call = chunk.get("tool_call", {})
                    all_tool_calls.append(tool_call)
                    yield self._format_sse("tool_call", {
                        "id": tool_call.get("id"),
                        "name": tool_call.get("function", {}).get("name"),
                        "arguments": tool_call.get("function", {}).get("arguments"),
                    })

                elif chunk_type == "tool_result":
                    yield self._format_sse("tool_result", {
                        "tool_call_id": chunk.get("tool_call_id"),
                        "success": chunk.get("result", {}).get("success"),
                        "data": chunk.get("result", {}).get("data"),
                        "error": chunk.get("result", {}).get("error"),
                    })

                elif chunk_type == "done":
                    # Save assistant message
                    assistant_msg = CopilotMessage(
                        conversation_id=self.conversation.id,
                        role="assistant",
                        content=chunk.get("content", full_content),
                        tool_calls=all_tool_calls if all_tool_calls else None,
                        tokens_used=chunk.get("tokens_used"),
                        response_time_ms=chunk.get("response_time_ms"),
                        model_used=self.copilot.model,
                    )
                    self.session.add(assistant_msg)

                    # Update conversation
                    self.conversation.message_count += 2
                    self.conversation.total_tokens_used += chunk.get("tokens_used", 0)
                    self.conversation.last_message_at = datetime.now(timezone.utc)
                    self.conversation.updated_at = datetime.now(timezone.utc)

                    # Update copilot usage
                    self.copilot.usage_count += 1

                    self.session.add(self.conversation)
                    self.session.add(self.copilot)
                    self.session.commit()
                    self.session.refresh(assistant_msg)

                    yield self._format_sse("done", {
                        "message_id": str(assistant_msg.id),
                        "conversation_id": str(self.conversation.id),
                        "tokens_used": chunk.get("tokens_used"),
                        "response_time_ms": chunk.get("response_time_ms"),
                        "iterations": chunk.get("iterations"),
                    })

        except Exception as e:
            yield self._format_sse("error", {
                "message": str(e),
            })

    def _format_sse(self, event: str, data: dict) -> str:
        """Format data as Server-Sent Event."""
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def create_streaming_response(
    copilot: Copilot,
    conversation: CopilotConversation,
    session: Session,
    user_id: uuid.UUID,
    user_message: str,
) -> StreamingResponse:
    """
    Convenience function to create a streaming response.
    """
    handler = StreamingHandler(
        copilot=copilot,
        conversation=conversation,
        session=session,
        user_id=user_id,
    )
    return await handler.stream_response(user_message)
