"""
Credits and Top-Up API Routes

Handles:
- Credit top-up via bank transfer (Flutterwave/Monnify)
- Top-up status checking
- Credit balance queries
- Transaction history
- Webhook processing for payment providers
"""
import logging
import uuid
from typing import Any
from decimal import Decimal
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, status, Header, Request, Depends
from sqlmodel import select, func, col

from app.api.deps import CurrentUser, SessionDep, RequiresPermission
from app.models import (
    TopUp,
    TopUpCreate,
    TopUpPublic,
    TopUpStatus,
    TopUpStatusResponse,
    CreditTransaction,
    User,
)
from app.payments.payment_service import payment_service
from app.credit_repository import add_credits, get_user_credit_balance
from app.core.config import settings
from app.services.user_credit_service import transfer_credits as execute_transfer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/credits", tags=["credits"])


# ==================== Helper Functions ====================

def calculate_ai_credits(naira_amount: Decimal) -> Decimal:
    """Calculate AI credits from Naira amount"""
    return (naira_amount / Decimal(settings.NAIRA_TO_CREDIT_RATE)).quantize(Decimal("0.0001"))


# ==================== Endpoints ====================

@router.post("/top-up")
async def initiate_top_up(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    top_up_in: TopUpCreate,
) -> Any:
    """
    Initiate a credit top-up via bank transfer

    Creates a virtual bank account and pending top-up record.
    Uses the configured payment provider (Flutterwave by default).

    The payment provider will generate a dedicated virtual account
    for this transaction that can be used for bank transfer.
    """
    # Enforce minimum credit purchase from platform settings
    from app.models import PlatformSettings
    platform_settings = session.exec(select(PlatformSettings)).first()
    min_amount = 1000  # Default fallback
    
    if platform_settings and "payments" in platform_settings.payments:
        min_amount = platform_settings.payments.get("minCreditAmount", 1000)
    elif platform_settings:
        min_amount = platform_settings.payments.get("minCreditAmount", 1000)

    logger.info(f"Initiating top-up for {current_user.email}. Request: {top_up_in.model_dump()}")
    
    # Robust handling of IDs from either snake_case or camelCase (if Pydantic alias fails for any reason)
    org_id = top_up_in.organization_id 
    if not org_id and hasattr(top_up_in, "organizationId"):
         org_id = getattr(top_up_in, "organizationId")
    
    ws_id = top_up_in.workspace_id
    if not ws_id and hasattr(top_up_in, "workspaceId"):
         ws_id = getattr(top_up_in, "workspaceId")

    # Filter out empty strings/null strings which can happen from frontend
    if isinstance(org_id, str) and (not org_id.strip() or org_id.lower() == 'null' or org_id.lower() == 'undefined'):
        org_id = None
    if isinstance(ws_id, str) and (not ws_id.strip() or ws_id.lower() == 'null' or ws_id.lower() == 'undefined'):
        ws_id = None

    # Inference logic: If org_id is missing but current_user is an org_super_admin, 
    # try to resolve their organization automatically. This fixes frontend race conditions.
    if not org_id and not ws_id:
        from app.models import OrganizationMember
        # Check if user is an org_super_admin in exactly one organization
        admin_orgs = session.exec(
            select(OrganizationMember.organization_id)
            .where(OrganizationMember.user_id == current_user.id)
            .where(OrganizationMember.role == "org_super_admin")
            .where(OrganizationMember.status == "active")
        ).all()
        
        if len(admin_orgs) == 1:
            org_id = admin_orgs[0]
            logger.info(f"Inferred Org ID {org_id} for org_super_admin {current_user.email} since it was missing in request.")

    logger.info(f"Resolved Org ID: {org_id} (Type: {type(org_id)}), WS ID: {ws_id} (Type: {type(ws_id)})")

    if top_up_in.amount < Decimal(str(min_amount)):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Minimum top-up amount is ₦{min_amount:,.0f}"
        )

    # Detect payment method even if sent as camelCase paymentMethod
    pm = top_up_in.payment_method
    if hasattr(top_up_in, "paymentMethod"):
        pm = getattr(top_up_in, "paymentMethod")

    try:
        # Use payment service to initiate top-up
        result = await payment_service.initiate_topup(
            amount=float(top_up_in.amount),
            user_id=str(current_user.id),
            email=current_user.email,
            db=session,
            workspace_id=ws_id,
            organization_id=org_id,
            meta={
                "customer_name": current_user.full_name or current_user.email,
                "payment_method": pm
            }
        )

        logger.info(
            f"Created top-up {result['topup_id']} for user {current_user.email}: "
            f"₦{result['amount']} -> {result['ai_credits']} credits via {result['provider']}"
        )

        return {
            "id": result["topup_id"],
            "amount_naira": result["amount"],
            "ai_credits": result["ai_credits"],
            "status": result["status"],
            "payment_reference": result["reference"],
            "account_number": result["account_number"],
            "bank_name": result["bank_name"],
            "account_name": result.get("account_name", "Qorebit"),
            "expires_at": result["expires_at"],
            "provider": result["provider"],
            "message": result["message"]
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error initiating top-up for user {current_user.email}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate top-up: {str(e)}"
        )


