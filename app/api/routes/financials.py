import uuid
import logging
from typing import Any, List
from decimal import Decimal
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlmodel import select, func, desc, or_
import csv
import io

from app.api.deps import (
    CurrentUser,
    SessionDep,
    RequiresPermission,
)
from app.models import (
    User,
    Payment,
    Due,
    Message,
)
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter()

class PaymentAnalytics(BaseModel):
    totalCollected: str
    pendingPayments: str
    totalInvoices: int
    overdueMembers: int
    targetAmount: float
    collectedAmount: float
    percentageAchieved: float

class RecordPaymentRequest(BaseModel):
    memberId: str
    amount: float
    date: str
    paymentMethod: str
    category: str
    description: str | None = None
    sendReceipt: bool = True

@router.get("/analytics", response_model=PaymentAnalytics)
def get_payment_analytics(session: SessionDep) -> Any:
    """
    Get aggregated financial analytics for the Admin Payment Dashboard.
    """
    # Total Collected (Completed Payments)
    total_collected = session.exec(
        select(func.sum(Payment.amount)).where(Payment.status == "completed")
    ).one() or Decimal("0.00")
    
    # Pending Payments (Count)
    pending_amount = session.exec(
        select(func.sum(Payment.amount)).where(Payment.status == "pending")
    ).one() or Decimal("0.00")
    
    # Total Invoices (Total Payment records)
    total_invoices = session.exec(select(func.count()).select_from(Payment)).one()
    
    # Total Members
    total_members = session.exec(select(func.count()).select_from(User)).one()
    
    # Overdue Members (Members with at least one unpaid due)
    latest_due = session.exec(select(Due).order_by(desc(Due.due_date))).first()
    overdue_count = 0
    target_amount = 0.0
    collected_amount = float(total_collected)

    # Calculate Target Amount: Sum of active dues * total members
    active_dues = session.exec(select(Due).where(Due.is_active == True)).all()
    if not active_dues and latest_due:
        # If no dues are explicitly marked active, use the latest one as the target benchmark
        active_dues = [latest_due]
    
    if active_dues:
        target_amount = sum([float(d.amount) for d in active_dues]) * total_members
        
        # Calculate overdue members
        paid_member_ids = session.exec(
            select(Payment.user_id).where(Payment.status == "completed")
        ).all()
        overdue_count = max(0, total_members - len(set(paid_member_ids)))

    percentage = (collected_amount / target_amount * 100) if target_amount > 0 else 0

    return {
        "totalCollected": f"₦{float(total_collected):,.0f}",
        "pendingPayments": f"₦{float(pending_amount):,.0f}",
        "totalInvoices": total_invoices,
        "overdueMembers": overdue_count,
        "targetAmount": target_amount,
        "collectedAmount": collected_amount,
        "percentageAchieved": percentage
    }

@router.get("/transactions")
def get_transactions(
    session: SessionDep,
    search: str | None = None,
    startDate: str | None = None,
    endDate: str | None = None,
    page: int = 1,
    page_size: int = 50
) -> Any:
    """
    Get detailed payment transactions.
    """
    statement = select(User, Payment).join(Payment, User.id == Payment.user_id).order_by(desc(Payment.created_at))
    
    if search:
        search_filter = or_(
            User.full_name.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%"),
            Payment.transaction_reference.ilike(f"%{search}%")
        )
        statement = statement.where(search_filter)
        
    if startDate:
        try:
            start_dt = datetime.fromisoformat(startDate).replace(tzinfo=timezone.utc)
            statement = statement.where(Payment.created_at >= start_dt)
        except ValueError:
            pass
            
    if endDate:
        try:
            end_dt = datetime.fromisoformat(endDate).replace(tzinfo=timezone.utc)
            statement = statement.where(Payment.created_at <= end_dt)
        except ValueError:
            pass

    results = session.exec(statement.offset((page - 1) * page_size).limit(page_size)).all()
    
    data = []
    for user, payment in results:
        data.append({
            "id": str(payment.id),
            "invoiceId": f"INV-{str(payment.id)[:8].upper()}",
            "member": user.full_name or user.email,
            "email": user.email,
            "amount": f"₦{float(payment.amount):,.0f}",
            "paid": f"₦{float(payment.amount):,.0f}" if payment.status == "completed" else "₦0",
            "status": payment.status.capitalize() if payment.status else "Pending",
            "date": payment.created_at.isoformat(),
            "ref": payment.transaction_reference,
            "method": payment.payment_method or "Online"
        })
        
    return data

@router.get("/outstanding")
def get_outstanding_dues(
    session: SessionDep,
    search: str | None = None,
) -> Any:
    """
    Get list of members with outstanding dues.
    """
    # Fetch all active dues
    active_dues = session.exec(select(Due).where(Due.is_active == True)).all()
    if not active_dues:
        return []

    # Get members who have not paid for any active due
    # This is a join-based approach to find members with missing payments for active dues
    statement = select(User)
    
    if search:
        statement = statement.where(or_(
            User.full_name.ilike(f"%{search}%"),
            User.email.ilike(f"%{search}%")
        ))
        
    users = session.exec(statement.limit(100)).all()
    
    data = []
    for user in users:
        # For each user, find which active dues they haven't paid
        for due in active_dues:
            payment = session.exec(
                select(Payment).where(
                    Payment.user_id == user.id,
                    Payment.status == "completed",
                    # In a real app, we'd have a DueID in Payment. For now, we check description or amount match
                    # or just assume they haven't paid if they don't have enough payments.
                )
            ).first()
            
            if not payment:
                overdue_delta = datetime.now(timezone.utc) - due.due_date.replace(tzinfo=timezone.utc)
                overdue_days = max(0, overdue_delta.days)
                
                data.append({
                    "id": str(user.id),
                    "member": user.full_name or user.email,
                    "email": user.email,
                    "type": due.title,
                    "amount": f"₦{float(due.amount):,.0f}",
                    "dueDate": due.due_date.strftime("%Y-%m-%d"),
                    "overdue": f"{overdue_days} days"
                })
                # Break after first outstanding due to avoid duplicate user rows in simple view
                break
        
    return data

