import uuid
from typing import Any
from decimal import Decimal
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import select, func

from app.api.deps import SessionDep, CurrentUser, get_current_active_superuser
from app.models import (
    User,
    TeamMemberPublic,
    TeamListResponse,
    TeamAnalytics,
    APIRequest,
    CreditTransaction,
    Role,
    UserRole,
)
from sqlmodel import Session

router = APIRouter(prefix="/team-members", tags=["team"])


def _get_user_role_name(session: Session, user_id: uuid.UUID) -> str | None:
    stmt = select(Role.name).join(UserRole, Role.id == UserRole.role_id).where(UserRole.user_id == user_id)
    row = session.exec(stmt).first()
    return row


@router.get("/analytics", response_model=TeamAnalytics)
def get_team_analytics(session: SessionDep, current_user: CurrentUser) -> Any:
    """Return aggregated team analytics/stats."""
    # Total members
    total = session.exec(select(func.count()).select_from(User)).one()

    # Active members
    active = session.exec(select(func.count()).select_from(User).where(User.is_active == True)).one()

    # Team usage = sum of APIRequest.cost
    usage_row = session.exec(select(func.sum(APIRequest.cost))).one()
    team_usage = usage_row or Decimal("0.00")

    # Shared credits = sum of positive CreditTransaction.amount
    shared_row = session.exec(select(func.sum(CreditTransaction.amount))).one()
    shared_credits = shared_row or Decimal("0.00")

    # Pending invites = users with is_active == False
    pending = session.exec(select(func.count()).select_from(User).where(User.is_active == False)).one()

    analytics = TeamAnalytics(
        totalMembers=int(total),
        activeMembers=int(active),
        teamUsage=team_usage if isinstance(team_usage, Decimal) else Decimal(str(team_usage or 0)),
        teamUsagePeriod=None,
        sharedCredits=shared_credits if isinstance(shared_credits, Decimal) else Decimal(str(shared_credits or 0)),
        sharedCreditsChange=None,
        sharedCreditsChangePeriod=None,
        pendingInvites=int(pending),
        pendingInvitesStatus=None,
    )
    return analytics


@router.get("", response_model=TeamListResponse)
def list_team_members(
    session: SessionDep,
    current_user: CurrentUser,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    status: str | None = None,
    role: str | None = None,
    sort_by: str | None = None,
    order: str | None = None,
) -> Any:
    """Paginated list of team members with simple filters."""
    if page < 1:
        page = 1
    if page_size < 1:
        page_size = 20
    skip = (page - 1) * page_size

    stmt = select(User)

    if search:
        pattern = f"%{search}%"
        stmt = stmt.where((User.email.ilike(pattern)) | (User.full_name.ilike(pattern)))

    if status:
        if status.lower() == "active":
            stmt = stmt.where(User.is_active == True)
        elif status.lower() == "pending":
            stmt = stmt.where(User.is_active == False)

    if role:
        # join with UserRole -> Role
        stmt = stmt.join(UserRole, User.id == UserRole.user_id).join(Role, Role.id == UserRole.role_id).where(Role.name == role)

    # total count
    count_stmt = stmt.with_only_columns(func.count()).order_by(None)
    total = session.exec(count_stmt).one()

    # sorting - simple support
    if sort_by == "email":
        if order == "desc":
            stmt = stmt.order_by(User.email.desc())
        else:
            stmt = stmt.order_by(User.email)
    else:
        # default order by created id
        stmt = stmt.order_by(User.id)

    stmt = stmt.offset(skip).limit(page_size)
    users = session.exec(stmt).all()

    # Fetch usage per user
    result_list: list[TeamMemberPublic] = []
    for u in users:
        usage = session.exec(select(func.sum(APIRequest.cost)).where(APIRequest.user_id == u.id)).one() or Decimal("0.00")
        last_req = session.exec(select(APIRequest).where(APIRequest.user_id == u.id).order_by(APIRequest.created_at.desc()).limit(1)).first()
        role_name = _get_user_role_name(session, u.id)
        first_name = None
        last_name = None
        if u.full_name:
            parts = u.full_name.split(" ", 1)
            first_name = parts[0]
            last_name = parts[1] if len(parts) > 1 else None

        member = TeamMemberPublic(
            id=u.id,
            name=u.full_name,
            firstName=first_name,
            lastName=last_name,
            email=u.email,
            username=u.username,
            phoneNumber=u.phone_number,
            address=u.address,
            city=u.city,
            country=u.country,
            img=None,
            role=role_name,
            lastOnline=last_req.created_at if last_req else None,
            status=("active" if u.is_active else "pending"),
            totalSpending=usage if isinstance(usage, Decimal) else Decimal(str(usage or 0)),
        )
        result_list.append(member)

    return TeamListResponse(list=result_list, total=int(total))


