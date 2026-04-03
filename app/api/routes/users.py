import uuid
import os
import shutil
from typing import Any
from decimal import Decimal
import logging
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from sqlmodel import delete, func, select, update, desc
from sqlalchemy.orm import selectinload

from app import user_repository
from app.api.deps import (
    CopilotSessionDep,
    CurrentUser,
    SessionDep,
    RequiresPermission,
    RequiresRole,
)
from app.core.config import settings
from app.core.security import get_password_hash, verify_password
from app.credit_repository import get_user_credit_balance
from app.models import (
    APIRequest,
    Message,
    Project,
    UpdatePassword,
    User,
    UserCreate,
    UserPublic,
    UserRegister,
    UsersPublic,
    UserUpdate,
    UserIdentityRoleUpdate,
    UserUpdateMe,
    UserRole,
    Organization,
    OrganizationMember,
    APIKey,
    CreditTransaction,
    AIChat,
    TopUp,
    Notification,
    Campaign,
    CreditTransfer,
    Workspace,
    WorkspaceMember,
    WorkspaceProject,
    OAuthConnection,
    AIChatMessage,
    WorkspaceProjectMember,
    Wallet,
    WalletTransaction,
    WalletOwnerType,
    WalletTransactionType,
    WorkspaceCreditTransaction,
)
from app.copilot.models import Copilot
from app.utils import (
    send_new_account_email,
    send_email_verification,
)
from app.notification_repository import create_notification
from pydantic import BaseModel, Field

router = APIRouter(prefix="/users", tags=["users"])

class UserCreditAllocation(BaseModel):
    adjustment_type: str = Field(..., pattern="^(add|deduct)$")
    amount: float = Field(..., gt=0)
    reason_category: str
    reason_description: str = Field("")
    notify_user: bool = True


@router.get(
    "/analytics",
    dependencies=[Depends(RequiresPermission("platform:view_audit_logs"))],
)
def get_users_analytics(session: SessionDep) -> Any:
    """
    Get users analytics with real database values and growth trends.
    """
    from datetime import timedelta
    
    now = datetime.now(timezone.utc)
    thirty_days_ago = now - timedelta(days=30)

    # 1. Total Users & Trend
    total_users = session.exec(select(func.count()).select_from(User)).one()
    total_users_prev = session.exec(select(func.count()).select_from(User).where(User.created_at <= thirty_days_ago)).one()

    # 2. Active Users & Trend (Based on creation time of currently active users)
    active_users = session.exec(select(func.count()).select_from(User).where(User.status == "active")).one()
    active_users_prev = session.exec(select(func.count()).select_from(User).where(User.status == "active", User.created_at <= thirty_days_ago)).one()

    # 3. Pending Invites
    pending_invites = session.exec(select(func.count()).select_from(User).where(User.status == "pending")).one()

    # 4. Total Spending & Trend
    # Optimize: Calculate current spending (30d) and total spending. 
    # Current trend is compared to the lifetime spending before the last 30 days.
    thirty_days_ago = now - timedelta(days=30)
    current_period_spending = session.exec(
        select(func.sum(APIRequest.cost)).where(APIRequest.created_at > thirty_days_ago)
    ).one() or 0
    
    total_spending = session.exec(select(func.sum(APIRequest.cost))).one() or 0
    total_spending_prev = float(total_spending) - float(current_period_spending)
    
    # 5. Total Credits
    total_credits = session.exec(select(func.sum(User.credits))).one() or 0

    def calculate_trend(current, previous):
        # Ensure floating point for math
        curr = float(current)
        prev = float(previous)
        
        if prev <= 0:
            val = "100%" if curr > 0 else "0%"
            return {"value": val, "isPositive": True}
        
        change = ((curr - prev) / prev) * 100
        return {
            "value": f"{abs(change):.1f}%",
            "isPositive": change >= 0
        }

    return {
        "totalUsers": total_users,
        "activeUsers": active_users,
        "usersUsage": float(total_spending),
        "usersUsagePeriod": "Lifetime",
        "sharedCredits": int(total_credits),
        "sharedCreditsChange": 0,
        "sharedCreditsChangePeriod": "Last 30 days",
        "pendingInvites": pending_invites,
        "pendingInvitesStatus": "Incoming",
        "totalUsersTrend": calculate_trend(total_users, total_users_prev),
        "activeUsersTrend": calculate_trend(active_users, active_users_prev),
        "usersUsageTrend": calculate_trend(total_spending, total_spending_prev)
    }


