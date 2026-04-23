import uuid
import logging
from typing import Any, List
from decimal import Decimal
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlmodel import select, func, desc
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentUser,
    SessionDep,
    RequiresPermission,
)
from app.models import (
    Payment,
    PaymentPublic,
    PaymentsPublic,
    PaymentCreate,
    Message,
)
from app.services.payment_service import payment_service
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/payments", tags=["payments"])

class PaymentInitialization(BaseModel):
    amount: Decimal
    description: str
    callback_url: str

class PaymentVerification(BaseModel):
    transaction_id: str

@router.post("/initialize", response_model=dict)
async def initialize_payment(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    data: PaymentInitialization
) -> Any:
    """
    Generate payment URL for member to pay dues.
    """
    result = await payment_service.initialize_payment(
        session=session,
        user=current_user,
        amount=data.amount,
        description=data.description,
        callback_url=data.callback_url
    )
    
    if result.get("status") == "success":
        return result
    else:
        raise HTTPException(status_code=400, detail=result.get("message", "Could not initialize payment"))

@router.get("/verify", response_model=PaymentPublic)
async def verify_payment(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    transaction_id: str = Query(...)
) -> Any:
    """
    Verify a payment after member is redirected back from Paystack.
    """
    result = await payment_service.verify_transaction(session=session, transaction_id=transaction_id)
    
    if result.get("status") == "success":
        return result["payment"]
    else:
        raise HTTPException(status_code=400, detail=result.get("message", "Verification failed"))

@router.get("/my-history", response_model=PaymentsPublic)
def read_my_payments(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 50
) -> Any:
    """
    Retrieve current member's payment history.
    """
    statement = select(Payment).where(Payment.user_id == current_user.id).order_by(desc(Payment.created_at))
    count_statement = select(func.count()).select_from(statement.subquery())
    count = session.exec(count_statement).one()
    
    skip = (page - 1) * page_size
    payments = session.exec(statement.offset(skip).limit(page_size)).all()
    
    return PaymentsPublic(data=payments, count=count)

@router.get(
    "/all",
    dependencies=[Depends(RequiresPermission("payment:manage"))],
    response_model=PaymentsPublic
)
def read_all_payments(
    session: SessionDep,
    page: int = 1,
    page_size: int = 100,
    status: str | None = None
) -> Any:
    """
    Retrieve all payments across the platform (Admin only).
    """
    statement = select(User, Payment).join(User, User.id == Payment.user_id).order_by(desc(Payment.created_at))
    
    if status:
        statement = statement.where(Payment.status == status)
        
    count_statement = select(func.count()).select_from(statement.subquery())
    count = session.exec(count_statement).one()
    
    skip = (page - 1) * page_size
    results = session.exec(statement.offset(skip).limit(page_size)).all()
    
    # Flatten the result (User, Payment) -> PaymentPublic
    output = []
    for user, pay in results:
        # We can enrich PaymentPublic with user details if needed, but for now standard schema
        output.append(pay)
        
    return PaymentsPublic(data=output, count=count)


class PaymentProofSubmission(BaseModel):
    purpose: str
    amount: Decimal
    payment_date: str
    receipt_url: str | None = None


@router.post("/submit-proof", response_model=PaymentPublic)
def submit_payment_proof(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    data: PaymentProofSubmission
) -> Any:
    """
    Submit payment proof (bank transfer receipt) for manual verification.
    Creates a pending payment record that admins can review and approve.
    """
    ref = f"PROOF-{current_user.id.hex[:6].upper()}-{uuid.uuid4().hex[:6].upper()}"

    payment = Payment(
        user_id=current_user.id,
        amount=data.amount,
        currency="NGN",
        status="pending",
        payment_method="bank_transfer",
        transaction_reference=ref,
        description=f"{data.purpose} | Date: {data.payment_date}" + (f" | Receipt: {data.receipt_url}" if data.receipt_url else ""),
    )

    session.add(payment)
    session.commit()
    session.refresh(payment)

    # Notify Admins
    try:
        from app.utils.notifications import notify_admins
        notify_admins(
            session=session,
            title="New Payment Proof Submitted",
            description=f"{current_user.full_name or current_user.email} submitted a proof for ₦{data.amount:,.0f} ({data.purpose}).",
            notification_type="info",
            metadata={
                "payment_id": str(payment.id),
                "user_id": str(current_user.id),
                "type": "payment_proof"
            }
        )
    except Exception as e:
        logger.error(f"Failed to notify admins of payment proof: {e}")

    logger.info(f"Payment proof submitted by user {current_user.id}: {ref} for ₦{data.amount}")

    return payment
