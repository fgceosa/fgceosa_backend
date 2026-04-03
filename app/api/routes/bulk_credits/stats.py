import uuid
from fastapi import APIRouter
from typing import Any
from sqlmodel import select, func
from app.api.deps import SessionDep, CurrentUser
from app.models import CreditTransaction, OrganizationCreditTransaction, Campaign, OrganizationMember
from app.credit_repository import get_user_credit_balance
from app.core.config import settings

router = APIRouter()

@router.get("/stats")
async def get_bulk_credits_stats(
    session: SessionDep,
    current_user: CurrentUser,
    organization_id: uuid.UUID | None = None,
) -> Any:
    """
    Get statistics for bulk credits dashboard
    """
    # Determine target organization if any
    target_org_id = organization_id
    if not target_org_id:
        org_member = session.exec(
            select(OrganizationMember).where(
                OrganizationMember.user_id == current_user.id,
                OrganizationMember.role.in_(["org_super_admin", "org_admin"]),
                OrganizationMember.status == "active"
            )
        ).first()
        if org_member:
            target_org_id = org_member.organization_id

    # Initialize statistics
    sent_credits_amount = 0.0
    total_users = 0
    active_events = 0
    campaign_filter = (Campaign.user_id == current_user.id)

    # Context verification and balance check
    is_org_context = False
    if target_org_id:
        org_access = session.exec(
            select(OrganizationMember).where(
                OrganizationMember.organization_id == target_org_id,
                OrganizationMember.user_id == current_user.id,
                OrganizationMember.role.in_(["org_super_admin", "org_admin"]),
                OrganizationMember.status == "active"
            )
        ).first()
        
        if org_access:
            is_org_context = True
            credit_balance = get_user_credit_balance(session=session, user_id=current_user.id, organization_id=target_org_id)
            campaign_filter = (Campaign.organization_id == target_org_id)
        else:
            credit_balance = get_user_credit_balance(session=session, user_id=current_user.id)
    else:
        credit_balance = get_user_credit_balance(session=session, user_id=current_user.id)

    naira_balance = float(credit_balance) * settings.NAIRA_TO_CREDIT_RATE

    # 2. Calculate Sent Credits and Total Users based on context
    if is_org_context:
        # Organization Stats from OrganizationCreditTransaction
        sent_result = session.exec(
            select(func.coalesce(func.sum(OrganizationCreditTransaction.amount), 0)).where(
                OrganizationCreditTransaction.organization_id == target_org_id,
                OrganizationCreditTransaction.transaction_type == 'allocation'
            )
        ).one()
        # Sum is negative for allocations (debit)
        sent_credits_amount = abs(float(sent_result)) * settings.NAIRA_TO_CREDIT_RATE
        
        total_users_result = session.exec(
            select(func.count(OrganizationCreditTransaction.id)).where(
                OrganizationCreditTransaction.organization_id == target_org_id,
                OrganizationCreditTransaction.transaction_type == 'allocation'
            )
        ).one()
        total_users = total_users_result or 0
    else:
        # User Stats from CreditTransaction
        sent_result = session.exec(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.user_id == current_user.id,
                CreditTransaction.transaction_type.in_(['transfer_out', 'bulk_transfer_out', 'allocation_out'])
            )
        ).one()
        sent_credits_amount = abs(float(sent_result)) * settings.NAIRA_TO_CREDIT_RATE
        
        total_users_result = session.exec(
            select(func.count(CreditTransaction.id)).where(
                CreditTransaction.user_id == current_user.id,
                CreditTransaction.transaction_type.in_(['transfer_out', 'bulk_transfer_out', 'allocation_out'])
            )
        ).one()
        total_users = total_users_result or 0

    # 3. Active Events (Programs)
    try:
        active_events_result = session.exec(
            select(func.count(Campaign.id)).where(
                campaign_filter,
                Campaign.status == 'active'
            )
        ).one()
        active_events = active_events_result or 0
    except Exception:
        pass

    return {
        "totalBalance": naira_balance,
        "sentCredits": sent_credits_amount,
        "totalUsers": total_users,
        "activeEvents": active_events
    }
