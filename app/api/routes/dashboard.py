import logging
from typing import Any
from decimal import Decimal
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlmodel import select, func

from app.api.deps import (
    CurrentUser,
    SessionDep,
    RequiresPermission,
)
from app.models import (
    User,
    Payment,
    Announcement,
    Event,
    Due,
    EventRegistration,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/admin/stats", dependencies=[Depends(RequiresPermission("user:manage"))])
def get_admin_stats(session: SessionDep) -> Any:
    """
    Get high-level stats for the Admin Dashboard.
    """
    total_members = session.exec(select(func.count()).select_from(User)).one()
    active_members = session.exec(select(func.count()).select_from(User).where(User.status == "active")).one()
    
    total_dues = session.exec(
        select(func.sum(Payment.amount)).where(Payment.status == "completed")
    ).one() or Decimal("0.00")
    
    pending_payments = session.exec(
        select(func.count()).select_from(Payment).where(Payment.status == "pending")
    ).one()
    active_events = session.exec(select(func.count()).select_from(Event).where(Event.status == "Upcoming")).one()
    recent_announcements_count = session.exec(select(func.count()).select_from(Announcement).where(Announcement.is_active == True)).one()
    
    # 1. Recent Transactions (Completed)
    from sqlalchemy.orm import selectinload
    recent_transactions = session.exec(
        select(Payment).options(selectinload(Payment.user)).where(Payment.status == "completed").order_by(Payment.created_at.desc()).limit(5)
    ).all()
    
    rt_list = []
    for p in recent_transactions:
        rt_list.append({
            "name": p.user.full_name or f"{p.user.first_name} {p.user.last_name}" if p.user else "Unknown User",
            "date": p.created_at,
            "amount": float(p.amount),
            "status": p.status
        })

    # 2. Recent Announcements
    recent_announcements = session.exec(
        select(Announcement).where(Announcement.is_active == True).order_by(Announcement.created_at.desc()).limit(4)
    ).all()
    
    ra_list = []
    for a in recent_announcements:
        ra_list.append({
            "title": a.title,
            "date": a.created_at,
            "type": a.category,
            "priority": a.priority
        })
        
    # 3. Unpaid Followups (Pending Payments)
    unpaid_payments = session.exec(
        select(Payment).options(selectinload(Payment.user)).where(Payment.status == "pending").order_by(Payment.created_at.desc()).limit(5)
    ).all()
    
    up_list = []
    for p in unpaid_payments:
        if p.user:
            up_list.append({
                "id": str(p.user.id),
                "name": p.user.full_name or f"{p.user.first_name} {p.user.last_name}",
                "amount": float(p.amount)
            })

    return {
        "totalMembers": total_members,
        "activeMembers": active_members,
        "totalDuesCollected": float(total_dues),
        "pendingPaymentsCount": pending_payments,
        "activeEvents": active_events,
        "recentAnnouncementsCount": recent_announcements_count,
        "currency": "NGN",
        "recentTransactions": rt_list,
        "announcements": ra_list,
        "unpaidFollowups": up_list
    }

@router.get("/member/summary")
def get_member_summary(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Get detailed summary for the Member Dashboard.
    """
    # 1. Financial Stats
    total_paid = session.exec(
        select(func.sum(Payment.amount))
        .where(Payment.user_id == current_user.id, Payment.status == "completed")
    ).one() or Decimal("0.00")
    
    # Last Payment Info
    last_payment = session.exec(
        select(Payment)
        .where(Payment.user_id == current_user.id, Payment.status == "completed")
        .order_by(Payment.created_at.desc())
    ).first()

    # Calculate Outstanding Dues
    active_dues = session.exec(select(Due).where(Due.is_active == True)).all()
    completed_payments = session.exec(
        select(Payment).where(Payment.user_id == current_user.id, Payment.status == "completed")
    ).all()
    
    paid_dues_count = len(completed_payments)
    active_dues_sorted = sorted(active_dues, key=lambda x: x.due_date, reverse=True)
    
    unpaid_dues = []
    outstanding_amount = Decimal("0.00")
    outstanding_desc = None
    outstanding_due_date = None

    if len(active_dues_sorted) > paid_dues_count:
        num_unpaid = len(active_dues_sorted) - paid_dues_count
        unpaid_dues = active_dues_sorted[:num_unpaid]
        outstanding_amount = sum([d.amount for d in unpaid_dues])
        outstanding_desc = unpaid_dues[0].title
        outstanding_due_date = unpaid_dues[0].due_date.strftime("%b %d, %Y")
    else:
        outstanding_amount = Decimal("0.00")
        outstanding_desc = None
        outstanding_due_date = None
    
    # 2. Upcoming Events
    now = datetime.now(timezone.utc)
    upcoming_events = session.exec(
        select(Event)
        .where(Event.date >= now)
        .order_by(Event.created_at.desc())
        .limit(3)
    ).all()
    
    events_list = []
    for e in upcoming_events:
        # Check if user is registered for this event
        registration = session.exec(
            select(EventRegistration)
            .where(EventRegistration.event_id == e.id, EventRegistration.user_id == current_user.id)
        ).first()
        is_registered = registration is not None

        events_list.append({
            "id": str(e.id),
            "title": e.title,
            "date": e.date.strftime("%b %d, %Y") if e.date else "TBD",
            "location": e.location or "Virtual",
            "featured": e.status == "Upcoming", # Use status as fallback for featured
            "image": e.image,
            "is_registered": is_registered
        })

    # 3. Recent Payments
    recent_payments = session.exec(
        select(Payment)
        .where(Payment.user_id == current_user.id)
        .order_by(Payment.created_at.desc())
        .limit(4)
    ).all()
    
    payments_list = []
    for p in recent_payments:
        payments_list.append({
            "id": str(p.id),
            "title": p.description or "General Payment",
            "ref": p.transaction_reference or f"REF-{str(p.id)[:8]}",
            "date": p.created_at.strftime("%b %d, %Y"),
            "amount": float(p.amount),
            "status": "Paid" if p.status == "completed" else p.status.capitalize(),
            "type": "subscription" if "dues" in (p.description or "").lower() else "event" if "event" in (p.description or "").lower() else "donation",
            "method": p.payment_method
        })

    # 4. Announcements
    announcements = session.exec(
        select(Announcement)
        .where(Announcement.is_active == True)
        .order_by(Announcement.created_at.desc())
        .limit(3)
    ).all()
    
    ann_list = []
    for a in announcements:
        # Calculate 'time ago' or just format date
        ann_list.append({
            "id": str(a.id),
            "title": a.title,
            "content": a.content,
            "date": a.created_at.strftime("%b %d, %Y"),
            "type": a.category or "General",
            "color": "emerald" if a.category == "Event" else "blue" if a.category == "System" else "red",
            "image": a.image,
            "views": getattr(a, 'views', 0)
        })

    return {
        "membershipStatus": current_user.status.capitalize() if current_user.status else "Active",
        "verified": current_user.is_verified,
        "duesStatus": "overdue" if outstanding_amount > 0 else "paid",
        "totalPaid": float(total_paid),
        "lastPaymentAmount": float(last_payment.amount) if last_payment else 0,
        "lastPaymentDate": last_payment.created_at.strftime("%b %d, %Y") if last_payment else "No payments",
        "upcomingEventsCount": len(upcoming_events),
        "outstandingAmount": float(outstanding_amount),
        "outstandingTitle": outstanding_desc or "No Dues Found",
        "outstandingDueDate": outstanding_due_date or "Up to date",
        "unpaidDues": [
            {
                "id": str(d.id), 
                "title": d.title, 
                "amount": float(d.amount),
                "description": d.description,
                "dueDate": d.due_date.strftime("%b %d, %Y") if d.due_date else "N/A"
            } 
            for d in unpaid_dues
        ],
        "upcomingEvents": events_list,
        "paymentHistory": payments_list,
        "announcements": ann_list,
        "membershipId": current_user.membership_id
    }