from sqlalchemy.orm import selectinload

@router.get(
    "",
    dependencies=[Depends(RequiresPermission("user:manage"))],
    response_model=UsersPublic,
)
def read_users(
    session: SessionDep, 
    copilot_session: CopilotSessionDep,
    page: int = 1, 
    page_size: int = 100,
    search: str | None = None,
    status: str | None = None,
    role: str | None = None,
    sort_by: str | None = None,
    order: str | None = "asc"
) -> Any:
    """
    Retrieve users with filtering, pagination, and real spending data.
    """
    statement = select(User).options(selectinload(User.user_roles))
    
    if search:
        search_filter = f"%{search}%"
        statement = statement.where(
            (User.email.ilike(search_filter)) | 
            (User.full_name.ilike(search_filter))
        )
    
    from datetime import timedelta
    if status and status != 'all':
        statement = statement.where(User.status == status)
    
    if role and role != 'all':
        if role == 'admin':
            statement = statement.where(User.is_superuser == True)
        elif role == 'member':
            statement = statement.where(User.is_superuser == False)

    # Apply sorting
    if sort_by:
        sort_attr = getattr(User, sort_by, None)
        if sort_attr:
            statement = statement.order_by(desc(sort_attr) if order == "desc" else sort_attr)
    else:
        statement = statement.order_by(desc(User.created_at))

    # Get total count with filters applied
    count_statement = select(func.count()).select_from(statement.subquery())
    count = session.exec(count_statement).one()

    # Apply pagination and fetch results
    skip = (page - 1) * page_size
    users = session.exec(statement.offset(skip).limit(page_size)).all()

    # Optimize: Batch fetch spending, counts, and balances to avoid N+1 queries
    user_ids = [u.id for u in users]
    
    # 1. Batch Spending
    spending_stmt = select(APIRequest.user_id, func.sum(APIRequest.cost)).where(APIRequest.user_id.in_(user_ids)).group_by(APIRequest.user_id)
    spending_map = {row[0]: row[1] or 0 for row in session.exec(spending_stmt).all()}
    
    # 2. Batch Projects
    projects_stmt = select(Project.owner_user_id, func.count()).where(Project.owner_user_id.in_(user_ids)).group_by(Project.owner_user_id)
    projects_map = {row[0]: row[1] or 0 for row in session.exec(projects_stmt).all()}
    
    # 3. Batch Bots (Graceful fallback if copilot DB or schema is missing/inaccessible)
    bots_map = {}
    try:
        bots_stmt = select(Copilot.created_by, func.count()).where(Copilot.created_by.in_(user_ids)).group_by(Copilot.created_by)
        bots_results = copilot_session.exec(bots_stmt).all()
        bots_map = {row[0]: row[1] or 0 for row in bots_results}
    except Exception as e:
        print(f"⚠️ Could not fetch bot counts: {e}")
        bots_map = {}

    # Enhance users with fetched data
    public_users = []
    
    # Batch fetch organization memberships for all users in the current batch
    memberships = session.exec(
        select(OrganizationMember)
        .where(OrganizationMember.user_id.in_(user_ids))
        .options(selectinload(OrganizationMember.organization))
    ).all()
    
    # Map user_id to their primary organization (first one found)
    user_org_map = {}
    for m in memberships:
        if m.user_id not in user_org_map and m.organization:
            user_org_map[m.user_id] = {
                "id": str(m.organization_id),
                "name": m.organization.name,
                "credits_balance": float(m.organization.credits_balance)
            }

    for u in users:
        user_spending = spending_map.get(u.id, 0)
        bots_count = bots_map.get(u.id, 0)
        projects_count = projects_map.get(u.id, 0)
        
        real_balance = u.credits
        
        public_user = UserPublic.from_user(u)
        public_user.totalSpending = float(user_spending)
        public_user.credits = float(real_balance)
        public_user.botsCount = bots_count
        public_user.projectsCount = projects_count
        
        # Add organization info if available
        if u.id in user_org_map:
            public_user.organizationName = user_org_map[u.id]["name"]
            public_user.organization = user_org_map[u.id]
            public_user.orgCredits = user_org_map[u.id]["credits_balance"]
            
        public_users.append(public_user)

    return UsersPublic(
        data=public_users, 
        count=count
    )


