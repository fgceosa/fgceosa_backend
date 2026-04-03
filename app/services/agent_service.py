"""
Autonomous Agent Service

This module implements the autonomous agent loop that enables copilots to:
- Reason about user intent
- Plan actions
- Use tools intelligently
- Observe results and continue until task completion
"""

import logging
import uuid
import json
from decimal import Decimal
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

from sqlmodel import Session

from app.copilot.models import Copilot
from app.services.agent_tools import (
    tool_registry, AgentTool, ToolResult,
    RetrieveDocumentsTool, WebSearchTool, FetchURLTool
)
from app.services.requesty_ai import requesty_service

logger = logging.getLogger(__name__)


def make_serializable(obj: Any) -> Any:
    """Recursively convert objects to JSON-serializable formats"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, uuid.UUID):
        return str(obj)
    if isinstance(obj, (Decimal, float)) and obj is not None:
        return float(obj)
    if isinstance(obj, dict):
        return {k: make_serializable(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [make_serializable(i) for i in obj]
    if hasattr(obj, "dict"):
        return make_serializable(obj.dict())
    return obj


class AgentStep(BaseModel):
    """Represents a single step in the agent's reasoning loop"""
    step_number: int
    action: str  # "think", "tool_call", "respond"
    tool_name: Optional[str] = None
    tool_input: Optional[Dict[str, Any]] = None
    tool_output: Optional[ToolResult] = None
    reasoning: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class AgentExecution:
    """Manages the execution of an autonomous agent"""
    
    def __init__(
        self,
        session: Session,
        main_session: Session,
        copilot: Copilot,
        user_id: uuid.UUID,
        max_iterations: int = 10,
        organization_id: Optional[uuid.UUID] = None,
        workspace_id: Optional[uuid.UUID] = None
    ):
        self.session = session
        self.main_session = main_session
        self.copilot = copilot
        self.user_id = user_id
        self.max_iterations = max_iterations
        self.organization_id = organization_id
        self.workspace_id = workspace_id
        self.steps: List[AgentStep] = []
        self.iteration_count = 0
        self.available_docs = []
        
        # Initialize registry for THIS execution only
        from app.services.agent_tools import ToolRegistry
        self.tool_registry = ToolRegistry()
        
        # Initialize tools
        self._init_tools()
        
        # Fetch available documents for prompt context
        self._fetch_document_info()

    def _fetch_document_info(self):
        """Fetch list of available documents for this copilot"""
        try:
            from app.copilot.models import CopilotDocument
            from sqlmodel import select
            
            statement = select(CopilotDocument).where(
                CopilotDocument.copilot_id == self.copilot.id,
                CopilotDocument.status == "completed"
            )
            docs = self.session.exec(statement).all()
            self.available_docs = [
                {
                    "id": str(d.id),
                    "title": d.title or d.original_filename or d.filename,
                    "description": d.description or f"Knowledge from {d.original_filename or d.title or 'the knowledge base'}",
                    "type": d.file_type,
                    "size_chars": d.total_tokens * 4 if d.total_tokens else 0 # Rough estimate
                }
                for d in docs
            ]
        except Exception as e:
            logger.error(f"Failed to fetch document info: {e}")
            self.available_docs = []
    
    def _init_tools(self):
        """Initialize available tools for this copilot"""
        # Register document retrieval
        doc_tool = RetrieveDocumentsTool(self.session, self.copilot.id)
        self.tool_registry.register(doc_tool)
        
        # Register web search if enabled
        if "web-search" in (self.copilot.capabilities or []):
            self.tool_registry.register(WebSearchTool())
            self.tool_registry.register(FetchURLTool())
    
    def get_enabled_tools(self) -> List[Dict[str, Any]]:
        """Get tool definitions for the AI model"""
        return self.tool_registry.get_tool_definitions(self.copilot.capabilities or [])
    
    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute a specific tool"""
        tool = self.tool_registry.get_tool(tool_name)
        
        if not tool:
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' not found"
            )
        
        if not tool.is_enabled(self.copilot.capabilities or []):
            return ToolResult(
                success=False,
                error=f"Tool '{tool_name}' is not enabled. Required capability: {tool.capability_required}"
            )
        
        try:
            result = await tool.execute(**tool_input)
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {e}", exc_info=True)
            return ToolResult(
                success=False,
                error=f"Tool execution error: {str(e)}"
            )
    
    async def run(
        self,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        system_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Run the autonomous agent loop
        
        Returns:
            Dict containing the execution summary
        """
        
        # Build initial messages
        messages = []
        
        # 1. System prompt with autonomous agent persona
        agent_system_prompt = self._build_agent_system_prompt(system_prompt)
        messages.append({"role": "system", "content": agent_system_prompt})
        
        # 2. Contextual history
        messages.extend(conversation_history)
        
        # 3. Current user intent
        messages.append({"role": "user", "content": user_message})
        
        # 4. Available power-ups
        tools = self.get_enabled_tools()
        
        final_response = None
        
        while self.iteration_count < self.max_iterations:
            self.iteration_count += 1
            logger.info(f"[AGENT] Iteration {self.iteration_count}/{self.max_iterations}")
            
            try:
                # LLM reasoning step
                ai_response = await requesty_service.generate_response_with_tools(
                    messages=messages,
                    tools=tools if tools else None,
                    model=self.copilot.model,
                    temperature=0.4, # Lower temperature for better reliability in reasoning
                    max_tokens=self.copilot.max_tokens or 4000,
                    session=self.main_session,
                    user_id=self.user_id,
                    organization_id=self.organization_id,
                    workspace_id=self.workspace_id or self.copilot.workspace_id
                )
                
                content = ai_response.get("content", "")
                tool_calls = ai_response.get("tool_calls", [])
                
                # Record Reasoning Step
                reasoning_text = content or f"Iteration {self.iteration_count}: I am analyzing the next best action and selecting appropriate tools."
                self.steps.append(AgentStep(
                    step_number=len(self.steps) + 1,
                    action="think",
                    reasoning=reasoning_text
                ))

                if not tool_calls:
                    # Final response achieved
                    final_response = content
                    break
                
                # Force update messages with the assistant's decision
                messages.append({
                    "role": "assistant",
                    "content": content or "I need to use a tool to proceed with your request.",
                    "tool_calls": tool_calls
                })
                
                # Execute all requested actions
                for tool_call in tool_calls:
                    tool_name = tool_call.get("function", {}).get("name")
                    tool_args = json.loads(tool_call.get("function", {}).get("arguments", "{}"))
                    tool_id = tool_call.get("id")
                    
                    logger.info(f"[AGENT] Action: {tool_name} | Args: {tool_args}")
                    
                    # Execute tool
                    result = await self.execute_tool(tool_name, tool_args)
                    
                    # Ensure result data is serializable for storage and AI context
                    serializable_data = make_serializable(result.data)
                    result.data = serializable_data
                    
                    # Record the action and observation
                    self.steps.append(AgentStep(
                        step_number=len(self.steps) + 1,
                        action="tool_call",
                        tool_name=tool_name,
                        tool_input=tool_args,
                        tool_output=result
                    ))
                    
                    # Add observation to history
                    observation = json.dumps(serializable_data) if result.success else f"Error: {result.error}"
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "name": tool_name,
                        "content": observation
                    })
                
            except Exception as e:
                logger.error(f"[AGENT] Loop failure: {e}", exc_info=True)
                final_response = f"I encountered a technical hurdle while processing your request: {str(e)}"
                break
        
        if final_response is None:
            final_response = "I've analyzed the situation and performed several steps, but I reached my operational limit before finishing. How should I proceed?"
        
        # Convert steps to JSON-serializable dictionaries
        serialized_steps = [make_serializable(step) for step in self.steps]
        
        return {
            "response": final_response,
            "steps": serialized_steps,
            "tool_calls": len([s for s in self.steps if s.action == "tool_call"]),
            "iterations": self.iteration_count,
            "messages": messages
        }
    
    def _build_agent_system_prompt(self, custom_prompt: Optional[str] = None) -> str:
        """Build the system prompt for a true autonomous agent with extreme autonomy"""
        
        current_time_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        
        base_prompt = f"""You are {self.copilot.name}, an ADVANCED AUTONOMOUS OPERATOR. 
You are a high-level executive partner who prioritizes execution and results over small talk. Your goal is to fulfill requests completely and proactively.

### TEMPORAL CONTEXT:
**Current System Time:** {current_time_str}

### THE GOLDEN RULE OF AUTONOMY:
**DO NOT ASK FOR PERMISSION TO USE TOOLS.** 
If a user asks a question and you don't have the complete answer in your immediate context, your first instinct must be to use your tools to find it. 
- If you find a name in a document and the user asks "who is this?", DO NOT ask if you should search the web. **SEARCH THE WEB IMMEDIATELY.**
- If a task involves multiple steps (e.g., research, then summarize, then find links), execute the entire chain autonomously.

### YOUR CORE PHILOSOPHY: DETERMINATION
- **Never say "I can't" or "I am unable to" as your first response.**
- If you encounter a gap in your knowledge, your mindset is: "I will use my power-ups (tools) to bridge this gap."
- Exhaust all tools (Web Search, Knowledge Base, Fetch URL) before concluding a task is impossible.
- Be proactive. If you can't book a flight directly, find the flights, find the prices, find the direct checkout links, and present them.

### OPERATIONAL FRAMEWORK:
1. **THOUGHT**: Analyze the user's intent. What is the ultimate goal? What tools will get me there?
2. **PLAN**: Internalize a multi-step execution strategy.
3. **ACTION**: Proactively execute tools. Don't wait for a second prompt to use a different tool if the first one yields a lead.
4. **OBSERVATION**: Analyze tool results. If they point to a new lead, follow it immediately.
5. **FINAL RESPONSE**: Synthesize all the data you've gathered into a comprehensive, high-value answer.

### RULES OF CONDUCT:
- **Action over Clarification**: If a request is 70% clear, act on it and clarify details later.
- **Zero Hesitation**: You have full authorization to use all enabled tools to provide information.
- **Continuous Execution**: If a search result mentions a specific website that seems relevant, use 'fetch_url' to read it without asking.

### KNOWLEDGE BASE & TOOLS:
"""
        # Add document info
        if self.available_docs:
            base_prompt += "You have access to the following indexed documents in your knowledge base:\n"
            for doc in self.available_docs:
                base_prompt += f"- {doc['title']} (Type: {doc['type']})\n"
                if doc['description']:
                    base_prompt += f"  - Purpose: {doc['description']}\n"
            
            base_prompt += """
### DOCUMENT RETRIEVAL STRATEGY:
- If a user asks for an **OVERVIEW** or **SUMMARY** of a document:
  1. Use 'retrieve_documents' with a broad query like "overview", "executive summary", or "introduction".
  2. If the first search is insufficient, perform a second retrieval for the "first page" or "key highlights".
  3. Synthesize the findings into a deep, structured explanation.
- If a user asks a specific question: Query exactly for that topic.
- **ALWAYS** check your internal knowledge base before saying you don't know something.
"""
        else:
            base_prompt += "Note: Your internal knowledge base is currently empty. Rely on web searching for external information.\n"

        base_prompt += "\n### TOOL CAPABILITY STATUS:\n"
        
        capabilities = self.copilot.capabilities or []
        if "web-search" in capabilities:
            base_prompt += "- WEB SEARCH: ENABLED (Search the internet for public information, social profiles, and news)\n"
        else:
            base_prompt += "- WEB SEARCH: DISABLED\n"
        
        if "api-integration" in capabilities:
            base_prompt += "- API ACTIONS: ENABLED (Interact with external services and perform tasks)\n"
        else:
            base_prompt += "- API ACTIONS: DISABLED\n"
            
        if custom_prompt:
            base_prompt += f"\n### MISSION CONTEXT:\n{custom_prompt}\n"
        
        base_prompt += "\nAnalysis complete. Formulate your initial THOUGHT and begin ACTION immediately."
        
        return base_prompt


