"""
User Credit Service - Peer-to-Peer Credit Transfers

Handles credit transfers between users' personal wallets.
"""

import uuid
import logging
from decimal import Decimal
from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Session, select
from fastapi import HTTPException

from app.models import User, CreditTransaction, WalletOwnerType
from app.core.config import settings
from app.services.email_service import email_service, EmailType
from app.utils.tag_generator import normalize_tag_number
from app.notification_repository import create_notification
from app.services.wallet_service import WalletService

logger = logging.getLogger(__name__)


def get_user_by_email_or_tag(
    session: Session,
    identifier: str
) -> Optional[User]:
    """
    Find user by email or tag number.

    Args:
        session: Database session
        identifier: Email address or tag number (with or without @)

    Returns:
        User object if found, None otherwise
    """
    # Try as email first
    statement = select(User).where(User.email == identifier.lower().strip())
    user = session.exec(statement).first()

    if user:
        return user

    # Try as tag number
    normalized_tag = normalize_tag_number(identifier)
    statement = select(User).where(User.tag_number == normalized_tag)
    user = session.exec(statement).first()

    return user


def transfer_credits(
    *,
    session: Session,
    sender: User,
    recipient_identifier: str,
    amount: Decimal,
    message: Optional[str] = None,
    reference_name: Optional[str] = None,
    transaction_type_override: Optional[str] = None
) -> dict:
    """
    Transfer credits from sender's personal wallet to recipient's wallet.

    Args:
        session: Database session
        sender: User sending credits
        recipient_identifier: Recipient's email or tag number
        amount: Amount of credits to transfer
        message: Optional message to recipient

    Returns:
        Dictionary with transaction details

    Raises:
        HTTPException: If validation fails or transfer cannot be completed
    """
    # Validate amount
    if amount <= 0:
        raise HTTPException(
            status_code=400,
            detail="Transfer amount must be greater than 0"
        )

    # Find recipient
    recipient = get_user_by_email_or_tag(session, recipient_identifier)

    if not recipient:
        raise HTTPException(
            status_code=404,
            detail=f"User not found: {recipient_identifier}"
        )

    # Check if sender is trying to send to themselves
    if sender.id == recipient.id:
        raise HTTPException(
            status_code=400,
            detail="Cannot transfer credits to yourself"
        )

    # Check sender has enough credits
    sender_balance = sender.credits or 0
    if sender_balance < amount:
        raise HTTPException(
            status_code=400,
            detail=f"Insufficient credits. You have {sender_balance} credits, but need {amount}"
        )

    try:
        description = f"Sent {int(amount)} credits to {recipient.full_name or recipient.email}" + (f": {message}" if message else "")
        
        sender_tx, recipient_tx = WalletService.transfer_p2p(
            session=session,
            sender_id=sender.id,
            recipient_id=recipient.id,
            amount=amount,
            description=description
        )

        # Create in-app notification (part of the same transaction)
        create_notification(
            session=session,
            user_id=recipient.id,
            title="Credits Received! 🎉",
            description=f"You received {int(amount)} credits from {sender.full_name or sender.email}.",
            type="credit_received",
            metadata={
                "sender_id": str(sender.id),
                "amount": float(amount),
                "message": message
            },
            commit=False # Don't commit yet, we commit everything at once
        )

        # Now commit everything: balances, credit transactions, and notification record
        session.commit()
        
        # Refresh objects to get latest states from DB
        session.refresh(sender)
        session.refresh(recipient)

        logger.info(
            f"Credit transfer successful: {sender.email} -> {recipient.email}, "
            f"Amount: {amount}, Sender balance: {sender.credits}, "
            f"Recipient balance: {recipient.credits}"
        )

        # Send email notification to recipient (Side-effect: Only happens if DB work succeeded)
        try:
            send_email_notification(
                sender=sender,
                recipient=recipient,
                amount=amount,
                message=message,
                reference_name=reference_name
            )
        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")
            # Don't fail the transfer if email fails

        return {
            "success": True,
            "sender": {
                "id": str(sender.id),
                "email": sender.email,
                "full_name": sender.full_name,
                "new_balance": float(sender.credits) if sender.credits is not None else 0.0
            },
            "recipient": {
                "id": str(recipient.id),
                "email": recipient.email,
                "full_name": recipient.full_name,
                "tag_number": recipient.tag_number,
                "new_balance": float(recipient.credits) if recipient.credits is not None else 0.0
            },
            "amount": float(amount),
            "transaction_id": str(sender_tx.id),
            "timestamp": sender_tx.created_at.isoformat()
        }

    except HTTPException:
        session.rollback()
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Credit transfer failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to transfer credits: {str(e)}"
        )