@router.post(
    "", dependencies=[Depends(RequiresPermission("user:create"))], response_model=UserPublic
)
def create_user(*, session: SessionDep, current_user: CurrentUser, user_in: UserCreate) -> Any:
    """
    Create new user or invite a user.
    If no password is provided, it's treated as an invitation (is_active=False).
    """
    import secrets
    from app.core.security import get_password_hash

    user = user_repository.get_user_by_email(session=session, email=user_in.email)
    if user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )

    # Handle invitation flow
    is_invite = False
    if not user_in.password:
        is_invite = True
        user_in.password = secrets.token_urlsafe(16)
        # We'll set is_active=False manually after repo creates it or by overriding repo
    
    user = user_repository.create_user(session=session, user_create=user_in)
    
    if is_invite:
        user.is_active = False
        user.status = "pending"
        session.add(user)
        session.commit()
        session.refresh(user)

    if settings.emails_enabled and user_in.email:
        if is_invite:
            # For invited users, use the branded team invitation template
            # This is primarily for inviting users to the Platform/HQ
            
            # invitation_link = f"{settings.FRONTEND_HOST}/login"
            # Direct to sign-up for new users to set password
            invitation_link = f"{settings.FRONTEND_HOST}/sign-up?email={user_in.email}"
            
            # Determine role for message context
            role_desc = ""
            if user_in.role:
                role_desc = f" as {user_in.role.replace('_', ' ').title()}"
            elif user_in.roles:
                roles_str = ', '.join([r.replace('_', ' ').title() for r in user_in.roles])
                role_desc = f" with roles: {roles_str}"

            custom_msg = f"You have been invited to join Qorebit HQ{role_desc}."

            from app.utils import send_team_invitation_email
            send_team_invitation_email(
                email_to=user_in.email,
                inviter_name=current_user.full_name or current_user.email,
                workspace_name="Qorebit HQ",
                invitation_link=invitation_link,
                custom_message=custom_msg
            )
        else:
            # Self-signup still gets welcome email
            send_new_account_email(
                email_to=user_in.email,
                username=user_in.email
            )
    return UserPublic.from_user(user)


@router.patch("/me", response_model=UserPublic)
def update_user_me(
    *, session: SessionDep, user_in: UserUpdateMe, current_user: CurrentUser
) -> Any:
    """
    Update own user.
    """
    from datetime import datetime, timezone

    if user_in.email:
        existing_user = user_repository.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != current_user.id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )
    # Convert camelCase to snake_case for database
    user_data = user_in.to_db_dict()
    current_user.sqlmodel_update(user_data)
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return UserPublic.from_user(current_user)