@router.get("/top-up/{top_up_id}/status")
async def check_top_up_status(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    top_up_id: uuid.UUID,
) -> Any:
    """
    Check the status of a top-up

    This endpoint:
    1. Fetches the top-up record from database
    2. If still pending, queries payment provider to check for payment
    3. If payment found, processes it and updates status
    4. Returns current status

    Uses the payment service which abstracts provider details.
    """
    try:
        # Use payment service to get status
        result = await payment_service.get_topup_status(
            topup_id=top_up_id,
            db=session
        )

        # Verify this top-up belongs to the current user
        top_up = session.get(TopUp, top_up_id)
        if not top_up or top_up.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Top-up not found"
            )

        return {
            "topup_id": result["topup_id"],
            "reference": result["reference"],
            "status": result["status"],
            "amount": result["amount"],
            "ai_credits": result["ai_credits"],
            "account_number": result.get("account_number"),
            "bank_name": result.get("bank_name"),
            "created_at": result["created_at"],
            "paid_at": result.get("paid_at"),
            "expires_at": result.get("expires_at"),
            "provider": result["provider"]
        }

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error checking top-up status: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to check top-up status: {str(e)}"
        )


@router.post("/webhook/flutterwave")
async def flutterwave_webhook(
    *,
    request: Request,
    session: SessionDep,
    verif_hash: str = Header(None, alias="verif-hash"),
) -> Any:
    """
    Handle Flutterwave webhook notifications

    Called by Flutterwave when a payment event occurs.
    Verifies the webhook signature and processes successful payments.

    Webhook events handled:
    - charge.completed: Payment completed successfully
    """
    # IMPORTANT: Flutterwave stops retrying if it receives non-200 responses.
    # We MUST always return HTTP 200, even for errors.
    try:
        # Get raw payload for signature verification
        raw_payload = await request.body()
        payload = await request.json()

        # Debug logging for webhook troubleshooting
        logger.info(f"Received Flutterwave webhook event: {payload.get('event')}")
        logger.info(f"Webhook verif-hash present: {bool(verif_hash)}")
        logger.info(f"Webhook tx_ref: {payload.get('data', {}).get('tx_ref')}")
        logger.info(f"Webhook status: {payload.get('data', {}).get('status')}")
        logger.info(f"Webhook amount: {payload.get('data', {}).get('amount')}")

        # Process webhook using payment service
        result = await payment_service.process_webhook(
            payload=payload,
            signature=verif_hash or "",
            raw_payload=raw_payload,
            db=session
        )

        logger.info(f"Webhook processed successfully: {result}")
        return result

    except ValueError as e:
        # Return 200 so Flutterwave doesn't stop retrying due to auth errors
        logger.error(f"Webhook validation error (returning 200 anyway): {str(e)}")
        return {"status": "error", "message": str(e)}
    except Exception as e:
        # Return 200 so Flutterwave doesn't drop the event
        logger.error(f"Error processing Flutterwave webhook (returning 200 anyway): {str(e)}")
        return {"status": "error", "message": f"Webhook processing failed: {str(e)}"}


