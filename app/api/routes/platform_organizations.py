import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select, func, and_, desc, or_, String, delete

from app.api.deps import SessionDep, CurrentUser, RequiresPermission
from app.models import Organization, OrganizationMember, User, Workspace, APIRequest, Project, AuditLog, OrganizationCreateWithAdmin, WalletOwnerType, WalletTransactionType
from app.services.wallet_service import WalletService
from app.services.email_service import email_service
from app.services.organization_credit_service import OrganizationCreditService
from app.notification_repository import create_notification
from app import user_repository
from app.utils import generate_password_reset_token
from app.core.config import settings
import logging
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/organizations", tags=["platform-organizations"])

class OrganizationCreditAllocation(BaseModel):
    adjustment_type: str = Field(..., pattern="^(add|deduct)$")
    amount: float = Field(..., gt=0)
    reason_category: str
    reason_description: str = Field("")
    notify_organization: bool = True

@router.post("/create-with-admin", dependencies=[Depends(RequiresPermission("platform:manage_organizations"))])
def create_organization_with_admin(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    org_in: OrganizationCreateWithAdmin
) -> Any:
    """
    Create a new organization and its initial admin user suitable for offline onboarding.
    Sends a setup email to the admin with a secure link to set their password.
    """
    import secrets
    from datetime import datetime
    
    # 1. Handle User (Find or Create)
    user = user_repository.get_user_by_email(session=session, email=org_in.admin_email)
    
    is_new_user = False
    if not user:
        # Create new user
        # Generate a hard random password initially (they will reset it via link)
        temp_password = secrets.token_urlsafe(20) 
        
        from app.models import UserCreate
        user_create = UserCreate(
            email=org_in.admin_email,
            password=temp_password,
            full_name=org_in.admin_name,
            account_type="individual",  # Use "individual" to prevent auto org creation
            accept_terms=True # Implicitly accepted by Admin creation
        )
        # Create user WITHOUT auto-creating organization (we'll do it manually below)
        user = user_repository.create_user(
            session=session, 
            user_create=user_create, 
            account_type="individual",  # Prevent auto org creation
            organization_name=None,  # No org name to prevent auto creation
            accept_terms=True
        )
        is_new_user = True
    else:
        # Check if user already owns an organization
        existing_org = session.exec(
            select(Organization).where(Organization.owner_id == user.id)
        ).first()
        
        if existing_org:
            raise HTTPException(
                status_code=400,
                detail=f"User {org_in.admin_email} already owns an organization: {existing_org.name}. Each user can only own one organization."
            )
    
    # 2. Create Organization (manually, to avoid duplication)
    org = Organization(
        name=org_in.name,
        description=org_in.description,
        owner_id=user.id,
        is_active=True
    )
    session.add(org)
    session.flush() # Get ID
    
    # 3. Add User as Org Super Admin
    member = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="org_super_admin",
        status="active",
        joined_at=datetime.now(timezone.utc)
    )
    session.add(member)
    
    # Update user account_type to 'organization' now that org is created
    if is_new_user:
        user.account_type = "organization"
        user.organization_name = org.name
        session.add(user)
    
    # Ensure user has org_super_admin role
    from app.models import Role, UserRole
    org_super_admin_role = session.exec(select(Role).where(Role.name == "org_super_admin")).first()
    if org_super_admin_role:
        # Check if user already has this role
        existing_user_role = session.exec(
            select(UserRole).where(
                UserRole.user_id == user.id,
                UserRole.role_id == org_super_admin_role.id
            )
        ).first()
        if not existing_user_role:
            user_role = UserRole(user_id=user.id, role_id=org_super_admin_role.id)
            session.add(user_role)
    
    
    # 4. Send Setup Email
    if settings.emails_enabled:
        # Generate password reset token
        token = generate_password_reset_token(email=user.email)
        setup_link = f"{settings.FRONTEND_HOST}/setup-account?token={token}"
        
        email_service.send_organization_setup_email(
            email_to=user.email,
            username=user.full_name,
            org_name=org.name,
            setup_link=setup_link
        )
            
    # Audit Log
    audit = AuditLog(
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        action="ORGANIZATION_CREATED",
        target_id=str(org.id),
        target_type="Organization",
        meta_data={
            "org_name": org.name,
            "admin_email": user.email,
            "is_new_user": is_new_user
        }
    )
    session.add(audit)
    
    session.commit()
    session.refresh(org)
    
    return org


