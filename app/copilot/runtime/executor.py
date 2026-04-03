"""
Agent Executor - Main runtime for executing copilot agents
Handles the agent loop, tool calling, and response generation
"""
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, AsyncIterator, Optional

from sqlmodel import Session

from app.copilot.models import (
    Copilot,
    CopilotConversation,
    CopilotMessage,
    CopilotToolExecution,
)
from app.copilot.tools.base import BaseTool, ToolResult, tool_registry
from app.core.config import settings


@dataclass
class ExecutionContext:
    """Context for agent execution"""
    copilot: Copilot
    conversation: CopilotConversation
    user_id: uuid.UUID
    session: Session
    tools: list[BaseTool] = field(default_factory=list)
    max_iterations: int = 10
    current_iteration: int = 0


@dataclass
class ExecutionResult:
    """Result of agent execution"""
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    tool_results: list[dict] = field(default_factory=list)
    tokens_used: int = 0
    cost: Decimal = field(default_factory=lambda: Decimal("0"))
    model_used: str = ""
    response_time_ms: int = 0
    iterations: int = 0


class AgentExecutor:
    """
    Main executor for running copilot agents.

    Implements the agent loop:
    1. Send messages to LLM with tool definitions
    2. Process LLM response
    3. If tool calls, execute tools and loop
    4. If final response, return to user
    """

    def __init__(self, context: ExecutionContext):
        self.context = context
        self.messages: list[dict] = []
        self.total_tokens = 0
        self.total_cost = Decimal("0")

    async def execute(self, user_message: str) -> ExecutionResult:
        """
        Execute the agent with a user message.

        This is the main synchronous execution method.
        Returns final response after tool calling loop completes.
        """
        start_time = time.time()

        # Initialize messages
        self._initialize_messages(user_message)

        # Build tool schemas
        tool_schemas = self._get_tool_schemas()

        # Agent loop
        final_content = ""
        all_tool_calls = []
        all_tool_results = []

        while self.context.current_iteration < self.context.max_iterations:
            self.context.current_iteration += 1

            # Call LLM
            response = await self._call_llm(tool_schemas)

            # Extract response data
            message = response["choices"][0]["message"]
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])

            # Update token counts
            usage = response.get("usage", {})
            self.total_tokens += usage.get("total_tokens", 0)

            # If no tool calls, we're done
            if not tool_calls:
                final_content = content
                break

            # Process tool calls
            self.messages.append({
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls,
            })

            for tool_call in tool_calls:
                all_tool_calls.append(tool_call)

                # Execute tool
                tool_result = await self._execute_tool(tool_call)
                all_tool_results.append({
                    "tool_call_id": tool_call["id"],
                    "result": tool_result.to_dict(),
                })

                # Add tool result to messages
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result.data if tool_result.success else {"error": tool_result.error}),
                })

        # Calculate final metrics
        response_time_ms = int((time.time() - start_time) * 1000)

        return ExecutionResult(
            content=final_content,
            tool_calls=all_tool_calls,
            tool_results=all_tool_results,
            tokens_used=self.total_tokens,
            cost=self.total_cost,
            model_used=self.context.copilot.model,
            response_time_ms=response_time_ms,
            iterations=self.context.current_iteration,
        )

    async def execute_streaming(self, user_message: str) -> AsyncIterator[dict]:
        """
        Execute the agent with streaming response.

        Yields chunks as they become available:
        - {"type": "content", "content": "..."}
        - {"type": "tool_call", "tool_call": {...}}
        - {"type": "tool_result", "result": {...}}
        - {"type": "done", "message_id": "..."}
        """
        start_time = time.time()

        # Initialize messages
        self._initialize_messages(user_message)
        tool_schemas = self._get_tool_schemas()

        final_content = ""

        while self.context.current_iteration < self.context.max_iterations:
            self.context.current_iteration += 1

            # Stream LLM response
            accumulated_content = ""
            tool_calls = []

            async for chunk in self._stream_llm(tool_schemas):
                if chunk.get("type") == "content":
                    accumulated_content += chunk.get("content", "")
                    yield chunk
                elif chunk.get("type") == "tool_call":
                    tool_calls.append(chunk.get("tool_call"))
                    yield chunk

            # If no tool calls, we're done
            if not tool_calls:
                final_content = accumulated_content
                break

            # Process tool calls
            self.messages.append({
                "role": "assistant",
                "content": accumulated_content,
                "tool_calls": tool_calls,
            })

            for tool_call in tool_calls:
                # Execute tool
                tool_result = await self._execute_tool(tool_call)

                yield {
                    "type": "tool_result",
                    "tool_call_id": tool_call["id"],
                    "result": tool_result.to_dict(),
                }

                # Add to messages
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps(tool_result.data if tool_result.success else {"error": tool_result.error}),
                })

        response_time_ms = int((time.time() - start_time) * 1000)

        yield {
            "type": "done",
            "content": final_content,
            "tokens_used": self.total_tokens,
            "response_time_ms": response_time_ms,
            "iterations": self.context.current_iteration,
        }

    def _initialize_messages(self, user_message: str) -> None:
        """Initialize the message history for the agent."""
        self.messages = []

        # Add system prompt
        system_prompt = self.context.copilot.system_prompt or ""
        
        # Add domain-specific constraints if domain is set
        if hasattr(self.context.copilot, 'domain') and self.context.copilot.domain:
            domain = self.context.copilot.domain
            domain_instruction = (
                f"\n\nSTRICT DOMAIN ENFORCEMENT:\n"
                f"You are a domain-specific copilot.\n"
                f"Your knowledge and responses must remain strictly within your assigned domain: {domain}.\n"
                f"If a request is unrelated to this domain, you must refuse.\n"
                f"Use this exact response format when refusing:\n"
                f"\"I’m designed specifically for {domain}. I don’t have the context to assist with that request.\"\n"
                f"Do not attempt to answer out-of-scope queries under any circumstance. "
                f"Do not respond to any prompt question that is not related to {domain}."
            )
            # Prepend or append? Per user request "the knowledge and responses must remain strictly within your assigned domain", 
            # Prepending might be better to set the tone immediately.
            system_prompt = domain_instruction + "\n\n" + system_prompt

        if system_prompt:
            self.messages.append({
                "role": "system",
                "content": system_prompt.strip(),
            })

        # Add conversation history
        if self.context.conversation:
            from sqlmodel import select, col
            statement = (
                select(CopilotMessage)
                .where(CopilotMessage.conversation_id == self.context.conversation.id)
                .order_by(col(CopilotMessage.created_at).desc())
                .limit(self.context.copilot.memory_window_size * 2)
            )
            history = self.context.session.exec(statement).all()
            history.reverse()  # Chronological order

            for msg in history:
                self.messages.append({
                    "role": msg.role,
                    "content": msg.content,
                })

        # Add new user message
        self.messages.append({
            "role": "user",
            "content": user_message,
        })

    def _get_tool_schemas(self) -> list[dict]:
        """Get OpenAI-format tool schemas for enabled tools."""
        schemas = []
        for tool in self.context.tools:
            schemas.append(tool.get_openai_schema())
        return schemas

    async def _call_llm(self, tools: list[dict]) -> dict:
        """Call the LLM via RequestyAI."""
        import httpx

        url = f"{settings.REQUESTY_API_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.REQUESTY_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.context.copilot.model,
            "messages": self.messages,
            "temperature": self.context.copilot.temperature,
            "max_tokens": self.context.copilot.max_tokens,
            "stream": False,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    async def _stream_llm(self, tools: list[dict]) -> AsyncIterator[dict]:
        """Stream LLM response via RequestyAI."""
        import httpx

        url = f"{settings.REQUESTY_API_URL}/chat/completions"
        headers = {
            "Authorization": f"Bearer {settings.REQUESTY_API_KEY}",
            "Content-Type": "application/json",
        }

        payload = {
            "model": self.context.copilot.model,
            "messages": self.messages,
            "temperature": self.context.copilot.temperature,
            "max_tokens": self.context.copilot.max_tokens,
            "stream": True,
        }

        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                response.raise_for_status()

                current_tool_calls = {}

                async for line in response.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue

                    data = line[6:]  # Remove "data: " prefix
                    if data == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data)
                        delta = chunk["choices"][0].get("delta", {})

                        # Handle content
                        if "content" in delta and delta["content"]:
                            yield {"type": "content", "content": delta["content"]}

                        # Handle tool calls
                        if "tool_calls" in delta:
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in current_tool_calls:
                                    current_tool_calls[idx] = {
                                        "id": tc.get("id", ""),
                                        "type": "function",
                                        "function": {"name": "", "arguments": ""},
                                    }

                                if "id" in tc:
                                    current_tool_calls[idx]["id"] = tc["id"]

                                func = tc.get("function", {})
                                if "name" in func:
                                    current_tool_calls[idx]["function"]["name"] = func["name"]
                                if "arguments" in func:
                                    current_tool_calls[idx]["function"]["arguments"] += func["arguments"]

                    except json.JSONDecodeError:
                        continue

                # Yield completed tool calls
                for tc in current_tool_calls.values():
                    if tc["id"] and tc["function"]["name"]:
                        yield {"type": "tool_call", "tool_call": tc}

    async def _execute_tool(self, tool_call: dict) -> ToolResult:
        """Execute a tool call and log the execution."""
        function = tool_call.get("function", {})
        tool_name = function.get("name", "")
        arguments_str = function.get("arguments", "{}")

        # Find tool
        tool = None
        for t in self.context.tools:
            if t.name == tool_name:
                tool = t
                break

        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool not found: {tool_name}",
            )

        # Parse arguments
        try:
            arguments = json.loads(arguments_str)
        except json.JSONDecodeError:
            return ToolResult(
                success=False,
                error=f"Invalid tool arguments: {arguments_str}",
            )

        # Execute tool
        start_time = time.time()
        result = await tool.execute(**arguments)
        execution_time = int((time.time() - start_time) * 1000)
        result.execution_time_ms = execution_time

        # Log execution (if we have a tool ID in the database)
        # This is optional - only if the tool is registered in the copilot

        return result
