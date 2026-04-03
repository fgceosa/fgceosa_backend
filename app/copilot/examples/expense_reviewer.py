"""
Expense Reviewer Copilot
An AI agent that reviews expense reports and helps with expense management
"""
import uuid
from typing import Optional

from sqlmodel import Session

from app.copilot.models import Copilot, CopilotTool


EXPENSE_REVIEWER_SYSTEM_PROMPT = """You are an expert Expense Review Assistant for corporate expense management.

Your primary responsibilities:
1. Review expense reports for policy compliance
2. Identify potential issues or discrepancies
3. Provide recommendations for expense categorization
4. Answer questions about expense policies
5. Help employees submit proper expense reports

Key behaviors:
- Be thorough but efficient in your reviews
- Cite specific policy sections when flagging issues
- Be helpful and professional in your communication
- When uncertain, recommend escalation to finance team
- Maintain confidentiality of all expense data

You have access to the following tools:
- RAG Search: To look up company expense policies and guidelines
- Database Query: To check historical expense patterns (read-only)
- Email Send: To send notifications or approval requests

When reviewing expenses, check for:
- Receipt validity and completeness
- Policy compliance (meal limits, travel policies, etc.)
- Proper categorization
- Duplicate submissions
- Missing information

Always provide clear explanations for any flags or rejections."""

EXPENSE_REVIEWER_WELCOME = """👋 Hello! I'm your Expense Review Assistant.

I can help you with:
• Reviewing expense reports for compliance
• Answering expense policy questions
• Categorizing expenses properly
• Identifying potential issues

How can I assist you today?"""

EXPENSE_REVIEWER_PROMPTS = [
    "Review this expense report for policy compliance",
    "What is the daily meal allowance for business travel?",
    "Is this expense within our corporate policy?",
    "Help me categorize this expense",
    "What documentation is needed for travel expenses?",
]


def create_expense_reviewer_copilot(
    session: Session,
    user_id: uuid.UUID,
    workspace_id: Optional[uuid.UUID] = None,
) -> Copilot:
    """
    Create an Expense Reviewer Copilot for a user/workspace.

    Args:
        session: Database session
        user_id: ID of the user creating the copilot
        workspace_id: Optional workspace ID

    Returns:
        Created Copilot instance
    """
    copilot = Copilot(
        name="Expense Reviewer",
        description="AI assistant that reviews expense reports for policy compliance and helps with expense management.",
        category="finance",
        visibility="workspace" if workspace_id else "private",
        status="active",
        model="openai/gpt-4o",
        system_prompt=EXPENSE_REVIEWER_SYSTEM_PROMPT,
        welcome_message=EXPENSE_REVIEWER_WELCOME,
        suggested_prompts=EXPENSE_REVIEWER_PROMPTS,
        capabilities=["memory", "function-calling", "file-upload"],
        temperature=0.3,  # Lower temperature for more consistent reviews
        max_tokens=4096,
        tags=["finance", "expense", "review", "compliance"],
        created_by=user_id,
        workspace_id=workspace_id,
        allow_file_uploads=True,
        allow_web_search=False,
        allow_code_execution=False,
        memory_enabled=True,
        memory_window_size=20,
        tools_config={
            "email_enabled": True,
            "email_from": "expenses@company.com",
            "email_from_name": "Expense Review Bot",
        },
    )
    session.add(copilot)
    session.commit()
    session.refresh(copilot)

    # Add RAG Search tool for policy lookup
    rag_tool = CopilotTool(
        copilot_id=copilot.id,
        name="search_policies",
        description="Search company expense policies and guidelines",
        tool_type="rag_search",
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The policy question or topic to search for",
                },
            },
            "required": ["query"],
        },
        config={},
        is_enabled=True,
        requires_confirmation=False,
    )
    session.add(rag_tool)

    # Add Database Query tool for expense history
    db_tool = CopilotTool(
        copilot_id=copilot.id,
        name="check_expense_history",
        description="Check historical expense patterns and past submissions",
        tool_type="database_query",
        parameters_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "SQL SELECT query to run (read-only)",
                },
            },
            "required": ["query"],
        },
        config={
            "read_only": True,
            "max_rows": 50,
            "allowed_tables": ["expenses", "expense_reports", "expense_categories"],
        },
        is_enabled=True,
        requires_confirmation=True,  # Require confirmation for DB queries
    )
    session.add(db_tool)

    # Add Email tool for notifications
    email_tool = CopilotTool(
        copilot_id=copilot.id,
        name="send_notification",
        description="Send expense notification or approval request emails",
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
        requires_confirmation=True,  # Always confirm before sending emails
    )
    session.add(email_tool)

    session.commit()

    return copilot


# Example policy document content for RAG
SAMPLE_EXPENSE_POLICY = """
# Corporate Expense Policy

## 1. General Guidelines

All employees must submit expense reports within 30 days of incurring the expense.
Original receipts are required for all expenses over $25.

## 2. Travel Expenses

### 2.1 Airfare
- Economy class for flights under 6 hours
- Business class allowed for flights over 6 hours with manager approval
- Book at least 14 days in advance when possible

### 2.2 Hotels
- Maximum daily rate: $200 in standard markets, $350 in high-cost cities
- High-cost cities include: New York, San Francisco, London, Tokyo

### 2.3 Meals
- Breakfast: up to $20
- Lunch: up to $30
- Dinner: up to $60
- Daily total should not exceed $100

## 3. Office Expenses

### 3.1 Equipment
- Office supplies under $100 do not require approval
- Equipment over $100 requires manager approval
- Technology purchases over $500 require IT and manager approval

### 3.2 Software
- All software purchases must be approved by IT department
- Monthly subscriptions over $50/month require VP approval

## 4. Client Entertainment

- Client meals: up to $150 per person
- Client events: require pre-approval from VP
- Document business purpose and attendees

## 5. Submission Process

1. Collect all receipts
2. Complete expense report form
3. Attach digital copies of receipts
4. Submit within 30 days
5. Await manager approval
6. Reimbursement within 14 business days of approval
"""
