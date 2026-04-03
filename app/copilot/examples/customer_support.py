"""
Customer Support Copilot
An AI agent for handling customer support inquiries
"""
import uuid
from typing import Optional

from sqlmodel import Session

from app.copilot.models import Copilot, CopilotTool


CUSTOMER_SUPPORT_SYSTEM_PROMPT = """You are a friendly and professional Customer Support Agent for Qorebit.

Your primary responsibilities:
1. Answer customer questions about products and services
2. Help resolve common issues
3. Guide customers through troubleshooting steps
4. Escalate complex issues to human agents when needed
5. Collect feedback and improvement suggestions

Key behaviors:
- Be empathetic and patient with all customers
- Use clear, simple language
- Provide step-by-step instructions when helping
- Always verify you've resolved the customer's issue before closing
- If you can't help, provide clear escalation path

You have access to:
- RAG Search: To look up product documentation and FAQs
- Web Search: For checking current service status or announcements
- Email: To send follow-up information or escalation requests

Common topics you can help with:
- Account management (billing, subscription, settings)
- Technical troubleshooting
- Feature explanations
- Pricing and plans
- Integration help

When you don't know an answer:
1. Search the knowledge base
2. If still unclear, offer to escalate to a specialist
3. Never make up information"""

CUSTOMER_SUPPORT_WELCOME = """👋 Hi there! I'm your Customer Support Assistant.

I'm here to help you with:
• Account and billing questions
• Technical issues and troubleshooting
• Product features and how-tos
• General inquiries

What can I help you with today?"""

CUSTOMER_SUPPORT_PROMPTS = [
    "How do I reset my password?",
    "I'm having trouble with my billing",
    "How do I upgrade my plan?",
    "Can you explain how this feature works?",
    "I need help with API integration",
]


def create_customer_support_copilot(
    session: Session,
    user_id: uuid.UUID,
    workspace_id: Optional[uuid.UUID] = None,
) -> Copilot:
    """
    Create a Customer Support Copilot for a user/workspace.

    Args:
        session: Database session
        user_id: ID of the user creating the copilot
        workspace_id: Optional workspace ID

    Returns:
        Created Copilot instance
    """
    copilot = Copilot(
        name="Customer Support Agent",
        description="AI assistant that helps customers with questions, troubleshooting, and account management.",
        category="customer-support",
        visibility="workspace" if workspace_id else "private",
        status="active",
        model="openai/gpt-4o",
        system_prompt=CUSTOMER_SUPPORT_SYSTEM_PROMPT,
        welcome_message=CUSTOMER_SUPPORT_WELCOME,
        suggested_prompts=CUSTOMER_SUPPORT_PROMPTS,
        capabilities=["memory", "web-search", "function-calling"],
        temperature=0.5,
        max_tokens=2048,
        tags=["support", "customer-service", "help-desk"],
        created_by=user_id,
        workspace_id=workspace_id,
        allow_file_uploads=True,
        allow_web_search=True,
        allow_code_execution=False,
        memory_enabled=True,
        memory_window_size=30,
        tools_config={
            "email_enabled": True,
            "email_from": "support@qorebit.com",
            "email_from_name": "Qorebit Support",
        },
    )
    session.add(copilot)
    session.commit()
    session.refresh(copilot)

    # Add RAG Search tool for documentation
    rag_tool = CopilotTool(
        copilot_id=copilot.id,
        name="search_documentation",
        description="Search product documentation, FAQs, and help articles",
        tool_type="rag_search",
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The question or topic to search for",
                },
            },
            "required": ["query"],
        },
        config={},
        is_enabled=True,
        requires_confirmation=False,
    )
    session.add(rag_tool)

    # Add Web Search for status checks
    web_tool = CopilotTool(
        copilot_id=copilot.id,
        name="check_service_status",
        description="Check current service status or search for announcements",
        tool_type="web_search",
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query for status or announcements",
                },
            },
            "required": ["query"],
        },
        config={},
        is_enabled=True,
        requires_confirmation=False,
    )
    session.add(web_tool)

    # Add Email tool for follow-ups
    email_tool = CopilotTool(
        copilot_id=copilot.id,
        name="send_followup",
        description="Send follow-up email with additional information or escalation",
        tool_type="email_send",
        parameters_schema={
            "type": "object",
            "properties": {
                "to": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Recipient email addresses",
                },
                "subject": {
                    "type": "string",
                    "description": "Email subject",
                },
                "body": {
                    "type": "string",
                    "description": "Email body text",
                },
            },
            "required": ["to", "subject", "body"],
        },
        config={},
        is_enabled=True,
        requires_confirmation=True,
    )
    session.add(email_tool)

    session.commit()

    return copilot
