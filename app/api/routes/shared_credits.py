"""
Shared Credits API Routes

This module handles credit sharing functionality including:
- Viewing shared credits statistics
- Transferring credits to team members
- Viewing transaction history
"""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import Session, select, func, and_, or_

from app.api import deps
from app.models import (
    User,
    CreditTransfer,
    CreditTransferCreate,
    CreditTransferPublic,
    CreditTransferList,
    SharedCreditsStats,
    TransactionStatus,
    Message,
    UserPublic,
)
from app.core.config import settings
from app.credit_repository import add_credits, deduct_credits, get_user_credit_balance
from app.services.email_service import email_service
from app.notification_repository import create_notification


router = APIRouter(prefix="/shared-credits", tags=["shared-credits"])


@router.get("/stats")
def get_shared_credits_stats(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Get shared credits statistics for the current user.

    Returns:
        - availableCredits: Current user's available credits
        - teamMembers: Total number of users (excluding current user)
        - creditsShared: Total credits sent by current user
        - totalTransfers: Total number of transactions by current user
    """
    # Get available credits from transaction history
    available_credits = get_user_credit_balance(session=session, user_id=current_user.id)
    
    # Debug: Print credit balance info
    print(f"DEBUG shared_credits/stats: user_id={current_user.id}")
    print(f"DEBUG shared_credits/stats: user.credits={current_user.credits}")
    print(f"DEBUG shared_credits/stats: get_user_credit_balance returned={available_credits}")

    # Get total unique recipients current user has shared with
    total_recipients = session.exec(
        select(func.count(func.distinct(CreditTransfer.recipient_id))).where(
            CreditTransfer.sender_id == current_user.id
        )
    ).one()

    # Get total credits shared (sent by current user, completed only)
    credits_shared_result = session.exec(
        select(func.sum(CreditTransfer.amount)).where(
            and_(
                CreditTransfer.sender_id == current_user.id,
                CreditTransfer.status == TransactionStatus.COMPLETED,
            )
        )
    ).one()
    credits_shared = credits_shared_result or 0

    # Get total transfers count (sent by current user)
    total_transfers = session.exec(
        select(func.count(CreditTransfer.id)).where(
            CreditTransfer.sender_id == current_user.id
        )
    ).one()

    # Calculate cost in Naira
    cost_naira = credits_shared * settings.NAIRA_TO_CREDIT_RATE
    
    # Return with camelCase keys for frontend
    return {
        "availableCredits": int(available_credits),
        "totalRecipients": total_recipients,
        "creditsShared": int(credits_shared),
        "totalTransfers": total_transfers,
        "costNaira": float(cost_naira),
    }


@router.get("/resolve-tag/{tag}", response_model=UserPublic | None)
def resolve_tag(
    tag: str,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Resolve a user tag number to public user info.
    """
    # Clean tag: strip whitespace, remove @ if present, and strip again
    print(f"DEBUG: Resolving tag original: '{tag}'")
    tag = tag.strip()
    clean_tag = tag[1:].strip() if tag.startswith("@") else tag
    print(f"DEBUG: Resolving tag cleaned: '{clean_tag}'")
    
    user = session.exec(
        select(User).where(User.tag_number.ilike(clean_tag))
    ).first()
    
    if not user:
        print(f"DEBUG: User not found for tag: '{clean_tag}'")
        return None
        
    print(f"DEBUG: User found: {user.email}")
    return UserPublic.from_user(user)


@router.get("/transactions", response_model=CreditTransferList)
def get_credit_transactions(
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search by recipient name or email"),
) -> Any:
    """
    Get paginated list of credit transactions for the current user.

    Includes both sent and received transactions.

    Query Parameters:
        - page: Page number (default: 1)
        - page_size: Number of items per page (default: 10, max: 100)
        - search: Optional search term to filter by recipient name/email
    """
    # Build base query - transactions where user is sender or recipient
    query = select(CreditTransfer).where(
        or_(
            CreditTransfer.sender_id == current_user.id,
            CreditTransfer.recipient_id == current_user.id,
        )
    )

    # Add search filter if provided
    if search:
        # Join with recipient user to search by name/email
        query = (
            query.join(
                User,
                CreditTransfer.recipient_id == User.id,
            )
            .where(
                or_(
                    User.full_name.ilike(f"%{search}%"),  # type: ignore
                    User.email.ilike(f"%{search}%"),  # type: ignore
                )
            )
        )

    # Get total count
    count_query = select(func.count()).select_from(query.subquery())
    total = session.exec(count_query).one()

    # Apply pagination
    query = query.order_by(CreditTransfer.created_at.desc())  # type: ignore
    query = query.offset((page - 1) * page_size).limit(page_size)

    # Execute query
    transactions = session.exec(query).all()

    # Enrich with recipient information
    transactions_public = []
    for transaction in transactions:
        # Get recipient info
        recipient = session.get(User, transaction.recipient_id)

        transaction_public = CreditTransferPublic(
            id=transaction.id,
            senderId=transaction.sender_id,
            recipientId=transaction.recipient_id,
            amount=transaction.amount,
            message=transaction.message,
            status=transaction.status,
            createdAt=transaction.created_at,
            updatedAt=transaction.updated_at,
            recipientName=recipient.full_name if recipient else None,
            recipientEmail=str(recipient.email) if recipient else None,
        )
        transactions_public.append(transaction_public)

    return CreditTransferList(
        transactions=transactions_public,
        total=total,
    )


@router.post("/transfer", response_model=Message)
async def transfer_credits(
    request: Request,
    data: CreditTransferCreate,
    session: Session = Depends(deps.get_db),
    current_user: User = Depends(deps.get_current_user),
) -> Any:
    """
    Transfer credits to one or more team members.

    Request Body:
        - recipient_ids: List of recipient user IDs
        - amount: Amount of credits to transfer per recipient
        - message: Optional message to include with the transfer

    Validates:
        - User has sufficient credits
        - Recipients exist and are active
        - Recipients are not the sender
    """
    # Debug: log incoming data
    try:
        body = await request.json()
        print(f"DEBUG transfer: RAW BODY={body}")
    except Exception as e:
        print(f"DEBUG transfer: Could not read raw body: {e}")

    print(f"DEBUG transfer: data={data}")
    print(f"DEBUG transfer: data.recipientIds={data.recipientIds}")
    print(f"DEBUG transfer: data.recipientTags={data.recipientTags}")
    print(f"DEBUG transfer: data.amount={data.amount}")
    print(f"DEBUG transfer: data.message={data.message}")
    
    # Resolve tags to user IDs if provided
    recipient_ids = list(data.recipientIds or [])
    if data.recipientTags:
        for tag in data.recipientTags:
            tag = tag.strip()
            clean_tag = tag[1:].strip() if tag.startswith("@") else tag
            user = session.exec(select(User).where(User.tag_number.ilike(clean_tag))).first()
            if not user:
                raise HTTPException(status_code=404, detail=f"User with tag {tag} not found")
            if user.id not in recipient_ids:
                recipient_ids.append(user.id)

    if not recipient_ids:
        raise HTTPException(status_code=400, detail="No recipients specified")

    # Calculate total credits needed
    total_amount = data.amount * len(recipient_ids)

    # Check if user has sufficient credits
    current_balance = get_user_credit_balance(session=session, user_id=current_user.id)
    if current_balance < total_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient credits. You have {int(current_balance)} credits but need {total_amount}",
        )

    # Validate all recipients exist and are active
    for recipient_id in recipient_ids:
        # Check if trying to send to self
        if recipient_id == current_user.id:
            raise HTTPException(
                status_code=400,
                detail="Cannot transfer credits to yourself",
            )

        # Check recipient exists and is active
        recipient = session.get(User, recipient_id)
        if not recipient:
            raise HTTPException(
                status_code=404,
                detail=f"Recipient with ID {recipient_id} not found",
            )
        if not recipient.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Recipient {recipient.full_name or recipient.email} is not active",
            )

    # Deduct credits from sender's wallet (creates transaction history)
    deduct_credits(
        session=session,
        user_id=current_user.id,
        amount=total_amount,
        transaction_type="transfer_out",
        description=f"Shared {total_amount} credits with {len(recipient_ids)} recipient(s)",
    )

    # Create transactions for each recipient
    for recipient_id in recipient_ids:
        recipient = session.get(User, recipient_id)
        if recipient:
            # Add credits to recipient's wallet (creates transaction history)
            add_credits(
                session=session,
                user_id=recipient.id,
                amount=data.amount,
                transaction_type="transfer_in",
                description=f"Received {data.amount} credits from {current_user.full_name or current_user.email}" + (f": {data.message}" if data.message else ""),
                reference_id=None,
            )

            # Create shared credit transfer record (for shared credits page history)
            transaction = CreditTransfer(
                sender_id=current_user.id,
                recipient_id=recipient_id,
                amount=data.amount,
                message=data.message,
                status=TransactionStatus.COMPLETED,
            )
            session.add(transaction)

            # Send email notification
            try:
                email_service.send_credit_received_notification(
                    email_to=str(recipient.email),
                    username=recipient.full_name or str(recipient.email).split('@')[0],
                    sender_name=current_user.full_name or str(current_user.email),
                    amount=data.amount,
                    message=data.message,
                    credits_balance=int(recipient.credits) if recipient.credits else None
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
                    description=f"You received {data.amount} credits from {current_user.full_name or current_user.email}.",
                    type="credit_received",
                    metadata={
                        "sender_id": str(current_user.id),
                        "amount": data.amount,
                        "message": data.message
                    }
                )
            except Exception as e:
                print(f"Failed to create notification: {e}")


    # Commit all changes
    session.commit()

    return Message(
        message=f"Successfully transferred {total_amount} credits to {len(recipient_ids)} recipient(s)"
    )