@router.post("/webhook/monnify")
async def monnify_webhook(
    *,
    request: Request,
    session: SessionDep,
    x_monnify_signature: str = Header(None),
) -> Any:
    """
    Handle Monnify webhook notifications (DEPRECATED - kept for backward compatibility)

    Called by Monnify when a payment is received.
    This endpoint is kept for backward compatibility with existing integrations.

    For new integrations, use Flutterwave webhook instead.

    Webhook events we handle:
    - SUCCESSFUL_TRANSACTION: Payment received successfully
    """
    try:
        # Get raw payload for signature verification
        raw_payload = await request.body()
        payload = await request.json()

        logger.info(f"Received Monnify webhook: {payload.get('eventType')}")

        # Process webhook using payment service
        result = await payment_service.process_webhook(
            payload=payload,
            signature=x_monnify_signature or "",
            raw_payload=raw_payload,
            db=session
        )

        return result

    except ValueError as e:
        logger.error(f"Webhook validation error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error processing Monnify webhook: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Webhook processing failed: {str(e)}"
        )


@router.post("/top-up/test")
async def test_top_up(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    amount: Decimal = Decimal("5000"),  # Default ₦5000
) -> dict[str, Any]:
    """
    **TEST ENDPOINT ONLY - FOR LOCAL DEVELOPMENT**

    Instantly add credits to your wallet without Monnify payment.
    This simulates a successful top-up for testing purposes.

    **DO NOT USE IN PRODUCTION** - This endpoint should be disabled
    or protected in production environments.

    Args:
        amount: Amount in Naira to add (default: ₦5000)

    Returns:
        Updated balance and transaction details
    """
    # WARNING: Only allow in development/local environments
    if settings.ENVIRONMENT not in ["local", "development"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Test top-up endpoint is disabled in production"
        )

    # Validate minimum amount
    if amount < Decimal("100"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Minimum test top-up amount is ₦100"
        )

    # Calculate AI credits
    ai_credits = calculate_ai_credits(amount)

    # Create a test top-up record
    payment_reference = f"TEST-{current_user.id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

    top_up = TopUp(
        user_id=current_user.id,
        amount_naira=amount,
        ai_credits=ai_credits,
        status=TopUpStatus.COMPLETED,
        payment_reference=payment_reference,
        monnify_reference=f"TEST-{uuid.uuid4()}",
        account_number="TEST-ACCOUNT",
        bank_name="Test Bank (Development Only)",
        payment_method="test_credit",
        paid_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )

    session.add(top_up)

    # Add credits to user account
    add_credits(
        session=session,
        user_id=current_user.id,
        amount=ai_credits,
        transaction_type="purchase",
        description=f"TEST Top-up: ₦{amount} (Development Only)",
        reference_id=str(top_up.id),
    )

    session.commit()
    session.refresh(top_up)

    # Get updated balance
    new_balance = get_user_credit_balance(session=session, user_id=current_user.id)
    naira_equivalent = new_balance * Decimal(settings.NAIRA_TO_CREDIT_RATE)

    logger.warning(
        f"TEST TOP-UP: Added ₦{amount} ({ai_credits} credits) to user {current_user.email}"
    )

    return {
        "success": True,
        "message": f"Successfully added ₦{amount} ({ai_credits} credits) to your wallet",
        "top_up": {
            "id": str(top_up.id),
            "amount_naira": float(amount),
            "ai_credits": float(ai_credits),
            "payment_reference": payment_reference,
        },
        "new_balance": {
            "ai_credits": float(new_balance),
            "naira_equivalent": float(naira_equivalent),
            "conversion_rate": settings.NAIRA_TO_CREDIT_RATE,
        }
    }


