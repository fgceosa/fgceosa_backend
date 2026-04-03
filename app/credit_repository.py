"""
AI Credits CRUD Operations

Handles credit checking, deduction, and usage logging for AI API requests.
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Any

from sqlmodel import Session, select
from fastapi import HTTPException, status

from app.models import (
    CreditTransaction, 
    APIRequest, 
    Project, 
    User, 
    WorkspaceCreditTransaction,
    OrganizationCreditTransaction,
    WorkspaceMember,
    Workspace,
    WalletOwnerType,
    WalletTransactionType
)
from app.services.wallet_service import WalletService


def get_user_credit_balance(
    *, 
    session: Session, 
    user_id: uuid.UUID,
    organization_id: Optional[uuid.UUID] = None
) -> Decimal:
    """
    Get current credit balance from wallet ledger.
    If organization_id is provided, checks organization wallet balance.
    Otherwise checks user wallet balance.
    """
    if organization_id:
        wallet = WalletService.get_or_create_wallet(session, organization_id, WalletOwnerType.ORGANIZATION)
    else:
        wallet = WalletService.get_or_create_wallet(session, user_id, WalletOwnerType.USER)
        
    return WalletService.get_balance(session, wallet.id)


def check_sufficient_credits(
    *,
    session: Session,
    user_id: uuid.UUID,
    organization_id: Optional[uuid.UUID] = None,
    estimated_cost: Decimal = Decimal("0.01")
) -> Decimal:
    """
    Check if user/org has sufficient credits for an AI request

    Args:
        session: Database session
        user_id: User UUID
        organization_id: Optional Organization UUID. If provided, checks org wallet.
        estimated_cost: Estimated cost of the request (default: $0.01)

    Returns:
        Current balance

    Raises:
        HTTPException: If insufficient credits
    """
    balance = get_user_credit_balance(
        session=session, 
        user_id=user_id, 
        organization_id=organization_id
    )

    if balance < estimated_cost:
        owner_type = "Organization" if organization_id else "User"
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "message": f"Insufficient {owner_type} credits. Your current balance is ${balance:.2f}.",
                "current_balance": float(balance),
                "required": float(estimated_cost),
                "owner_type": owner_type.lower()
            }
        )

    return balance


def deduct_credits(
    *,
    session: Session,
    user_id: uuid.UUID,
    amount: Decimal,
    description: str,
    organization_id: Optional[uuid.UUID] = None,
    workspace_id: Optional[uuid.UUID] = None,
    reference_id: Optional[str] = None,
    transaction_type: str = "usage",
) -> Any:
    """
    Deduct credits from account using WalletService.
    If organization_id is provided, deducts from organization wallet.
    Otherwise deducts from user wallet.
    """
    if organization_id:
        owner_id = organization_id
        owner_type = WalletOwnerType.ORGANIZATION
    else:
        owner_id = user_id
        owner_type = WalletOwnerType.USER

    tx = WalletService.deduct_usage(
        session=session,
        owner_id=owner_id,
        owner_type=owner_type,
        amount=amount,
        description=description,
        reference_id=reference_id
    )

    # If organization usage, also log to OrganizationCreditTransaction for usage summary
    if organization_id:
        from app.services.organization_credit_service import OrganizationCreditService
        OrganizationCreditService.log_transaction(
            session=session,
            org_id=organization_id,
            amount=-amount,
            transaction_type="usage",
            description=description,
            workspace_id=workspace_id,
            performed_by=user_id,
            commit=True
        )

    return tx


def log_api_request(
    *,
    session: Session,
    user_id: uuid.UUID,
    project_id: Optional[uuid.UUID],
    model: str,
    endpoint: str,
    request_tokens: int,
    response_tokens: int,
    cost: Decimal,
    status: str = "success",
    response_time_ms: Optional[int] = None,
    organization_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
    origin: Optional[str] = None
) -> APIRequest:
    """
    Log an API request to the database

    Args:
        session: Database session
        user_id: User UUID
        project_id: Optional project UUID (can be None for direct API usage)
        model: AI model used
        endpoint: API endpoint called
        request_tokens: Number of input tokens
        response_tokens: Number of output tokens
        cost: Cost of the request in USD
        status: Request status (success, error, timeout)
        response_time_ms: Response time in milliseconds

    Returns:
        Created APIRequest record
    """
    # If no project_id is provided, try to get or create a default project
    if not project_id:
        # Try to find a default project for this user (support old and new names)
        default_project_stmt = select(Project).where(
            Project.owner_user_id == user_id,
            Project.is_deleted == False,
            Project.name.in_([
                "AI Engine (Direct API)", 
                "AI Direct Access"
            ])
        ).limit(1)
        default_project = session.exec(default_project_stmt).first()

        # Create default project if it doesn't exist
        if not default_project:
            default_project = Project(
                name="AI Direct Access",
                description="Direct API usage",
                owner_user_id=user_id,
                is_active=True,
            )
            session.add(default_project)
            session.commit()
            session.refresh(default_project)

        project_id = default_project.id

    # Create API request log
    api_request = APIRequest(
        project_id=project_id,
        user_id=user_id,
        model=model,
        endpoint=endpoint,
        request_tokens=request_tokens,
        response_tokens=response_tokens,
        total_tokens=request_tokens + response_tokens,
        cost=cost,
        status=status,
        response_time_ms=response_time_ms,
        organization_id=organization_id,
        ip_address=ip_address,
        origin=origin,
    )

    session.add(api_request)
    session.commit()
    session.refresh(api_request)

    return api_request


def process_ai_request_usage(
    *,
    session: Session,
    user_id: uuid.UUID,
    project_id: Optional[uuid.UUID],
    model: str,
    endpoint: str,
    prompt_tokens: int,
    completion_tokens: int,
    cost: Decimal,
    response_time_ms: Optional[int] = None,
    organization_id: Optional[uuid.UUID] = None,
    workspace_id: Optional[uuid.UUID] = None,
    ip_address: Optional[str] = None,
    origin: Optional[str] = None
) -> tuple[CreditTransaction, APIRequest]:
    """
    Process AI request usage: deduct credits and log request

    This is a convenience function that combines credit deduction and usage logging
    in a single transaction.

    Args:
        session: Database session
        user_id: User UUID
        project_id: Optional project UUID
        model: AI model used
        endpoint: API endpoint called
        prompt_tokens: Number of input tokens
        completion_tokens: Number of output tokens
        cost: Cost in USD
        response_time_ms: Response time in milliseconds

    Returns:
        Tuple of (CreditTransaction, APIRequest)

    Raises:
        HTTPException: If insufficient credits
    """
    # Deduct credits
    transaction = deduct_credits(
        session=session,
        user_id=user_id,
        amount=cost,
        description=f"AI API usage: {model} ({prompt_tokens + completion_tokens} tokens)",
        organization_id=organization_id,  # Deduct from Org wallet if present
        workspace_id=workspace_id,
        reference_id=None,  # Will be updated with API request ID
    )

    # Log API request
    api_request = log_api_request(
        session=session,
        user_id=user_id,
        project_id=project_id,
        model=model,
        endpoint=endpoint,
        request_tokens=prompt_tokens,
        response_tokens=completion_tokens,
        cost=cost,
        status="success",
        response_time_ms=response_time_ms,
        organization_id=organization_id,
        ip_address=ip_address,
        origin=origin,
    )

    # Update transaction reference_id with API request ID
    transaction.reference_id = str(api_request.id)
    session.add(transaction)
    session.commit()

    # Log to organization/workspace if context provided
    if workspace_id and organization_id:
        try:
            from app.services.organization_credit_service import OrganizationCreditService
            OrganizationCreditService.track_workspace_usage(
                session=session,
                workspace_id=workspace_id,
                org_id=organization_id,
                amount=cost,
                metadata={
                    "model": model,
                    "tokens": prompt_tokens + completion_tokens,
                    "type": "copilot_usage"
                }
            )
        except Exception as e:
            # Don't fail the whole request if tracking fails
            import logging
            logging.error(f"Failed to track workspace usage: {e}")

    # Create granular WorkspaceCreditTransaction for dashboard "Usage Today" stats
    if workspace_id:
        try:
            # 1. Get Workspace Member ID
            member_stmt = select(WorkspaceMember).where(
                WorkspaceMember.workspace_id == workspace_id,
                WorkspaceMember.user_id == user_id
            )
            member = session.exec(member_stmt).first()
            recipient_id = member.id if member else None

            # 2. Get current workspace balance (for the record, not deducting since User paid)
            # Optimization: If we heavily use this, we might want to fetch just the balance field
            workspace = session.get(Workspace, workspace_id)
            current_ws_balance = workspace.credits_balance if workspace else Decimal("0.00")

            # 3. Create Transaction
            ws_transaction = WorkspaceCreditTransaction(
                workspace_id=workspace_id,
                type="usage",
                amount=cost,
                tokens=prompt_tokens + completion_tokens,
                balance=current_ws_balance, 
                description=f"AI Usage: {model}",
                recipient_id=recipient_id,
                status="completed"
            )
            session.add(ws_transaction)
            session.commit()
        except Exception as e:
            import logging
            logging.error(f"Failed to create workspace credit transaction: {e}")

    return transaction, api_request


def add_credits(
    *,
    session: Session,
    user_id: uuid.UUID,
    amount: Decimal,
    transaction_type: str = "purchase",
    description: str,
    reference_id: Optional[str] = None
) -> Any:
    """
    Add credits to user account using WalletService.
    """
    wallet = WalletService.get_or_create_wallet(session, user_id, WalletOwnerType.USER)
    
    # Map old types to new types
    tx_type = WalletTransactionType.TOP_UP if transaction_type == "purchase" else WalletTransactionType.ADJUSTMENT
    
    tx = WalletService.add_transaction(
        session=session,
        wallet_id=wallet.id,
        transaction_type=tx_type,
        amount=amount,
        credit=amount,
        description=description,
        reference_id=reference_id,
        source="manual_topup"
    )
    return tx
