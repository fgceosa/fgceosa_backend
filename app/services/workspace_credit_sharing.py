"""
Workspace AI Credit Sharing Service

Handles credit transfers from workspace wallet to team members.
Supports single and bulk transfers with email or tag identification.
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone
from typing import List, Dict, Any
from sqlmodel import Session, select
from fastapi import HTTPException, status

from app.models import (
    User,
    Workspace,
    WorkspaceMember,
    WorkspaceCreditTransaction,
    OrganizationCreditTransaction,
)
from app.services.workspace_service import check_workspace_access
from app.services.email_service import email_service
from app.notification_repository import create_notification


# Pydantic Models for Request/Response
from pydantic import BaseModel, EmailStr, Field


class RecipientInput(BaseModel):
    """Input for a single recipient"""
    email: EmailStr | None = None
    tag_number: str | None = None
    user_id: uuid.UUID | None = None
    amount: Decimal | None = Field(None, description="Amount for this recipient (if per-user mode)")

    def __str__(self):
        return str(self.user_id) if self.user_id else (self.email or self.tag_number or "Unknown")


class CreditShareRequest(BaseModel):
    """Request to share credits"""
    recipients: List[RecipientInput] = Field(..., min_length=1, description="List of recipients")
    amount_per_user: Decimal | None = Field(None, gt=0, description="Amount per user (equal split mode)")
    total_amount: Decimal | None = Field(None, gt=0, description="Total amount to split equally")
    message: str | None = Field(None, max_length=500, description="Optional message")
    draw_from_organization: bool = Field(False, description="Draw credits from organization treasury if workspace balance is insufficient")

    class Config:
        json_schema_extra = {
            "example": {
                "recipients": [
                    {"email": "user1@example.com", "amount": 10.0},
                    {"tag_number": "@qor123456", "amount": 15.0}
                ],
                "message": "Monthly credit allocation"
            }
        }


class CreditShareResult(BaseModel):
    """Result for a single recipient transfer"""
    recipient_identifier: str
    recipient_id: uuid.UUID | None = None
    recipient_name: str | None = None
    amount: Decimal
    status: str  # "success" or "failed"
    error: str | None = None


class CreditShareResponse(BaseModel):
    """Response from credit sharing operation"""
    success_count: int
    failed_count: int
    total_amount: Decimal
    results: List[CreditShareResult]
    workspace_balance_before: Decimal
    workspace_balance_after: Decimal


async def resolve_recipient(
    session: Session,
    email: str | None,
    tag_number: str | None,
    user_id: uuid.UUID | None = None,
) -> User:
    """
    Resolve a recipient by email or tag number.

    Args:
        session: Database session
        email: User email address
        tag_number: User tag number

    Returns:
        User object

    Raises:
        HTTPException: If user not found
    """
    if not email and not tag_number and not user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either email, tag_number, or user_id must be provided"
        )

    query = select(User)

    if user_id:
        user = session.get(User, user_id)
    elif email:
        query = select(User).where(User.email == email)
        user = session.exec(query).first()
    elif tag_number:
        # Normalize tag number (remove @ if present)
        normalized_tag = tag_number.lstrip('@')
        query = select(User).where(User.tag_number == normalized_tag)
        user = session.exec(query).first()

    if not user:
        identifier = email or tag_number
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User not found: {identifier}"
        )

    return user


async def share_credits_to_single_user(
    session: Session,
    workspace: Workspace,
    admin_user: User,
    recipient: User,
    amount: Decimal,
    message: str | None = None,
    use_org_treasury: bool = False
) -> WorkspaceCreditTransaction:
    """
    Transfer credits from workspace to a single user.

    Args:
        session: Database session
        workspace: Source workspace
        admin_user: Admin performing the transfer
        recipient: Recipient user
        amount: Amount to transfer
        message: Optional message
        use_org_treasury: If True, draw from organization treasury instead of workspace balance

    Returns:
        WorkspaceCreditTransaction record

    Raises:
        HTTPException: If insufficient balance
    """
    # Credits now always come from the Organization Treasury via WalletService.
    # The Workspace Wallet is not used for credit sharing to maintain centralized control.
    
    if not workspace.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace does not belong to an organization. Credit sharing requires an organization treasury."
        )
    
    from app.services.organization_credit_service import OrganizationCreditService
    
    # WalletService.share_credits handles Org-to-User wallet transfer
    # and OrganizationCreditService.share_credits ensures it's logged in history
    OrganizationCreditService.share_credits(
        session=session,
        org_id=workspace.organization_id,
        member_id=recipient.id,
        amount=amount,
        admin_id=admin_user.id,
        description=message or f"Credit allocation to {recipient.email} via {workspace.name}",
        workspace_id=workspace.id,
        commit=False
    )

    # Check if recipient is a workspace member
    member_statement = select(WorkspaceMember).where(
        WorkspaceMember.workspace_id == workspace.id,
        WorkspaceMember.user_id == recipient.id
    )
    member = session.exec(member_statement).first()

    # If member exists, also update their allocated credits
    if member:
        if member.credits_allocated is None:
            member.credits_allocated = Decimal("0.00")
        member.credits_allocated += amount

    # Create transaction record
    transaction = WorkspaceCreditTransaction(
        workspace_id=workspace.id,
        type="allocation",
        amount=amount,
        balance=workspace.credits_balance,
        description=message or f"Credit transfer to {recipient.email}",
        recipient_id=member.id if member else None,
        status="completed",
        created_at=datetime.now(timezone.utc),
    )

    session.add(workspace)
    session.add(recipient)
    if member:
        session.add(member)
    session.add(transaction)
    
    # Commit here to ensure recipient balance is updated before notification cache
    session.flush()

    # Send email notification
    try:
        email_service.send_credit_received_notification(
            email_to=str(recipient.email),
            username=recipient.full_name or str(recipient.email).split('@')[0],
            sender_name=admin_user.full_name or str(admin_user.email),
            amount=float(amount),
            message=message,
            credits_balance=float(recipient.credits) if recipient.credits else None
        )
    except Exception as e:
        # Don't fail the transaction if email fails
        print(f"Failed to send notification email: {e}")

    # Create in-app notification
    try:
        create_notification(
            session=session,
            user_id=recipient.id,
            title="Credits Received! 🎉",
            description=f"You received {amount} credits from {admin_user.full_name or admin_user.email} via {workspace.name}.",
            type="credit_received",
            metadata={
                "sender_id": str(admin_user.id),
                "amount": float(amount),
                "message": message,
                "workspace_id": str(workspace.id)
            },
            commit=False # Let the caller commit the whole batch
        )
    except Exception as e:
        print(f"Failed to create notification: {e}")

    return transaction


async def share_credits_bulk(
    session: Session,
    workspace_id: uuid.UUID,
    admin_user: User,
    request: CreditShareRequest,
) -> CreditShareResponse:
    """
    Share credits to multiple users atomically.

    Args:
        session: Database session
        workspace_id: Workspace ID
        admin_user: Admin performing the transfer
        request: Credit share request

    Returns:
        CreditShareResponse with results for each recipient

    Raises:
        HTTPException: On validation errors
    """
    # Fetch workspace
    workspace = session.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found"
        )

    # Check admin permission
    check_workspace_access(session=session, workspace=workspace, user=admin_user, require_owner=False)

    # If workspace belongs to an organization, we will enforce organization membership check
    organization_id = workspace.organization_id
    org_member_ids = set()
    if organization_id:
        from app.models import OrganizationMember
        org_members = session.exec(
            select(OrganizationMember.user_id).where(OrganizationMember.organization_id == organization_id)
        ).all()
        # Be safe with scalar conversion
        org_member_ids = {u if not hasattr(u, "_tuple_at") else u[0] for u in org_members}
        print(f"DEBUG: OrgID={organization_id}, MemberCount={len(org_member_ids)}")

    # Calculate amounts
    results: List[CreditShareResult] = []
    total_amount = Decimal("0.00")

    # Determine amount per user
    if request.total_amount:
        # Equal split mode - round to 2 decimal places
        amount_per_user = (request.total_amount / len(request.recipients)).quantize(Decimal("0.01"))
    elif request.amount_per_user:
        # Fixed amount per user
        amount_per_user = request.amount_per_user
    else:
        # Per-recipient amounts (must be specified in each recipient)
        amount_per_user = None

    # Resolve all recipients first (fail fast)
    recipients_data: List[tuple[RecipientInput, User, Decimal]] = []

    for recipient_input in request.recipients:
        try:
            user = await resolve_recipient(
                session,
                recipient_input.email,
                recipient_input.tag_number,
                recipient_input.user_id
            )

            # Enforce organization membership if applicable
            if organization_id and user.id not in org_member_ids:
                print(f"DEBUG: User {user.id} not in org_member_ids {org_member_ids}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"User {user.email} (ID: {user.id}) is not a member of this organization"
                )

            # Determine amount for this recipient
            if recipient_input.amount is not None:
                recipient_amount = recipient_input.amount
            elif amount_per_user is not None:
                recipient_amount = amount_per_user
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Amount not specified for {recipient_input}"
                )

            recipients_data.append((recipient_input, user, recipient_amount))
            total_amount += recipient_amount

        except HTTPException as e:
            # Record failure but continue
            results.append(CreditShareResult(
                recipient_identifier=str(recipient_input),
                amount=recipient_input.amount or Decimal("0.00"),
                status="failed",
                error=str(e.detail)
            ))

    # Round total amount to match DB precision
    total_amount = total_amount.quantize(Decimal("0.01"))

    workspace_balance_before = workspace.credits_balance
    
    # Validate organization treasury balance
    if not workspace.organization_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Workspace must belong to an organization to share credits."
        )

    # Check organization balance
    from app.services.organization_credit_service import OrganizationCreditService
    org_credits = OrganizationCreditService.get_balance(session, workspace.organization_id)
    if org_credits.balance < total_amount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient credits in organization treasury. Balance: {org_credits.balance}, Required: {total_amount}"
        )
    
    use_org_treasury = True # Always True now

    # Perform transfers (atomic)
    success_count = 0
    failed_count = 0

    try:
        for recipient_input, user, amount in recipients_data:
            try:
                transaction = await share_credits_to_single_user(
                    session=session,
                    workspace=workspace,
                    admin_user=admin_user,
                    recipient=user,
                    amount=amount,
                    message=request.message,
                    use_org_treasury=use_org_treasury
                )

                results.append(CreditShareResult(
                    recipient_identifier=recipient_input.email or recipient_input.tag_number or "Unknown",
                    recipient_id=user.id,
                    recipient_name=user.full_name or f"{user.first_name} {user.last_name}".strip() or user.email,
                    amount=amount,
                    status="success"
                ))
                success_count += 1

            except Exception as e:
                results.append(CreditShareResult(
                    recipient_identifier=recipient_input.email or recipient_input.tag_number or "Unknown",
                    amount=amount,
                    status="failed",
                    error=str(e)
                ))
                failed_count += 1
                # Rollback this individual transfer
                session.rollback()

        # Commit all successful transfers
        session.commit()

    except Exception as e:
        session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process credit transfers: {str(e)}"
        )

    # Refresh workspace to get updated balance
    session.refresh(workspace)

    return CreditShareResponse(
        success_count=success_count,
        failed_count=failed_count,
        total_amount=total_amount,
        results=results,
        workspace_balance_before=workspace_balance_before,
        workspace_balance_after=workspace.credits_balance
    )