@router.get("/analytics", dependencies=[Depends(RequiresPermission("platform:view_audit_logs"))])
def get_organizations_analytics(session: SessionDep) -> Any:
    """
    Get platform-wide organization analytics.
    """
    total_orgs = session.exec(select(func.count(Organization.id))).one()
    
    # Active Orgs (is_active is True)
    active_orgs = session.exec(select(func.count(Organization.id)).where(Organization.is_active == True)).one()
    
    # Over-limit Orgs (credits < 0)
    over_limit_orgs = session.exec(select(func.count(Organization.id)).where(Organization.credits_balance < 0)).one()
    
    # Suspended Orgs (is_active is False)
    suspended_orgs = session.exec(select(func.count(Organization.id)).where(Organization.is_active == False)).one()

    return {
        "totalOrganizations": total_orgs,
        "activeOrganizations": active_orgs,
        "overLimitOrganizations": over_limit_orgs,
        "suspendedOrganizations": suspended_orgs,
    }

@router.get("", dependencies=[Depends(RequiresPermission("platform:view_audit_logs"))])
def list_all_organizations(
    session: SessionDep,
    page: int = 1,
    page_size: int = 100,
    search: str | None = None,
    status: str | None = None,
) -> Any:
    """
    List all organizations with basic stats using optimized queries.
    """
    statement = select(Organization).join(User, Organization.owner_id == User.id)
    
    if search:
        statement = statement.where(
            or_(
                Organization.name.ilike(f"%{search}%"),
                Organization.id.cast(String).ilike(f"%{search}%"),
                User.full_name.ilike(f"%{search}%"),
                User.email.ilike(f"%{search}%")
            )
        )
    
    if status:
        if status == "active":
            statement = statement.where(Organization.is_active == True)
        elif status == "suspended":
            statement = statement.where(Organization.is_active == False)

    # Count total
    count_statement = select(func.count()).select_from(statement.subquery())
    total = session.exec(count_statement).one()

    # Pagination
    statement = statement.order_by(desc(Organization.created_at)).offset((page - 1) * page_size).limit(page_size)
    results = session.exec(statement).all()
    # If using select(Organization) with a join, results will be a list of Organization objects
    # If it was select(Organization, User), it would be a list of tuples.
    # Current call select(Organization) returns only Organization objects.
    
    # Optimized fetching of counts and usage in a structured way (could be optimized further with JSON_AGG or similar if using Raw SQL, but for now we'll do batches)
    result_list = []
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    
    for org in results:
        # Get owner info from relationship or separate query if not eager loaded
        owner = session.get(User, org.owner_id)
        
        # Get counts via subqueries or separate optimized lookups
        workspaces_count = session.exec(select(func.count(Workspace.id)).where(Workspace.organization_id == org.id)).one()
        members_count = session.exec(select(func.count(OrganizationMember.id)).where(OrganizationMember.organization_id == org.id)).one()
        
        # Monthly Usage (last 30 days)
        usage = session.exec(
            select(func.sum(APIRequest.cost))
            .join(Project, APIRequest.project_id == Project.id)
            .where(Project.org_id == org.id, APIRequest.created_at >= thirty_days_ago)
        ).one() or 0

        # Last Activity
        last_request = session.exec(
            select(APIRequest.created_at)
            .join(Project, APIRequest.project_id == Project.id)
            .where(Project.org_id == org.id)
            .order_by(APIRequest.created_at.desc())
        ).first()

        result_list.append({
            "id": org.id,
            "name": org.name,
            "owner": owner.full_name if owner else "Unknown",
            "ownerEmail": owner.email if owner else "Unknown",
            "status": "active" if org.is_active else "suspended",
            "workspaces": workspaces_count,
            "members": members_count,
            "monthlyUsage": float(usage),
            "credits": float(org.credits_balance),
            "lastActivity": last_request,
            "createdAt": org.created_at
        })

    return {
        "list": result_list,
        "total": total
    }

