"""
Base Tool Interface for Copilot Agents
Defines the contract all tools must implement
"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional, Type

from pydantic import BaseModel


@dataclass
class ToolResult:
    """Result returned by tool execution"""
    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: int = 0
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "metadata": self.metadata,
        }


class BaseTool(ABC):
    """
    Abstract base class for all copilot tools.

    Each tool must define:
    - name: Unique identifier
    - description: What the tool does (used in prompts)
    - parameters_schema: OpenAI-style JSON Schema for parameters
    - execute(): The actual tool implementation
    """

    name: str
    description: str
    parameters_schema: dict

    def __init__(self, config: dict | None = None):
        """
        Initialize tool with optional configuration.

        Args:
            config: Tool-specific configuration dict
        """
        self.config = config or {}

    @abstractmethod
    async def execute(self, **params) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            **params: Tool parameters matching the schema

        Returns:
            ToolResult with success/failure and data
        """
        pass

    def get_openai_schema(self) -> dict:
        """
        Get the tool schema in OpenAI function calling format.
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters_schema,
            }
        }

    def validate_params(self, params: dict) -> tuple[bool, str | None]:
        """
        Validate parameters against the schema.
        Returns (is_valid, error_message).
        """
        # Basic validation - check required fields
        required = self.parameters_schema.get("required", [])
        properties = self.parameters_schema.get("properties", {})

        for req_field in required:
            if req_field not in params:
                return False, f"Missing required parameter: {req_field}"

        # Type checking
        for param_name, param_value in params.items():
            if param_name in properties:
                expected_type = properties[param_name].get("type")
                if not self._check_type(param_value, expected_type):
                    return False, f"Invalid type for {param_name}: expected {expected_type}"

        return True, None

    def _check_type(self, value: Any, expected_type: str) -> bool:
        """Check if value matches expected JSON Schema type."""
        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        expected_python_type = type_map.get(expected_type)
        if expected_python_type is None:
            return True  # Unknown type, allow
        return isinstance(value, expected_python_type)


class ToolRegistry:
    """
    Registry for managing available tools.
    Allows dynamic tool registration and retrieval.
    """

    _instance: Optional["ToolRegistry"] = None
    _tools: dict[str, Type[BaseTool]]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._tools = {}
        return cls._instance

    def register(self, tool_class: Type[BaseTool]) -> None:
        """Register a tool class."""
        # Create temporary instance to get name
        temp_instance = tool_class()
        self._tools[temp_instance.name] = tool_class

    def get(self, name: str) -> Type[BaseTool] | None:
        """Get a tool class by name."""
        return self._tools.get(name)

    def get_instance(self, name: str, config: dict | None = None) -> BaseTool | None:
        """Get a tool instance by name."""
        tool_class = self._tools.get(name)
        if tool_class:
            return tool_class(config)
        return None

    def list_tools(self) -> list[str]:
        """List all registered tool names."""
        return list(self._tools.keys())

    def get_all_schemas(self) -> list[dict]:
        """Get OpenAI schemas for all registered tools."""
        schemas = []
        for tool_class in self._tools.values():
            instance = tool_class()
            schemas.append(instance.get_openai_schema())
        return schemas


# Global registry instance
tool_registry = ToolRegistry()


def register_tool(tool_class: Type[BaseTool]) -> Type[BaseTool]:
    """Decorator to register a tool class."""
    tool_registry.register(tool_class)
    return tool_class