def send_email_notification(
    sender: User,
    recipient: User,
    amount: int,
    message: Optional[str] = None,
    reference_name: Optional[str] = None
):
    """Send email notification to recipient about credit transfer."""

    sender_name = sender.full_name or sender.email
    recipient_name = recipient.full_name or recipient.email
    
    current_date = datetime.now(timezone.utc).strftime("%B %d, %Y at %I:%M %p UTC")

    subject = f"Credits Allocated! 🎉"

    html_content = f"""
    <div style="font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif; max-width: 600px; margin: 0 auto; background-color: #ffffff; padding: 20px;">
        <!-- Header -->
        <div style="background-color: #0046B5; color: white; padding: 40px 20px; text-align: center; border-radius: 12px; margin-bottom: 40px; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);">
            <h1 style="margin: 0; font-size: 28px; font-weight: bold; letter-spacing: -0.5px;">Credits Allocated! 🎉</h1>
        </div>

        <!-- Body -->
        <div style="padding: 0 10px;">
            <p style="font-size: 16px; color: #1e293b; margin-bottom: 24px;">Hello {recipient_name},</p>
            
            <p style="font-size: 16px; color: #334155; line-height: 1.6; margin-bottom: 32px;">
                Great news! You have been allocated 
                <span style="color: #0046B5; font-weight: 800; font-size: 19px;">{amount} AI credits</span> 
                from <strong>{sender_name}</strong>.
            </p>

            <!-- Details Card -->
            <div style="background-color: #F8FAFC; border-radius: 12px; padding: 32px; border-left: 5px solid #0046B5; margin-bottom: 32px; box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);">
                <div style="margin-bottom: 12px; display: flex; align-items: flex-start;">
                    <strong style="color: #64748B; font-size: 14px; min-width: 80px; text-transform: uppercase; letter-spacing: 0.05em;">Amount:</strong>
                    <span style="color: #1E293B; font-size: 14px; font-weight: 600;">{amount} credits</span>
                </div>
                <div style="margin-bottom: 12px; display: flex; align-items: flex-start;">
                    <strong style="color: #64748B; font-size: 14px; min-width: 80px; text-transform: uppercase; letter-spacing: 0.05em;">From:</strong>
                    <span style="color: #1E293B; font-size: 14px; font-weight: 600;">{sender_name}</span>
                </div>
                {f'''<div style="margin-bottom: 12px; display: flex; align-items: flex-start;">
                    <strong style="color: #64748B; font-size: 14px; min-width: 80px; text-transform: uppercase; letter-spacing: 0.05em;">Message:</strong>
                    <span style="color: #1E293B; font-size: 14px; font-weight: 600;">{message}</span>
                </div>''' if message else ''}
                {f'''<div style="margin-bottom: 12px; display: flex; align-items: flex-start;">
                    <strong style="color: #64748B; font-size: 14px; min-width: 80px; text-transform: uppercase; letter-spacing: 0.05em;">Reference:</strong>
                    <span style="color: #1E293B; font-size: 14px; font-weight: 600;">{reference_name}</span>
                </div>''' if reference_name else ''}
                <div style="display: flex; align-items: flex-start;">
                    <strong style="color: #64748B; font-size: 14px; min-width: 80px; text-transform: uppercase; letter-spacing: 0.05em;">Date:</strong>
                    <span style="color: #1E293B; font-size: 14px; font-weight: 600;">{current_date}</span>
                </div>
            </div>

            <p style="font-size: 16px; color: #334155; line-height: 1.6; margin-bottom: 40px;">
                These credits have been added to your personal wallet and are ready to use!
            </p>

            <!-- Button -->
            <div style="text-align: center; margin-bottom: 40px;">
                <a href="{settings.FRONTEND_HOST}" style="background-color: #0046B5; color: white; padding: 16px 40px; text-decoration: none; border-radius: 8px; font-weight: bold; font-size: 16px; display: inline-block; box-shadow: 0 4px 6px -1px rgba(0, 70, 181, 0.2);">View Your Wallet</a>
            </div>
        </div>
    </div>
    """

    try:
        email_service.send_email(
            email_to=recipient.email,
            subject=subject,
            html_content=html_content,
            email_type=EmailType.TRANSACTION_ALERT
        )
        logger.info(f"Credit transfer email sent to {recipient.email}")
    except Exception as e:
        logger.error(f"Failed to send credit transfer email: {e}")
        raise


def get_user_balance(user_id: uuid.UUID, session: Session) -> int:
    """
    Get user's current credit balance from WalletService.
    """
    wallet = WalletService.get_or_create_wallet(session, user_id, WalletOwnerType.USER)
    balance = WalletService.get_balance(session, wallet.id)
    return int(balance)


def get_user_transactions(
    *,
    session: Session,
    user_id: uuid.UUID,
    limit: int = 50,
    offset: int = 0
) -> list[CreditTransaction]:
    """
    Get user's credit transaction history.

    Args:
        session: Database session
        user_id: User ID
        limit: Maximum number of transactions to return
        offset: Number of transactions to skip

    Returns:
        List of credit transactions
    """
    statement = (
        select(CreditTransaction)
        .where(CreditTransaction.user_id == user_id)
        .order_by(CreditTransaction.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    transactions = session.exec(statement).all()
    return list(transactions)