@router.get("/{user_id}", response_model=TeamMemberPublic)
def get_team_member(user_id: uuid.UUID, session: SessionDep, current_user: CurrentUser) -> Any:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    usage = session.exec(select(func.sum(APIRequest.cost)).where(APIRequest.user_id == user.id)).one() or Decimal("0.00")
    last_req = session.exec(select(APIRequest).where(APIRequest.user_id == user.id).order_by(APIRequest.created_at.desc()).limit(1)).first()
    role_name = _get_user_role_name(session, user.id)
    first_name = None
    last_name = None
    if user.full_name:
        parts = user.full_name.split(" ", 1)
        first_name = parts[0]
        last_name = parts[1] if len(parts) > 1 else None

    return TeamMemberPublic(
        id=user.id,
        name=user.full_name,
        firstName=first_name,
        lastName=last_name,
        email=user.email,
        username=user.username,
        phoneNumber=user.phone_number,
        address=user.address,
        city=user.city,
        country=user.country,
        img=None,
        role=role_name,
        lastOnline=last_req.created_at if last_req else None,
        status=("active" if user.is_active else "pending"),
        totalSpending=usage if isinstance(usage, Decimal) else Decimal(str(usage or 0)),
    )


@router.post("", response_model=TeamMemberPublic)
def create_team_member(data: dict, session: SessionDep, current_user: User = Depends(get_current_active_superuser)) -> Any:
    """Create/invite a team member. Expects keys: email, role, firstName, lastName (optional)"""
    email = data.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=409, detail="User already exists")

    # minimal create: generate a random password and create inactive user (invite)
    import secrets
    from app.core.security import get_password_hash

    pw = secrets.token_urlsafe(12)
    hashed = get_password_hash(pw)
    full_name = None
    first = data.get("firstName")
    last = data.get("lastName")
    if first and last:
        full_name = f"{first} {last}"
    elif first:
        full_name = first

    user = User(
        email=email,
        hashed_password=hashed,
        is_active=False,
        full_name=full_name,
        username=data.get("username"),
        phone_number=data.get("phoneNumber"),
        dial_code=data.get("dialCode"),
        address=data.get("address"),
        postcode=data.get("postcode"),
        city=data.get("city"),
        country=data.get("country"),
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    # assign role if provided
    role_name = data.get("role")
    if role_name:
        role = session.exec(select(Role).where(Role.name == role_name)).first()
        if role:
            ur = UserRole(user_id=user.id, role_id=role.id)
            session.add(ur)
            session.commit()

    return get_team_member(user.id, session=session, current_user=current_user)


@router.put("/{user_id}", response_model=TeamMemberPublic)
def update_team_member(user_id: uuid.UUID, data: dict, session: SessionDep, current_user: User = Depends(get_current_active_superuser)) -> Any:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # allow updating role, status, name
    role_name = data.get("role")
    if role_name:
        role = session.exec(select(Role).where(Role.name == role_name)).first()
        if role:
            # remove old roles and add new
            olds = session.exec(select(UserRole).where(UserRole.user_id == user.id)).all()
            for o in olds:
                session.delete(o)
            session.commit()
            ur = UserRole(user_id=user.id, role_id=role.id)
            session.add(ur)
            session.commit()

    if "status" in data:
        s = data.get("status")
        user.is_active = True if s == "active" else False

    if "firstName" in data or "lastName" in data:
        first = data.get("firstName")
        last = data.get("lastName")
        if first and last:
            user.full_name = f"{first} {last}"
        elif first:
            user.full_name = first

    # allow updating username and contact/profile fields
    if "username" in data:
        user.username = data.get("username")
    if "phoneNumber" in data:
        user.phone_number = data.get("phoneNumber")
    if "dialCode" in data:
        user.dial_code = data.get("dialCode")
    if "address" in data:
        user.address = data.get("address")
    if "postcode" in data:
        user.postcode = data.get("postcode")
    if "city" in data:
        user.city = data.get("city")
    if "country" in data:
        user.country = data.get("country")

    session.add(user)
    session.commit()
    session.refresh(user)
    return get_team_member(user.id, session=session, current_user=current_user)


@router.delete("/{user_id}")
def delete_team_member(user_id: uuid.UUID, session: SessionDep, current_user: User = Depends(get_current_active_superuser)) -> Any:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session.delete(user)
    session.commit()
    return {"success": True, "message": "User deleted"}


@router.post("/{user_id}/resend-invitation")
def resend_invitation(user_id: uuid.UUID, session: SessionDep, current_user: User = Depends(get_current_active_superuser)) -> Any:
    user = session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # For now just return success. Email sending could be wired here.
    return {"success": True, "message": "Invitation resent (simulated)"}