@router.post("/record-payment")
async def record_offline_payment(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    data: RecordPaymentRequest
) -> Any:
    """
    Manually record an offline payment.
    """
    import json
    logger.error(f"INCOMING RECORD PAYMENT PAYLOAD: {data.model_dump_json()}")
    
    # 1. Ensure user has permission
    from app.utils.permissions import user_has_permission
    if not user_has_permission(session, current_user, "payment:manage"):
        raise HTTPException(
            status_code=403,
            detail="Action Restricted: You do not have the required permission to record payments."
        )

    # 2. Try to get user_id from the memberId (which might be an email or UUID)
    user_id = None
    try:
        user_id_obj = uuid.UUID(data.memberId)
        user = session.get(User, user_id_obj)
        if user:
            user_id = user.id
    except ValueError:
        pass
        
    if not user_id:
        # Fallback to email search or manual input
        user = session.exec(select(User).where(User.email == data.memberId)).first()
        if not user:
            # If the admin entered 'manual-entry', we need to reject cleanly
            if data.memberId == 'manual-entry':
                raise HTTPException(status_code=400, detail="Please select a valid member to record payment.")
            raise HTTPException(status_code=404, detail="Member not found")
        user_id = user.id

    new_payment = Payment(
        user_id=user_id,
        amount=Decimal(str(data.amount)),
        status="completed",
        transaction_reference=f"OFF-{uuid.uuid4().hex[:10].upper()}",
        payment_method=data.paymentMethod,
        description=data.description or f"Manual recording of {data.category}",
        created_at=datetime.fromisoformat(data.date).replace(tzinfo=timezone.utc) if data.date else datetime.now(timezone.utc)
    )
    
    session.add(new_payment)
    session.commit()
    session.refresh(new_payment)
    
    # Notify other Admins
    try:
        from app.utils.notifications import notify_admins
        notify_admins(
            session=session,
            title="Offline Payment Recorded",
            description=f"An offline payment of ₦{data.amount:,.0f} for {user.full_name or user.email} was recorded by {current_user.full_name or current_user.email}.",
            notification_type="success",
            metadata={
                "payment_id": str(new_payment.id),
                "user_id": str(user.id),
                "recorded_by": str(current_user.id),
                "type": "offline_payment_recorded"
            }
        )
    except Exception as e:
        logger.error(f"Failed to notify admins of offline payment recording: {e}")

    return {"success": True, "id": str(new_payment.id)}

@router.post("/send-reminder", dependencies=[Depends(RequiresPermission("user:manage"))])
def send_payment_reminder_bulk(
    *,
    session: SessionDep,
    data: dict
) -> Any:
    """
    Send payment reminders. Handles both single and bulk reminders.
    """
    from app.services.email_service import email_service
    
    user_ids = data.get("user_ids", [])
    
    statement = select(Payment).where(Payment.status == "pending")
    if user_ids:
        # Filter for specific users if provided
        uuid_list = [uuid.UUID(uid) if isinstance(uid, str) else uid for uid in user_ids]
        statement = statement.where(Payment.user_id.in_(uuid_list))
    
    from sqlalchemy.orm import selectinload
    pending_payments = session.exec(statement.options(selectinload(Payment.user))).all()
    
    sent_count = 0
    errors = []
    
    for payment in pending_payments:
        if payment.user and payment.user.email:
            try:
                email_service.send_payment_reminder(
                    email_to=payment.user.email,
                    username=payment.user.full_name or "FGCEOSA Member",
                    amount=float(payment.amount),
                    description=payment.description or "Outstanding Alumni Dues"
                )
                sent_count += 1
            except Exception as e:
                logger.error(f"Failed to send reminder to {payment.user.email}: {e}")
                errors.append(str(e))
    
    return {
        "success": True, 
        "sent_count": sent_count, 
        "failed_count": len(pending_payments) - sent_count,
        "message": f"Successfully sent {sent_count} reminders." if sent_count > 0 else "No reminders could be sent."
    }

@router.get("/export-report")
def export_annual_report(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    year: int = None
) -> Any:
    """
    Export financial report as CSV.
    """
    if not year:
        year = datetime.now().year
        
    start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    
    statement = select(User, Payment).join(Payment, User.id == Payment.user_id).where(
        Payment.created_at >= start_date,
        Payment.created_at <= end_date
    ).order_by(Payment.created_at)
    
    results = session.exec(statement).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Reference", "Member Name", "Email", "Amount", "Method", "Status", "Description"])
    
    for user, payment in results:
        writer.writerow([
            payment.created_at.strftime("%Y-%m-%d %H:%M"),
            payment.transaction_reference,
            user.full_name or "N/A",
            user.email,
            float(payment.amount),
            payment.payment_method or "Online",
            payment.status,
            payment.description or ""
        ])
    
    output.seek(0)
    
    filename = f"Annual_Financial_Report_{year}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
