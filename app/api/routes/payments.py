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
    User,
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
    receipt_base64: str | None = None
    receipt_filename: str | None = None


@router.post("/submit-proof", response_model=PaymentPublic)
def submit_payment_proof(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    data: PaymentProofSubmission
) -> Any:
    """
    Submit payment proof (bank transfer receipt) for manual verification.
    Creates a pending_verification payment record that admins can review and approve.
    """
    ref = f"PROOF-{current_user.id.hex[:6].upper()}-{uuid.uuid4().hex[:6].upper()}"
    
    receipt_url = None
    if data.receipt_base64:
        try:
            import base64
            import os
            # Remove base64 data URL prefix if exists (e.g. data:image/png;base64,)
            base64_str = data.receipt_base64
            if "," in base64_str:
                base64_str = base64_str.split(",")[1]
            
            file_data = base64.b64decode(base64_str)
            
            # Extract extension or default to png
            ext = "png"
            if data.receipt_filename and "." in data.receipt_filename:
                ext = data.receipt_filename.split(".")[-1]
            
            filename = f"{uuid.uuid4().hex}.{ext}"
            os.makedirs("uploads/receipts", exist_ok=True)
            filepath = os.path.join("uploads/receipts", filename)
            with open(filepath, "wb") as f:
                f.write(file_data)
            
            receipt_url = f"/uploads/receipts/{filename}"
        except Exception as e:
            logger.error(f"Failed to save payment proof receipt file: {e}")
            raise HTTPException(status_code=400, detail="Failed to process receipt file upload")

    payment = Payment(
        user_id=current_user.id,
        amount=data.amount,
        currency="NGN",
        status="pending_verification",
        payment_method="bank_transfer",
        transaction_reference=ref,
        description=f"{data.purpose} | Date: {data.payment_date}",
        receipt_url=receipt_url,
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


@router.get(
    "/pending-proofs",
    dependencies=[Depends(RequiresPermission("payment:manage"))],
    response_model=PaymentsPublic
)
def read_pending_proofs(
    session: SessionDep,
    page: int = 1,
    page_size: int = 100
) -> Any:
    """
    Retrieve all payments pending verification (Admin only).
    """
    statement = (
        select(Payment)
        .where(Payment.status == "pending_verification")
        .order_by(desc(Payment.created_at))
    )
    count_statement = select(func.count()).select_from(statement.subquery())
    count = session.exec(count_statement).one()
    
    skip = (page - 1) * page_size
    payments = session.exec(statement.offset(skip).limit(page_size)).all()
    
    return PaymentsPublic(data=payments, count=count)


class RejectionRequest(BaseModel):
    reason: str


@router.post(
    "/{payment_id}/approve",
    dependencies=[Depends(RequiresPermission("payment:manage"))],
    response_model=PaymentPublic
)
def approve_payment(
    *,
    session: SessionDep,
    payment_id: uuid.UUID
) -> Any:
    """
    Approve a pending payment proof (Admin only).
    Marks status as completed.
    """
    payment = session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
        
    if payment.status != "pending_verification":
        raise HTTPException(status_code=400, detail="Only payments pending verification can be approved")
        
    payment.status = "completed"
    payment.rejection_reason = None
    payment.updated_at = datetime.now(timezone.utc)
    
    session.add(payment)
    session.commit()
    session.refresh(payment)
    
    # Notify member via in-app notification
    try:
        from app.utils.notifications import create_notification
        create_notification(
            session=session,
            user_id=payment.user_id,
            title="Payment Approved",
            description=f"Your payment proof of ₦{payment.amount:,.0f} has been verified and approved.",
            notification_type="success",
            metadata={"payment_id": str(payment.id), "type": "payment_approved"}
        )
    except Exception as e:
        logger.error(f"Failed to create notification for approved payment: {e}")
        
    # Send email confirmation
    try:
        from app.services.email_service import email_service
        user = session.get(User, payment.user_id)
        if user and user.email:
            email_html = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: 'Inter', Arial, sans-serif; padding: 40px; background-color: #f9f9f9;">
                <div style="max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 24px; border: 1px solid #eee;">
                    <h2 style="color: #2e7d32; font-size: 24px; font-weight: 800; margin-bottom: 24px;">Payment Receipt & Confirmation</h2>
                    <p style="font-size: 16px; color: #444; line-height: 1.6;">Hello <strong>{{user.full_name or 'Member'}}</strong>,</p>
                    <p style="font-size: 16px; color: #444; line-height: 1.6;">Your bank transfer payment proof has been successfully verified and approved.</p>
                    
                    <div style="margin: 32px 0; padding: 24px; background-color: #e8f5e9; border-radius: 16px; border: 1px solid #c8e6c9;">
                        <div style="font-size: 12px; font-weight: 800; color: #2e7d32; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Amount Credited</div>
                        <div style="font-size: 32px; font-weight: 900; color: #2e7d32;">₦{{float(payment.amount):,.2f}}</div>
                        <div style="font-size: 14px; color: #555; margin-top: 8px;">Ref: {payment.transaction_reference}</div>
                    </div>

                    <p style="font-size: 15px; color: #666; margin-bottom: 32px;">This serves as official confirmation of your payment. Thank you for your support of FGCEOSA.</p>
                    
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 40px 0;">
                    <p style="font-size: 12px; color: #999; text-align: center;">FGCEOSA Alumni Network</p>
                </div>
            </body>
            </html>
            """
            email_service.send_email(
                email_to=user.email,
                subject="Payment Approved & Confirmed - FGCEOSA",
                html_content=email_html
            )
    except Exception as e:
        logger.error(f"Failed to send approval email: {e}")
        
    return payment


@router.post(
    "/{payment_id}/reject",
    dependencies=[Depends(RequiresPermission("payment:manage"))],
    response_model=PaymentPublic
)
def reject_payment(
    *,
    session: SessionDep,
    payment_id: uuid.UUID,
    data: RejectionRequest
) -> Any:
    """
    Reject a pending payment proof (Admin only).
    Marks status as rejected and stores the reason.
    """
    payment = session.get(Payment, payment_id)
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
        
    if payment.status != "pending_verification":
        raise HTTPException(status_code=400, detail="Only payments pending verification can be rejected")
        
    payment.status = "rejected"
    payment.rejection_reason = data.reason
    payment.updated_at = datetime.now(timezone.utc)
    
    session.add(payment)
    session.commit()
    session.refresh(payment)
    
    # Notify member via in-app notification
    try:
        from app.utils.notifications import create_notification
        create_notification(
            session=session,
            user_id=payment.user_id,
            title="Payment Rejected",
            description=f"Your payment proof of ₦{payment.amount:,.0f} was declined. Reason: {data.reason}",
            notification_type="error",
            metadata={"payment_id": str(payment.id), "type": "payment_rejected"}
        )
    except Exception as e:
        logger.error(f"Failed to create notification for rejected payment: {e}")
        
    # Send email notification
    try:
        from app.services.email_service import email_service
        user = session.get(User, payment.user_id)
        if user and user.email:
            email_html = f"""
            <!DOCTYPE html>
            <html>
            <body style="font-family: 'Inter', Arial, sans-serif; padding: 40px; background-color: #f9f9f9;">
                <div style="max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 24px; border: 1px solid #eee;">
                    <h2 style="color: #c62828; font-size: 24px; font-weight: 800; margin-bottom: 24px;">Payment Decline Notice</h2>
                    <p style="font-size: 16px; color: #444; line-height: 1.6;">Hello <strong>{{user.full_name or 'Member'}}</strong>,</p>
                    <p style="font-size: 16px; color: #444; line-height: 1.6;">Your submitted bank transfer payment proof was declined for the following reason:</p>
                    
                    <div style="margin: 32px 0; padding: 24px; background-color: #ffebee; border-radius: 16px; border: 1px solid #ffcdd2;">
                        <div style="font-size: 12px; font-weight: 800; color: #c62828; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Rejection Reason</div>
                        <div style="font-size: 16px; font-weight: 700; color: #c62828; line-height: 1.5;">{data.reason}</div>
                        <div style="font-size: 14px; color: #555; margin-top: 16px;">Amount Submitted: ₦{float(payment.amount):,.2f}</div>
                    </div>

                    <p style="font-size: 15px; color: #666; margin-bottom: 32px;">Please visit the payments dashboard to submit a correct proof or contact support if you believe this was an error.</p>
                    
                    <hr style="border: 0; border-top: 1px solid #eee; margin: 40px 0;">
                    <p style="font-size: 12px; color: #999; text-align: center;">FGCEOSA Alumni Network</p>
                </div>
            </body>
            </html>
            """
            email_service.send_email(
                email_to=user.email,
                subject="Action Required: Payment Declined - FGCEOSA",
                html_content=email_html
            )
    except Exception as e:
        logger.error(f"Failed to send rejection email: {e}")
        
    return payment


@router.post("/paystack/webhook")
async def paystack_webhook(
    request: Request,
    session: SessionDep
) -> Any:
    """
    Handle incoming Paystack webhooks to verify and record payments asynchronously.
    """
    payload = await request.body()
    signature = request.headers.get("x-paystack-signature")
    
    if not signature:
        logger.warning("Paystack webhook received without signature header.")
        raise HTTPException(status_code=400, detail="Missing signature")
        
    # Verify signature
    from app.payments.payment_factory import PaymentFactory
    provider = PaymentFactory.get_provider()
    
    # Check if active credentials override is available from settings
    system_settings = session.get(SystemSettings, 1)
    if system_settings and system_settings.paystack_secret_key:
        from app.payments.providers.paystack.provider import PaystackProvider
        provider = PaystackProvider(
            secret_key=system_settings.paystack_secret_key,
            public_key=system_settings.paystack_public_key
        )
        
    is_valid = await provider.validate_webhook_signature(payload, signature)
    if not is_valid:
        logger.warning("Paystack webhook signature verification failed.")
        raise HTTPException(status_code=400, detail="Invalid signature")
        
    data = await request.json()
    event = data.get("event")
    
    if event == "charge.success":
        event_data = data.get("data", {})
        reference = event_data.get("reference")
        amount = Decimal(str(event_data.get("amount", 0))) / 100 # Convert kobo to Naira
        
        statement = select(Payment).where(Payment.transaction_reference == reference)
        payment = session.exec(statement).first()
        
        if payment:
            if payment.status != "completed":
                payment.status = "completed"
                payment.paystack_id = str(event_data.get("id"))
                payment.payment_method = event_data.get("channel") or "paystack"
                payment.updated_at = datetime.now(timezone.utc)
                session.add(payment)
                
                # Notify Admins
                try:
                    from app.utils.notifications import notify_admins
                    user = session.get(User, payment.user_id)
                    user_full_name = user.full_name if user else ""
                    user_email = user.email if user else ""
                    notify_admins(
                        session=session,
                        title="Online Payment Received (Webhook)",
                        description=f"{user_full_name or user_email} paid ₦{amount:,.0f} via {payment.payment_method}.",
                        notification_type="success",
                        metadata={
                            "payment_id": str(payment.id),
                            "user_id": str(payment.user_id),
                            "type": "online_payment"
                        }
                    )
                except Exception as notif_err:
                    logger.error(f"Failed to notify admins via webhook: {notif_err}")

                # Notify Member
                try:
                    from app.utils.notifications import create_notification
                    create_notification(
                        session=session,
                        user_id=payment.user_id,
                        title="Payment Confirmed",
                        description=f"Your payment of ₦{amount:,.0f} has been successfully verified. Thank you!",
                        notification_type="success",
                        metadata={
                            "payment_id": str(payment.id),
                            "type": "payment_confirmed"
                        }
                    )
                except Exception as member_notif_err:
                    logger.error(f"Failed to notify member via webhook: {member_notif_err}")

                session.commit()
                logger.info(f"Payment reference {reference} successfully verified via webhook.")
            else:
                logger.info(f"Payment reference {reference} was already completed.")
        else:
            logger.warning(f"Payment reference {reference} received via webhook but not found in DB.")
            
    return {"status": "success"}