@router.get("/{org_id}", dependencies=[Depends(RequiresPermission("platform:view_audit_logs"))])
def get_organization_detail(org_id: uuid.UUID, session: SessionDep) -> Any:
    """
    Get detailed information about an organization including usage trends and workspace ranking.
    """
    org = session.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    owner = session.get(User, org.owner_id)
    
    # Billing summary
    thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
    usage = session.exec(
        select(func.sum(APIRequest.cost))
        .join(Project, APIRequest.project_id == Project.id)
        .where(Project.org_id == org.id, APIRequest.created_at >= thirty_days_ago)
    ).one() or 0

    # Usage Trends (Last 7 days aggregated by day)
    seven_days_ago = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7)
    trends_query = (
        select(
            func.date(APIRequest.created_at).label("date"),
            func.sum(APIRequest.cost).label("usage")
        )
        .join(Project, APIRequest.project_id == Project.id)
        .where(Project.org_id == org.id, APIRequest.created_at >= seven_days_ago)
        .group_by(func.date(APIRequest.created_at))
        .order_by(func.date(APIRequest.created_at))
    )
    trends_results = session.exec(trends_query).all()
    usage_trends = [{"date": str(r.date), "usage": float(r.usage)} for r in trends_results]

    # Top Workspaces by Usage (Last 30 days)
    top_workspaces_query = (
        select(
            Project.name,
            func.sum(APIRequest.cost).label("usage")
        )
        .join(APIRequest, APIRequest.project_id == Project.id)
        .where(Project.org_id == org.id, APIRequest.created_at >= thirty_days_ago)
        .group_by(Project.name)
        .order_by(desc("usage"))
        .limit(5)
    )
    top_workspaces_results = session.exec(top_workspaces_query).all()
    top_workspaces = [{"name": r.name, "usage": float(r.usage)} for r in top_workspaces_results]

    return {
        "profile": {
            "id": org.id,
            "name": org.name,
            "owner": owner.full_name if owner else "Unknown",
            "email": owner.email if owner else "Unknown",
            "status": "active" if org.is_active else "suspended",
            "createdAt": org.created_at,
            "description": org.description
        },
        "billing": {
            "credits": float(org.credits_balance),
            "monthlyUsage": float(usage),
            "overages": 0.0 # Logic for overages depends on plan
        },
        "activity": {
             "usageTrends": usage_trends,
             "topWorkspaces": top_workspaces
        }
    }

@router.patch("/{org_id}", dependencies=[Depends(RequiresPermission("platform:view_audit_logs"))])
def update_organization_admin(
    org_id: uuid.UUID, 
    update_data: dict, 
    session: SessionDep
) -> Any:
    """
    Administrative update of an organization.
    """
    org = session.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    if "is_active" in update_data:
        org.is_active = update_data["is_active"]
    
    if "name" in update_data:
        org.name = update_data["name"]

    if "description" in update_data:
        org.description = update_data["description"]

    session.add(org)
    session.commit()
    session.refresh(org)
    
    return org

@router.delete("/{org_id}", dependencies=[Depends(RequiresPermission("platform:view_audit_logs"))])
def delete_organization(
    org_id: uuid.UUID,
    session: SessionDep,
    current_user: CurrentUser
) -> Any:
    """
    Delete an organization and all its related data.
    This is a destructive action that will remove:
    - Organization members
    - Workspaces
    - Projects
    - All associated data
    """
    org = session.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    org_name = org.name
    
    # Delete all organization members
    session.exec(
        select(OrganizationMember).where(OrganizationMember.organization_id == org_id)
    ).all()
    session.exec(
        delete(OrganizationMember).where(OrganizationMember.organization_id == org_id)
    )
    
    # Delete all workspaces (this should cascade to projects if configured)
    session.exec(
        delete(Workspace).where(Workspace.organization_id == org_id)
    )
    
    # Delete all projects directly associated with the org
    session.exec(
        delete(Project).where(Project.org_id == org_id)
    )
    
    # Create audit log before deletion
    audit = AuditLog(
        actor_id=current_user.id,
        actor_name=current_user.full_name,
        action="ORGANIZATION_DELETED",
        target_id=str(org_id),
        target_type="Organization",
        severity="high",
        meta_data={
            "org_name": org_name,
            "deleted_by": current_user.email
        }
    )
    session.add(audit)
    
    # Delete the organization
    session.delete(org)
    session.commit()
    
    return {"message": f"Organization '{org_name}' deleted successfully"}