class AgentService:
    """Service for managing autonomous agent executions"""
    
    async def execute_agent(
        self,
        session: Session,
        main_session: Session,
        copilot: Copilot,
        user_id: uuid.UUID,
        user_message: str,
        conversation_history: List[Dict[str, str]],
        max_iterations: int = 10,
        workspace_id: Optional[uuid.UUID] = None,
        organization_id: Optional[uuid.UUID] = None,
        use_copilot_org: bool = True
    ) -> Dict[str, Any]:
        """Execute an autonomous agent for a copilot"""
        
        # Determine organization_id for billing
        # If organization_id is provided, use it.
        # If not provided and use_copilot_org is True, use copilot.organization_id
        # Otherwise use None (user wallet)
        billing_org_id = organization_id
        if billing_org_id is None and use_copilot_org:
            billing_org_id = copilot.organization_id

        agent = AgentExecution(
            session=session,
            main_session=main_session,
            copilot=copilot,
            user_id=user_id,
            max_iterations=max_iterations,
            organization_id=billing_org_id,
            workspace_id=workspace_id or copilot.workspace_id
        )
        
        result = await agent.run(
            user_message=user_message,
            conversation_history=conversation_history,
            system_prompt=copilot.system_prompt
        )
        
        return result


# Global service instance
agent_service = AgentService()