@router.get("/balance")
async def get_credit_balance(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """
    Get current credit balance for the user

    Returns both AI credits and Naira equivalent
    """
    balance = get_user_credit_balance(session=session, user_id=current_user.id)
    naira_equivalent = balance * Decimal(settings.NAIRA_TO_CREDIT_RATE)

    return {
        "ai_credits": float(balance),
        "naira_equivalent": float(naira_equivalent),
        "conversion_rate": settings.NAIRA_TO_CREDIT_RATE,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/transactions")
async def get_credit_transactions(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Get credit transaction history for the user from the unified Wallet system.
    Returns all credit additions and deductions.
    """
    try:
        from app.services.wallet_service import WalletService
        from app.models import WalletOwnerType, WalletTransaction

        # 1. Get User's Wallet
        wallet = WalletService.get_or_create_wallet(session, current_user.id, WalletOwnerType.USER)

        # 2. Get total count of transactions for this wallet
        count_stmt = select(func.count()).select_from(WalletTransaction).where(
            WalletTransaction.wallet_id == wallet.id
        )
        total = session.exec(count_stmt).one()

        # 3. Get transactions
        statement = (
            select(WalletTransaction)
            .where(WalletTransaction.wallet_id == wallet.id)
            .order_by(col(WalletTransaction.created_at).desc())
            .offset(skip)
            .limit(limit)
        )
        transactions = session.exec(statement).all()

        # 4. Calculate running balance (optional simplification: just return current balance for now or calculate if needed)
        
        # Let's fetch current balance
        current_balance = WalletService.get_balance(session, wallet.id)

        return {
            "transactions": [
                {
                    "id": str(t.id),
                    "amount": float(t.amount),
                    "balance_after": float(current_balance),
                    "transaction_type": str(t.transaction_type),
                    "description": t.description or (
                        "Top-up via bank transfer" if t.source in ["manual_topup", "repository_action"] 
                        else (t.source.replace('_', ' ').title() if t.source else "Transaction")
                    ),
                    "created_at": t.created_at.replace(tzinfo=timezone.utc).isoformat() if t.created_at.tzinfo is None else t.created_at.isoformat(),
                }
                for t in transactions
            ],
            "total": total,
            "skip": skip,
            "limit": limit,
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error(f"Error fetching transactions: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to fetch transactions: {str(e)}"
        )


@router.get("/top-ups")
async def get_top_up_history(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    skip: int = 0,
    limit: int = 50,
) -> dict[str, Any]:
    """
    Get top-up history for the user

    Returns all top-up attempts (pending, completed, failed)
    """
    # Get total count
    count_stmt = select(func.count()).select_from(TopUp).where(
        TopUp.user_id == current_user.id
    )
    total = session.exec(count_stmt).one()

    # Get top-ups
    statement = (
        select(TopUp)
        .where(TopUp.user_id == current_user.id)
        .order_by(col(TopUp.created_at).desc())
        .offset(skip)
        .limit(limit)
    )
    top_ups = session.exec(statement).all()

    return {
        "top_ups": [
            {
                **t.model_dump(by_alias=True, mode='json'),
                "created_at": t.created_at.replace(tzinfo=timezone.utc).isoformat() if t.created_at.tzinfo is None else t.created_at.isoformat(),
                "paid_at": t.paid_at.replace(tzinfo=timezone.utc).isoformat() if t.paid_at and t.paid_at.tzinfo is None else (t.paid_at.isoformat() if t.paid_at else None),
                "expires_at": t.expires_at.replace(tzinfo=timezone.utc).isoformat() if t.expires_at.tzinfo is None else t.expires_at.isoformat(),
            }
            for t in top_ups
        ],
        "total": total,
        "skip": skip,
        "limit": limit,
    }


@router.post("/transfer")
async def transfer_credits_to_user(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    recipient_identifier: str,
    amount: int,
    message: str | None = None,
) -> dict[str, Any]:
    """
    Transfer credits from your personal wallet to another user.

    You can identify the recipient by:
    - Email address: user@example.com
    - Tag number: qor7k2m9p or @qor7k2m9p

    Args:
        recipient_identifier: Recipient's email or tag number
        amount: Amount of credits to transfer (must be > 0)
        message: Optional message to recipient

    Returns:
        Transfer confirmation with sender and recipient details
    """
    try:
        result = execute_transfer(
            session=session,
            sender=current_user,
            recipient_identifier=recipient_identifier,
            amount=amount,
            message=message
        )

        logger.info(
            f"P2P Transfer: {current_user.email} -> {recipient_identifier}, "
            f"Amount: {amount} credits"
        )

        return {
            "success": True,
            "message": f"Successfully transferred {amount} credits to {result['recipient']['full_name'] or result['recipient']['email']}",
            "transfer": result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in P2P transfer: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transfer failed: {str(e)}"
        )


@router.post("/top-up/verify-pending")
async def verify_my_pending_topups(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    organization_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """
    Re-verify all pending top-ups for the current user (or org) with Flutterwave.

    Call this when returning to the wallet page — it checks if any previously
    initiated bank transfers have been completed and applies credits automatically.
    Safe to call repeatedly (idempotent).
    """
    from datetime import timedelta

    # Only look at PENDING topups created in the last 48 hours
    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)

    # Build query — filter by organization or user
    if organization_id:
        # Verify user belongs to the org before querying
        from app.models import OrganizationMember
        org_member = session.exec(
            select(OrganizationMember).where(
                OrganizationMember.user_id == current_user.id,
                OrganizationMember.organization_id == organization_id
            )
        ).first()
        if not org_member:
            raise HTTPException(status_code=403, detail="Not a member of this organization")

        statement = select(TopUp).where(
            TopUp.organization_id == organization_id,
            TopUp.status == TopUpStatus.PENDING,
            TopUp.created_at >= cutoff
        )
    else:
        statement = select(TopUp).where(
            TopUp.user_id == current_user.id,
            TopUp.status == TopUpStatus.PENDING,
            TopUp.created_at >= cutoff
        )

    pending_topups = session.exec(statement).all()
    logger.info(f"User {current_user.email} (Org: {organization_id}) found {len(pending_topups)} pending topups within the last 48h (since {cutoff})")
    
    if len(pending_topups) == 0:
        # Debug: Check if there are ANY topups for this org, even if not pending
        if organization_id:
             total_org_topups = session.exec(select(func.count(TopUp.id)).where(TopUp.organization_id == organization_id)).one()
             logger.info(f"DEBUG: Total topups ever for Org {organization_id}: {total_org_topups}")
        else:
             total_user_topups = session.exec(select(func.count(TopUp.id)).where(TopUp.user_id == current_user.id)).one()
             logger.info(f"DEBUG: Total topups ever for User {current_user.id}: {total_user_topups}")

    credited = []
    still_pending = []

    for topup in pending_topups:
        try:
            result = await payment_service.verify_topup(
                reference=topup.payment_reference,
                db=session
            )
            if result["status"] in ["success", "already_completed"]:
                credited.append({
                    "reference": topup.payment_reference,
                    "amount_naira": float(topup.amount_naira),
                    "ai_credits": float(topup.ai_credits),
                })
                logger.info(f"Auto-credited topup {topup.payment_reference} for user {current_user.email}")
            else:
                still_pending.append(topup.payment_reference)
        except Exception as e:
            logger.error(f"Error verifying topup {topup.payment_reference}: {str(e)}")
            still_pending.append(topup.payment_reference)

    return {
        "checked": len(pending_topups),
        "credited": credited,
        "still_pending": still_pending,
        "credits_applied": len(credited) > 0
    }


@router.post("/admin/verify-pending-payments", dependencies=[Depends(RequiresPermission("credit:treasury_manage"))])
async def verify_pending_payments(
    *,
    session: SessionDep,
    current_user: CurrentUser,
) -> dict[str, Any]:
    """
    Admin endpoint to verify all pending payments with Flutterwave.
    """

    # Get all pending top-ups
    statement = select(TopUp).where(TopUp.status == TopUpStatus.PENDING)
    pending_topups = session.exec(statement).all()

    results = {
        "total_pending": len(pending_topups),
        "verified_and_credited": [],
        "still_pending": [],
        "failed": [],
        "errors": []
    }

    for topup in pending_topups:
        try:
            # Use payment service to verify with Flutterwave
            verification_result = await payment_service.verify_topup(
                reference=topup.payment_reference,
                db=session
            )

            if verification_result["status"] == "success":
                results["verified_and_credited"].append({
                    "reference": topup.payment_reference,
                    "amount_naira": float(topup.amount_naira),
                    "ai_credits": float(topup.ai_credits),
                    "user_id": str(topup.user_id)
                })
            elif verification_result["status"] == "already_completed":
                results["verified_and_credited"].append({
                    "reference": topup.payment_reference,
                    "amount_naira": float(topup.amount_naira),
                    "ai_credits": float(topup.ai_credits),
                    "user_id": str(topup.user_id),
                    "note": "Was already completed"
                })
            else:
                results["still_pending"].append({
                    "reference": topup.payment_reference,
                    "amount_naira": float(topup.amount_naira)
                })

        except Exception as e:
            results["errors"].append({
                "reference": topup.payment_reference,
                "error": str(e)
            })
            logger.error(f"Error verifying payment {topup.payment_reference}: {str(e)}")

    logger.info(f"Admin verified pending payments: {len(results['verified_and_credited'])} credited, {len(results['still_pending'])} still pending")

    return results


@router.post("/admin/verify-single-payment/{reference}", dependencies=[Depends(RequiresPermission("credit:treasury_manage"))])
async def verify_single_payment(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    reference: str,
) -> dict[str, Any]:
    """
    Admin endpoint to verify a single payment by reference.
    """

    try:
        result = await payment_service.verify_topup(
            reference=reference,
            db=session
        )
        return result
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error verifying payment {reference}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Verification failed: {str(e)}"
        )
