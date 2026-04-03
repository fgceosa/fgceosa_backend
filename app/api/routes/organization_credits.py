from typing import Any
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, Body, Depends
from sqlmodel import select, and_

from app.api.deps import SessionDep, CurrentUser
from app.services import organization_service
from app.services.organization_credit_service import OrganizationCreditService
from app.schemas.organization_credits import (
    OrganizationCreditBalance,
    OrganizationCreditTransactionsList,
    OrganizationUsageSummary,
    WorkspaceLimitUpdate,
    MemberCreditAllocation
)
from app.services import roles_permissions_service
from app.notification_repository import create_notification
from app.models import Organization, User, OrganizationMember

router = APIRouter(tags=["organization-credits"])

@router.get("/organizations/{org_id}/credits/balance", response_model=OrganizationCreditBalance)
def get_organization_credit_balance(
    org_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Get the organization's credit balance and summary.
    """
    organization_service.check_organization_access(session, org_id, current_user)
    roles_permissions_service.require_permission(session, current_user.id, "credit:can_view_org_wallet")
    return OrganizationCreditService.get_balance(session, org_id)


@router.get("/organizations/{org_id}/credits/transactions", response_model=OrganizationCreditTransactionsList)
def list_organization_credit_transactions(
    org_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
) -> Any:
    """
    List organization credit transactions.
    """
    organization_service.check_organization_access(session, org_id, current_user)
    
    transactions, total = OrganizationCreditService.list_transactions(
        session, org_id, page, page_size
    )
    
    return OrganizationCreditTransactionsList(
        transactions=transactions,
        total=total,
        page=page,
        page_size=page_size
    )


@router.get("/organizations/{org_id}/credits/usage-summary", response_model=OrganizationUsageSummary)
def get_organization_usage_summary(
    org_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser,
    days: int = 30,
) -> Any:
    """
    Get usage breakdown by workspace for a specific period (default 30 days).
    """
    organization_service.check_organization_access(session, org_id, current_user)
    
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days)
    
    return OrganizationCreditService.get_usage_summary(session, org_id, start_date, end_date)


@router.put("/organizations/{org_id}/workspaces/{workspace_id}/limit")
def update_workspace_credit_limit(
    org_id: uuid.UUID,
    workspace_id: uuid.UUID,
    limit_update: WorkspaceLimitUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Update the monthly credit limit for a workspace.
    Requires org admin permissions.
    """
    organization_service.check_organization_access(
        session, org_id, current_user, required_permission="credit:can_manage_credit_rules"
    )
    
    # Verify workspace belongs to organization
    # (Implicitly checked by service but good to be sure or service handles it)
    
    updated_workspace = OrganizationCreditService.update_workspace_limit(
        session, workspace_id, limit_update.monthly_limit
    )
    
    return {"success": True, "monthly_limit": updated_workspace.monthly_credit_limit}


@router.post("/organizations/{org_id}/credits/allocate")
def allocate_credits(
    org_id: uuid.UUID,
    amount: float,
    description: str,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Manually allocate/deduct credits (Admin only).
    """
    organization_service.check_organization_access(session, org_id, current_user)
    roles_permissions_service.require_permission(session, current_user.id, "credit:can_top_up_org_wallet")
    
    from decimal import Decimal
    from app.email_utils import send_credit_allocation_email
    import logging
    
    logger = logging.getLogger(__name__)
    
    tx = OrganizationCreditService.process_transaction(
        session,
        org_id,
        Decimal(str(amount)),
        "manual_allocation" if amount > 0 else "manual_deduction",
        description,
        user_id=current_user.id
    )

    notified_admins = []
    # Notify organization admins if credits were added or deducted
    if amount != 0:
        org = session.get(Organization, org_id)
        if org:
            # Find all organization administrators to notify
            from sqlmodel import select
            from app.models import OrganizationMember, User
            
            admins_stmt = select(User).where(
                User.id.in_(
                    select(OrganizationMember.user_id).where(
                        OrganizationMember.organization_id == org.id,
                        OrganizationMember.role.in_(["org_super_admin", "org_admin"]),
                        OrganizationMember.status == "active"
                    )
                )
            )
            admins = session.exec(admins_stmt).all()
            
            # Fallback to owner if no active admins found
            if not admins and org.owner_id:
                owner = session.get(User, org.owner_id)
                if owner:
                    admins = [owner]
                    
            for admin in admins:
                try:
                    # Create in-app notification
                    action_type = "added" if amount > 0 else "deducted"
                    create_notification(
                        session=session,
                        user_id=admin.id,
                        title=f"Organization Credits {action_type.title()}! 🏦",
                        description=f"Administrative allocation: {int(abs(amount))} credits have been {action_type} to your organization '{org.name}'.",
                        type="credit_received" if amount > 0 else "credit_deducted",
                        metadata={
                            "org_id": str(org_id),
                            "amount": float(amount),
                            "admin_id": str(current_user.id),
                            "reason": description
                        },
                        commit=False  # Will commit later with email
                    )
                    notified_admins.append(admin.email)
                    logger.info(f"In-app notification created for {admin.email}")
                    
                    # Send email notification
                    try:
                        send_credit_allocation_email(
                            email_to=admin.email,
                            username=admin.full_name or admin.email,
                            amount=int(abs(amount)),
                            reason=description,
                            new_balance=float(tx.balance_after)
                        )
                        logger.info(f"Email sent to {admin.email} for credit allocation")
                    except Exception as email_err:
                        logger.error(f"Failed to send email to {admin.email}: {email_err}")
                        # Email failure doesn't block allocation, but log it
                        
                except Exception as e:
                    logger.error(f"Failed to create notification/email for {admin.email}: {e}")
            
            # Commit all notifications
            session.commit()
    
    return {
        "success": True, 
        "new_balance": float(tx.balance_after),
        "notified_admins": notified_admins,
        "notification_count": len(notified_admins)
    }


@router.post("/organizations/{org_id}/members/allocate")
def allocate_credits_to_member(
    org_id: uuid.UUID,
    allocation: MemberCreditAllocation,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Allocate credits from the organization wallet to a specific member.
    """
    # 1. Check if current user has permission in the organization
    organization_service.check_organization_access(
        session, org_id, current_user, required_permission="credit:can_share_credit"
    )
    
    # 2. Get organization
    org = organization_service.get_organization_by_id(session, org_id)
    
    # 3. Resolve recipient and verify they belong to the organization
    recipient = session.get(User, allocation.user_id)
    if not recipient:
        raise HTTPException(status_code=404, detail="Recipient user not found")
        
    member_check = session.exec(
        select(OrganizationMember).where(
            and_(
                OrganizationMember.organization_id == org_id,
                OrganizationMember.user_id == allocation.user_id
            )
        )
    ).first()
    
    if not member_check:
        raise HTTPException(
            status_code=400, 
            detail="User is not a member of this organization"
        )
    
    # 4. Perform the transfer using OrganizationCreditService to ensure it's logged
    from app.email_utils import send_credit_allocation_email
    import logging
    
    logger = logging.getLogger(__name__)
    amount = allocation.amount
    description = allocation.message or f"Credit allocation from organization '{org.name}'"
    
    OrganizationCreditService.share_credits(
        session=session,
        org_id=org_id,
        member_id=recipient.id,
        amount=amount,
        admin_id=current_user.id,
        description=description,
        commit=False # We still have notifications to add
    )
    
    # 5. Create in-app notification for the recipient
    create_notification(
        session=session,
        user_id=recipient.id,
        title="Credits Received! 🎉",
        description=f"You received {int(amount)} credits from organization: {org.name}.",
        type="credit_received",
        metadata={
            "org_id": str(org_id),
            "amount": float(amount),
            "sender_id": str(current_user.id),
            "message": allocation.message
        },
        commit=False
    )
    
    # 6. Send email notification to recipient
    try:
        send_credit_allocation_email(
            email_to=recipient.email,
            username=recipient.full_name or recipient.email,
            amount=int(amount),
            reason=description,
            new_balance=float(recipient.credits + amount)
        )
        logger.info(f"Email sent to {recipient.email} for credit allocation")
    except Exception as email_err:
        logger.error(f"Failed to send email to {recipient.email}: {email_err}")
    
    session.commit()
    
    return {"success": True, "new_member_balance": float(recipient.credits + amount)}