@router.post("/{org_id}/credits/allocate", dependencies=[Depends(RequiresPermission("platform:manage_organizations"))])
def allocate_organization_credits(
    org_id: uuid.UUID,
    data: OrganizationCreditAllocation,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Allocate organization credits (add or remove) with full audit logging.
    """
    org = session.get(Organization, org_id)
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    previous_balance = org.credits_balance
    adjustment_amount = Decimal(str(data.amount))
    signed_amount = adjustment_amount if data.adjustment_type == "add" else -adjustment_amount
    adjustment_type = "manual_allocation" if data.adjustment_type == "add" else "manual_deduction"
    description = f"{data.reason_category}: {data.reason_description}" if data.reason_description else data.reason_category
    
    # Step 1: Apply the wallet transaction (this syncs org.credits_balance via _sync_cached_balance)
    from app.models import WalletOwnerType, WalletTransactionType
    wallet = WalletService.get_or_create_wallet(session, org_id, WalletOwnerType.ORGANIZATION)
    WalletService.add_transaction(
        session=session,
        wallet_id=wallet.id,
        transaction_type=WalletTransactionType.TOP_UP if data.adjustment_type == "add" else WalletTransactionType.ADJUSTMENT,
        amount=signed_amount,
        credit=adjustment_amount if data.adjustment_type == "add" else Decimal("0.0000"),
        debit=adjustment_amount if data.adjustment_type == "deduct" else Decimal("0.0000"),
        description=description,
        created_by=current_user.id,
        source="platform_admin_allocation"
    )
    
    # Step 2: Log in the Organization credit transaction history
    from app.models import OrganizationCreditTransaction
    session.flush()  # flush so wallet balance is synced before we read it
    session.refresh(org)  # get updated credits_balance
    org_tx = OrganizationCreditTransaction(
        organization_id=org_id,
        amount=signed_amount,
        balance_after=org.credits_balance,
        transaction_type=adjustment_type,
        description=description,
        performed_by=current_user.id
    )
    session.add(org_tx)
    
    try:
        # Step 3: Create Audit Log
        audit_entry = AuditLog(
            actor_id=current_user.id,
            actor_name=current_user.full_name or current_user.email,
            actor_role="Platform Super Admin",
            action="CREDITS_ALLOCATED",
            action_category="financial",
            target_id=str(org.id),
            target_type="Organization",
            organization_id=org.id,
            severity="medium",
            status="success",
            meta_data={
                "adjustment_type": data.adjustment_type,
                "amount": float(adjustment_amount),
                "previous_balance": float(previous_balance),
                "new_balance": float(org.credits_balance),
                "reason_category": data.reason_category,
                "reason_description": data.reason_description,
                "notify_organization": data.notify_organization
            }
        )
        session.add(audit_entry)
        
        # Single atomic commit for wallet tx, org tx history, and audit log
        session.commit()
    except Exception as commit_err:
        session.rollback()
        logger.error(f"Failed to commit organization credit allocation: {commit_err}")
        raise HTTPException(
            status_code=500,
            detail=f"Database commit failed: {str(commit_err)}"
        )
    
    session.refresh(org)
    
    # Implement notification logic if data.notify_organization is True
    if data.notify_organization:
        # Find all organization administrators to notify
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
            # Send in-app notification
            if data.adjustment_type == "add":
                try:
                    create_notification(
                        session=session,
                        user_id=admin.id,
                        title=f"Credits Allocated to {org.name}! 🎉",
                        description=f"Administrative allocation: {int(adjustment_amount)} credits have been added to your organization wallet.",
                        type="credit_received",
                        metadata={
                            "admin_id": str(current_user.id),
                            "amount": float(adjustment_amount),
                            "reason": data.reason_description or data.reason_category,
                            "organization_id": str(org.id),
                            "organization_name": org.name
                        },
                        commit=False # Batch commit later
                    )
                except Exception as e:
                    logger.error(f"Failed to prepare notification for {admin.email}: {e}")
            
            # Send email notification
            try:
                email_service.send_credit_adjustment_notification(
                    email_to=admin.email,
                    org_name=org.name,
                    adjustment_type=data.adjustment_type,
                    amount=float(adjustment_amount),
                    reason=f"{data.reason_category}: {data.reason_description}",
                    new_balance=float(org.credits_balance)
                )
            except Exception as e:
                logger.error(f"Failed to send credit adjustment email to {admin.email}: {e}")
        
        # Commit all notifications
        try:
            session.commit()
        except Exception as e:
            logger.error(f"Failed to commit notifications: {e}")
            session.rollback()
    
    return {"id": org.id, "newBalance": float(org.credits_balance)}