@router.patch("/me/password", response_model=Message)
def update_password_me(
    *, session: SessionDep, body: UpdatePassword, current_user: CurrentUser
) -> Any:
    """
    Update own password.
    """
    if not verify_password(body.current_password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Incorrect password")
    if body.current_password == body.new_password:
        raise HTTPException(
            status_code=400, detail="New password cannot be the same as the current one"
        )
    hashed_password = get_password_hash(body.new_password)
    current_user.hashed_password = hashed_password
    session.add(current_user)
    session.commit()
    return Message(message="Password updated successfully")


@router.get("/me", response_model=UserPublic)
def read_user_me(current_user: CurrentUser) -> Any:
    """
    Get current user.
    """
    return UserPublic.from_user(current_user)


@router.post("/me/avatar", response_model=UserPublic)
def upload_avatar(
    *,
    session: SessionDep,
    current_user: CurrentUser,
    file: UploadFile = File(...),
) -> Any:
    """
    Upload user avatar.
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type. Allowed types: {', '.join(allowed_types)}",
        )

    # Validate file size (max 5MB)
    file.file.seek(0, 2)  # Seek to end
    file_size = file.file.tell()  # Get position (file size)
    file.file.seek(0)  # Reset to beginning

    max_size = 5 * 1024 * 1024  # 5MB
    if file_size > max_size:
        raise HTTPException(
            status_code=400,
            detail=f"File too large. Maximum size: {max_size / 1024 / 1024}MB",
        )

    # Create uploads directory if it doesn't exist
    upload_dir = Path("uploads/avatars")
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    file_extension = Path(file.filename).suffix if file.filename else ".jpg"
    unique_filename = f"{current_user.id}{file_extension}"
    file_path = upload_dir / unique_filename

    # Save file
    try:
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload file: {str(e)}")
    finally:
        file.file.close()

    # Update user avatar URL
    avatar_url = f"/uploads/avatars/{unique_filename}"
    current_user.avatar = avatar_url
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)

    return UserPublic.from_user(current_user)


@router.delete("/me/avatar", response_model=UserPublic)
def delete_avatar(
    *, session: SessionDep, current_user: CurrentUser
) -> Any:
    """
    Delete user avatar.
    """
    if current_user.avatar:
        # Try to delete the physical file
        try:
            file_path = Path(current_user.avatar.lstrip("/"))
            if file_path.exists():
                file_path.unlink()
        except Exception:
            # If file deletion fails, just clear the avatar field
            pass

    current_user.avatar = None
    current_user.updated_at = datetime.now(timezone.utc)
    session.add(current_user)
    session.commit()
    session.refresh(current_user)
    return UserPublic.from_user(current_user)


@router.delete("/me", response_model=Message)
def delete_user_me(session: SessionDep, current_user: CurrentUser) -> Any:
    """
    Delete own user.
    """
    if current_user.is_superuser:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    session.delete(current_user)
    session.commit()
    return Message(message="User deleted successfully")


@router.post("/signup", response_model=UserPublic)
def register_user(session: SessionDep, user_in: UserRegister) -> Any:
    """
    Create new user without the need to be logged in.
    """
    # Validate terms acceptance
    if not user_in.accept_terms:
        raise HTTPException(
            status_code=400,
            detail="You must accept the terms and conditions to create an account",
        )

    # Validate organization name for organization accounts
    if user_in.account_type == "organization" and not user_in.organization_name:
        raise HTTPException(
            status_code=400,
            detail="Organization name is required for company accounts",
        )

    user = user_repository.get_user_by_email(session=session, email=user_in.email)
    if user:
        # If user exists but is not active (e.g., invited user), allow them to "take over" the account
        if not user.is_active:
            # Update existing inactive user
            user.hashed_password = get_password_hash(user_in.password)
            if user_in.full_name:
                user.full_name = user_in.full_name
            
            user.is_active = True
            user.status = "active"
            # Auto-verify if they have a valid invitation token
            if user_in.invitation_token:
                from app.email_utils import verify_organization_invitation_token
                token_data = verify_organization_invitation_token(user_in.invitation_token)
                if token_data and token_data.get("email", "").lower() == user_in.email.lower():
                    user.is_verified = True
                    logger.info(f"Existing inactive user {user_in.email} auto-verified via invitation token")
            
            user.account_type = user_in.account_type
            if user_in.organization_name:
                user.organization_name = user_in.organization_name
            
            user.accepted_terms_at = datetime.now(timezone.utc)
            
            session.add(user)
            session.commit()
            session.refresh(user)
            
            # Send verification email for the "taken over" account if not verified
            if not user.is_verified:
                try:
                    send_email_verification(email_to=user.email, username=user.full_name or user.email)
                except Exception as e:
                    logger.error(f"Failed to send verification email to {user.email}: {e}")
            else:
                logger.info(f"Skipping verification email for already verified user: {user.email}")
            
            # If they are an organization account, ensure they have their own org
            if user_in.account_type == "organization" and user_in.organization_name:
                from app.models import Organization, OrganizationMember
                # Check if they already have an organization they own
                existing_org = session.exec(select(Organization).where(Organization.owner_id == user.id)).first()
                if not existing_org:
                    new_org = Organization(
                        name=user_in.organization_name,
                        owner_id=user.id,
                        is_active=True
                    )
                    session.add(new_org)
                    session.flush()
                    
                    org_member = OrganizationMember(
                        organization_id=new_org.id,
                        user_id=user.id,
                        role="org_super_admin",
                        status="active",
                        joined_at=datetime.now(timezone.utc)
                    )
                    session.add(org_member)
                    session.commit()

            return user
        
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system",
        )

    # Create UserCreate with base fields
    # Attempt to split full_name into first/last name for profile settings
    first_name = None
    last_name = None
    if user_in.full_name:
        parts = user_in.full_name.split(" ", 1)
        first_name = parts[0]
        if len(parts) > 1:
            last_name = parts[1]

    # Determine if user should be auto-verified (invited users)
    is_verified = False
    if user_in.invitation_token:
        from app.email_utils import verify_organization_invitation_token
        token_data = verify_organization_invitation_token(user_in.invitation_token)
        if token_data and token_data.get("email", "").lower() == user_in.email.lower():
            is_verified = True
            logger.info(f"User {user_in.email} auto-verified via invitation token")

    user_create = UserCreate(
        email=user_in.email,
        password=user_in.password,
        full_name=user_in.full_name,
        username=user_in.username or user_in.full_name,
        first_name=first_name,
        last_name=last_name,
        is_verified=is_verified
    )

    user = user_repository.create_user(
        session=session,
        user_create=user_create,
        account_type=user_in.account_type,
        organization_name=user_in.organization_name,
        accept_terms=user_in.accept_terms
    )
    
    # Send verification email only if not verified
    if not user.is_verified:
        try:
            send_email_verification(email_to=user.email, username=user.full_name or user.email)
        except Exception as e:
            logger.error(f"Failed to send verification email to {user.email}: {e}")
    return UserPublic.from_user(user)


@router.get("/{user_id}", response_model=UserPublic)
def read_user_by_id(
    user_id: uuid.UUID, session: SessionDep, copilot_session: CopilotSessionDep, current_user: CurrentUser
) -> Any:
    """
    Get a specific user by id with real usage stats.
    """
    user = session.exec(select(User).where(User.id == user_id).options(selectinload(User.user_roles))).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    is_org_admin = False
    if not current_user.is_superuser:
        from app.models import OrganizationMember
        # Check if user and current_user share an organization where current_user is admin
        # This is a bit complex but necessary for Org-level user management
        stmt = select(OrganizationMember).where(
            and_(
                OrganizationMember.user_id == current_user.id,
                OrganizationMember.role == "org_super_admin"
            )
        )
        admin_memberships = session.exec(stmt).all()
        if admin_memberships:
            admin_org_ids = [m.organization_id for m in admin_memberships]
            # Check if target user belongs to any of these orgs
            target_stmt = select(OrganizationMember).where(
                and_(
                    OrganizationMember.user_id == user.id,
                    OrganizationMember.organization_id.in_(admin_org_ids)
                )
            )
            if session.exec(target_stmt).first():
                is_org_admin = True

    if user != current_user and not current_user.is_superuser and not is_org_admin:
        raise HTTPException(
            status_code=403,
            detail="The user doesn't have enough privileges",
        )
    
    # Calculate spending
    user_spending = session.exec(
        select(func.sum(APIRequest.cost)).where(APIRequest.user_id == user.id)
    ).one() or 0
    
    # Get real-time credit balance
    real_balance = get_user_credit_balance(session=session, user_id=user.id)
    
    # Get organization membership
    membership = session.exec(
        select(OrganizationMember)
        .where(OrganizationMember.user_id == user.id)
        .options(selectinload(OrganizationMember.organization))
    ).first()
    
    public_user = UserPublic.from_user(user)
    
    if membership and membership.organization:
        public_user.organizationName = membership.organization.name
        public_user.organization = {
            "id": str(membership.organization_id),
            "name": membership.organization.name
        }
    
    public_user.credits = float(real_balance)

    # Get counts
    bots_count = copilot_session.exec(
        select(func.count()).select_from(Copilot).where(Copilot.created_by == user.id)
    ).one()
    projects_count = session.exec(
        select(func.count()).select_from(Project).where(Project.owner_user_id == user.id)
    ).one()

    public_user.totalSpending = float(user_spending)
    public_user.credits = float(real_balance)
    public_user.botsCount = bots_count
    public_user.projectsCount = projects_count
    
    return public_user


@router.patch(
    "/{user_id}",
    dependencies=[Depends(RequiresPermission("user:manage"))],
    response_model=UserPublic,
)
def update_user(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
    user_in: UserUpdate,
) -> Any:
    """
    Update a user.
    """

    db_user = session.exec(select(User).where(User.id == user_id).options(selectinload(User.user_roles))).first()
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    if user_in.email:
        existing_user = user_repository.get_user_by_email(session=session, email=user_in.email)
        if existing_user and existing_user.id != user_id:
            raise HTTPException(
                status_code=409, detail="User with this email already exists"
            )

    db_user = user_repository.update_user(session=session, db_user=db_user, user_in=user_in)
    return UserPublic.from_user(db_user)


@router.post(
    "/{user_id}/verify-email",
    dependencies=[Depends(RequiresRole("platform_super_admin"))],
    response_model=UserPublic,
)
def verify_user_email(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
) -> Any:
    """
    Manually verify a user's email (Platform Super Admin only).
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    
    user.is_verified = True
    session.add(user)
    session.commit()
    session.refresh(user)
    return UserPublic.from_user(user)


@router.delete("/{user_id}", dependencies=[Depends(RequiresPermission("user:delete"))])
def delete_user(
    session: SessionDep, 
    current_user: CurrentUser, 
    user_id: uuid.UUID,
    force_delete: bool = Query(False, alias="force")
) -> Any:
    """
    Delete a user. 
    If force_delete=True, manually cleans up common dependencies that might block deletion 
    due to missing DB cascades or complex relationships.
    """
    print(f"DEBUG: Delete request for user {user_id} (force_delete={force_delete})")
    logger.info(f"Delete request for user {user_id} (force_delete={force_delete})")
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Prevent self-deletion
    if user.id == current_user.id:
        raise HTTPException(
            status_code=403, detail="Super users are not allowed to delete themselves"
        )
    
    # Protection for root admin
    if user.email == "admin@qorebit.com" or user.email == settings.FIRST_SUPERUSER:
        raise HTTPException(
            status_code=403, detail="System protected root admin account cannot be deleted"
        )

    try:
        if force_delete:
            logger.info(f"Force deleting user {user_id} and cleaning up dependencies...")
            
            # 1. Delete OAuth Connections
            session.exec(delete(OAuthConnection).where(OAuthConnection.user_id == user_id))

            # 2. Delete API Requests
            session.exec(delete(APIRequest).where(APIRequest.user_id == user_id))
            
            # 3. Delete Credit Transactions
            session.exec(delete(CreditTransaction).where(CreditTransaction.user_id == user_id))
            
            # 4. Handle Workspaces where user is owner
            owned_workspaces = session.exec(select(Workspace).where(Workspace.owner_id == user_id)).all()
            for ws in owned_workspaces:
                # Cleanup workspace project members and projects
                projects = session.exec(select(WorkspaceProject).where(WorkspaceProject.workspace_id == ws.id)).all()
                for p in projects:
                    session.exec(delete(WorkspaceProjectMember).where(WorkspaceProjectMember.project_id == p.id))
                    session.delete(p)
                session.exec(delete(WorkspaceMember).where(WorkspaceMember.workspace_id == ws.id))
                session.delete(ws)

            # 5. Handle Organizations where user is owner
            owned_orgs = session.exec(select(Organization).where(Organization.owner_id == user_id)).all()
            for org in owned_orgs:
                session.exec(delete(OrganizationMember).where(OrganizationMember.organization_id == org.id))
                session.exec(delete(Project).where(Project.org_id == org.id))
                session.delete(org)
            
            # 6. Delete Projects where user is owner
            session.exec(delete(Project).where(Project.owner_user_id == user_id))

            # 7. Safety: Null out any remaining references to this user's API keys in OTHER projects
            # Get user's api key IDs
            user_api_key_ids = session.exec(select(APIKey.id).where(APIKey.user_id == user_id)).all()
            if user_api_key_ids:
                session.exec(update(Project).where(Project.api_key_id.in_(user_api_key_ids)).values(api_key_id=None))

            # 8. Decouple Projects from API keys before deleting keys
            # (Just a safety fallback for any lingering circular refs)
            session.exec(update(Project).where(Project.owner_user_id == user_id).values(api_key_id=None))

            # 9. Delete API Keys (Now safe after projects are handled)
            session.exec(delete(APIKey).where(APIKey.user_id == user_id))
            
            # 10. Delete Chat Messages and Chats
            session.exec(delete(AIChatMessage).where(
                AIChatMessage.chat_id.in_(select(AIChat.id).where(AIChat.user_id == user_id))
            ))
            session.exec(delete(AIChat).where(AIChat.user_id == user_id))

            # 11. Delete Campaigns, Notifications, TopUps, Credit Transfers
            session.exec(delete(Campaign).where(Campaign.user_id == user_id))
            session.exec(delete(Notification).where(Notification.user_id == user_id))
            session.exec(delete(TopUp).where(TopUp.user_id == user_id))
            session.exec(delete(CreditTransfer).where(
                (CreditTransfer.sender_id == user_id) | (CreditTransfer.recipient_id == user_id)
            ))

            # 12. Delete Wallets and Transactions
            # Delete transactions first
            session.exec(delete(WalletTransaction).where(
                WalletTransaction.wallet_id.in_(
                    select(Wallet.id).where((Wallet.owner_id == user_id) & (Wallet.owner_type == WalletOwnerType.USER))
                )
            ))
            session.exec(delete(Wallet).where((Wallet.owner_id == user_id) & (Wallet.owner_type == WalletOwnerType.USER)))

            # 12. Delete Memberships (Organization & Workspace)
            # Find and nullify any workspace credit transactions where this user's memberships are recipients
            member_ids = session.exec(
                select(WorkspaceMember.id).where(WorkspaceMember.user_id == user_id)
            ).all()
            if member_ids:
                session.exec(
                    update(WorkspaceCreditTransaction)
                    .where(WorkspaceCreditTransaction.recipient_id.in_(member_ids))
                    .values(recipient_id=None)
                )

            session.exec(delete(WorkspaceProjectMember).where(
                WorkspaceProjectMember.member_id.in_(
                    select(WorkspaceMember.id).where(WorkspaceMember.user_id == user_id)
                )
            ))
            session.exec(delete(WorkspaceMember).where(WorkspaceMember.user_id == user_id))
            session.exec(delete(OrganizationMember).where(OrganizationMember.user_id == user_id))

            # 13. Delete User Roles
            session.exec(delete(UserRole).where(UserRole.user_id == user_id))
            
            session.flush()

        session.delete(user)
        session.commit()
        return {"success": True, "message": "User deleted successfully"}
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to delete user {user_id}: {str(e)}")
        
        error_str = str(e).lower()
        if "foreign key" in error_str or "violation" in error_str:
             detail_msg = f"Cannot delete user because they have active records (projects, transactions, etc.) linked to them. [Force={force_delete}]"
             if force_delete:
                 detail_msg = f"Force delete failed due to persistent database constraint (Force={force_delete}): {str(e)}"
             raise HTTPException(
                status_code=400,
                detail=detail_msg
            )
        raise HTTPException(
            status_code=500,
            detail=f"An internal error occurred while deleting the user: {str(e)}"
        )
@router.patch(
    "/{user_id}/identity-role",
    dependencies=[Depends(RequiresPermission("user:roles_assign"))],
    response_model=UserPublic,
)
def update_user_identity_role_endpoint(
    *,
    session: SessionDep,
    user_id: uuid.UUID,
    role_in: UserIdentityRoleUpdate,
) -> Any:
    """
    Update a user's singular identity role.
    """
    db_user = session.exec(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.user_roles).selectinload(UserRole.role))
    ).first()
    if not db_user:
        raise HTTPException(
            status_code=404,
            detail="The user with this id does not exist in the system",
        )
    
    try:
        db_user = user_repository.update_user_identity_role(
            session=session, 
            db_user=db_user, 
            role_name=role_in.identityRole
        )
        
        # Explicitly re-fetch with full relationship tree for serialization
        db_user = session.exec(
            select(User)
            .where(User.id == db_user.id)
            .options(selectinload(User.user_roles).selectinload(UserRole.role))
        ).first()
        
        return UserPublic.from_user(db_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
@router.post("/{user_id}/credits/allocate", dependencies=[Depends(RequiresPermission("user:manage"))])
def allocate_user_credits(
    user_id: uuid.UUID,
    data: UserCreditAllocation,
    session: SessionDep,
    current_user: CurrentUser,
) -> Any:
    """
    Allocate user credits (add or remove) to their personal wallet
    with full audit logging.
    """
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    adjustment_amount = Decimal(str(data.amount))
    signed_amount = adjustment_amount if data.adjustment_type == "add" else -adjustment_amount
    description = f"{data.reason_category}: {data.reason_description}" if data.reason_description else data.reason_category
    
    from app.services.wallet_service import WalletService
    from app.models import WalletOwnerType, WalletTransactionType, AuditLog, OrganizationCreditTransaction
    
    # Determine target wallet (Priority: Organization if user owns one, for HQ consistency)
    from app.models import Organization
    owned_org = session.exec(select(Organization).where(Organization.owner_id == user.id)).first()
    
    if owned_org:
        # Allocate to organization wallet
        previous_balance = get_user_credit_balance(session=session, user_id=user.id, organization_id=owned_org.id)
        wallet = WalletService.get_or_create_wallet(session, owned_org.id, WalletOwnerType.ORGANIZATION)
        audit_target_type = "Organization"
        audit_target_id = str(owned_org.id)
    else:
        # Allocate to user's personal wallet
        previous_balance = get_user_credit_balance(session=session, user_id=user.id)
        wallet = WalletService.get_or_create_wallet(session, user.id, WalletOwnerType.USER)
        audit_target_type = "User"
        audit_target_id = str(user.id)
    
    WalletService.add_transaction(
        session=session,
        wallet_id=wallet.id,
        transaction_type=WalletTransactionType.TOP_UP if data.adjustment_type == "add" else WalletTransactionType.ADJUSTMENT,
        amount=signed_amount,
        description=description,
        credit=adjustment_amount if data.adjustment_type == "add" else Decimal("0.0000"),
        debit=adjustment_amount if data.adjustment_type == "deduct" else Decimal("0.0000"),
        created_by=current_user.id,
        source="admin_allocation"
    )
    session.refresh(user)
    if owned_org:
        new_balance = get_user_credit_balance(session=session, user_id=user.id, organization_id=owned_org.id)
    else:
        new_balance = get_user_credit_balance(session=session, user_id=user.id)
    
    # Create Audit Log
    audit_entry = AuditLog(
        actor_id=current_user.id,
        actor_name=current_user.full_name or current_user.email,
        actor_role="Platform Super Admin",
        action="USER_CREDITS_ALLOCATED",
        action_category="financial",
        target_id=audit_target_id,
        target_type=audit_target_type,
        severity="medium",
        status="success",
        meta_data={
            "adjustment_type": data.adjustment_type,
            "amount": float(adjustment_amount),
            "previous_balance": float(previous_balance),
            "new_balance": float(new_balance),
            "reason_category": data.reason_category,
            "reason_description": data.reason_description,
            "notify_user": data.notify_user
        }
    )
    session.add(audit_entry)
    session.commit()
    
    # Send in-app notification if requested and credits were added
    if data.notify_user and data.adjustment_type == "add":
        recipients = [user]
        org_name = owned_org.name if owned_org else None
        
        # If user owns an org, also notify other admins
        if owned_org:
            admins_stmt = select(User).where(
                User.id.in_(
                    select(OrganizationMember.user_id).where(
                        OrganizationMember.organization_id == owned_org.id,
                        OrganizationMember.role.in_(["org_super_admin", "org_admin"]),
                        OrganizationMember.status == "active"
                    )
                )
            )
            org_admins = session.exec(admins_stmt).all()
            # Combine and deduplicate
            recipient_ids = {r.id for r in recipients}
            for admin in org_admins:
                if admin.id not in recipient_ids:
                    recipients.append(admin)
                    recipient_ids.add(admin.id)

        title = f"Credits Allocated to {org_name}! 🎉" if org_name else "Credits Received! 🎉"
        body = (
            f"Administrative allocation: {int(adjustment_amount)} credits have been added to your organization wallet."
            if org_name else
            f"Administrative allocation: {int(adjustment_amount)} credits have been added to your wallet."
        )
        
        for recipient in recipients:
            try:
                create_notification(
                    session=session,
                    user_id=recipient.id,
                    title=title,
                    description=body,
                    type="credit_received",
                    metadata={
                        "admin_id": str(current_user.id),
                        "amount": float(adjustment_amount),
                        "reason": data.reason_description or data.reason_category,
                        "organization_id": str(owned_org.id) if owned_org else None,
                        "organization_name": org_name
                    },
                    commit=True
                )
                logger.info(f"Submitting in-app notification for user {recipient.email}")
            except Exception as e:
                logger.error(f"Failed to create credit notification for {recipient.email}: {e}")
            
            # Send email notification
            try:
                from app.services.email_service import email_service
                if owned_org:
                    email_service.send_credit_adjustment_notification(
                        email_to=recipient.email,
                        org_name=owned_org.name,
                        adjustment_type=data.adjustment_type,
                        amount=float(adjustment_amount),
                        reason=description,
                        new_balance=float(new_balance)
                    )
                else:
                    from app.email_utils import send_credit_allocation_email
                    send_credit_allocation_email(
                        email_to=recipient.email,
                        username=recipient.full_name or recipient.email,
                        amount=int(adjustment_amount),
                        reason=data.reason_description or data.reason_category,
                        new_balance=float(new_balance),
                    )
                logger.info(f"Submitting email notification for user {recipient.email}")
            except Exception as e:
                logger.error(f"Failed to send credit allocation email to {recipient.email}: {e}")
    
    return {"id": user.id, "newBalance": float(new_balance), "orgId": str(owned_org.id) if owned_org else None}

