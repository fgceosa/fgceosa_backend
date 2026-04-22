import logging
import uuid
from typing import Any

logger = logging.getLogger(__name__)

from sqlmodel import Session, select

from app.core.security import get_password_hash, verify_password
from app.models import User, UserCreate, UserUpdate, Role, UserRole
from app.utils.membership_generator import assign_membership_id


def create_user(
    *,
    session: Session,
    user_create: UserCreate,
    account_type: str = "individual",
    organization_name: str | None = None,
    accept_terms: bool = False
) -> User:
    from datetime import datetime, timezone

    db_obj = User.model_validate(
        user_create, update={
            "hashed_password": get_password_hash(user_create.password),
            "accepted_terms_at": datetime.now(timezone.utc) if accept_terms else None
        }
    )
    session.add(db_obj)
    session.commit()
    session.refresh(db_obj)

    # Assign role based on account type or explicit role provided
    # Organization accounts get 'org_super_admin' role, individuals get 'user' role
    # Priority: Explicit role > account_type
    role_names = []
    if user_create.roles:
        role_names = user_create.roles
    elif user_create.role:
        role_names = [user_create.role]
    else:
        role_names = ["super_admin" if account_type == "organization" else "member"]

    for role_name in role_names:
        # Normalize role name
        role_name = role_name.lower().replace(" ", "_")
        role_obj = session.exec(select(Role).where(Role.name == role_name)).first()
        if role_obj:
            user_role = UserRole(user_id=db_obj.id, role_id=role_obj.id)
            session.add(user_role)
            
            # Update legacy superuser flag if applicable
            admin_roles = ["super_admin", "admin"]
            if role_obj.name in admin_roles:
                db_obj.is_superuser = True
    
    # Organizations removed from schema

    session.commit()
    session.refresh(db_obj)

    # Generate and assign unique membership ID
    try:
        assign_membership_id(session=session, user=db_obj, commit=True)
    except Exception as e:
        # Log error but don't fail user creation
        logger.error(f"Failed to assign membership ID to user {db_obj.id}: {e}")

    return db_obj


def update_user(*, session: Session, db_user: User, user_in: UserUpdate) -> Any:
    user_data = user_in.model_dump(exclude_unset=True)
    extra_data = {}
    if "password" in user_data:
        password = user_data["password"]
        hashed_password = get_password_hash(password)
        extra_data["hashed_password"] = hashed_password
    
    # Handle role update if provided (supports both single 'role' string and 'roles' list of strings)
    role_names = user_data.pop("roles", None)
    if role_names is None and "role" in user_data:
        rn = user_data.pop("role")
        role_names = [rn] if rn else []
    
    if role_names is not None:
        # Fetch valid Role objects from the database
        roles = session.exec(select(Role).where(Role.name.in_(role_names))).all()
        
        if roles:
            # Update legacy superuser flag if any admin-level role is present
            admin_roles = ["super_admin", "admin"]
            db_user.is_superuser = any(r.name in admin_roles for r in roles)
            
            # Clear existing roles and add new ones (Syncing)
            from sqlmodel import delete
            session.exec(delete(UserRole).where(UserRole.user_id == db_user.id))
            
            for role in roles:
                user_role = UserRole(user_id=db_user.id, role_id=role.id)
                session.add(user_role)
                
                pass
        elif not role_names:
            # If empty list provided, clear all roles
            from sqlmodel import delete
            session.exec(delete(UserRole).where(UserRole.user_id == db_user.id))
            db_user.is_superuser = False
    
    db_user.sqlmodel_update(user_data, update=extra_data)
    session.add(db_user)
    session.commit()
    session.refresh(db_user)
    return db_user


def create_social_user(
    *,
    session: Session,
    email: str,
    full_name: str | None = None,
    avatar: str | None = None,
    auth_provider: str = "google",
) -> User:
    """
    Finds or creates a user for social login.
    """
    from datetime import datetime, timezone
    import secrets

    # Check if user already exists
    db_user = get_user_by_email(session=session, email=email)
    if db_user:
        # Update provider if it was password (to allow switching to social)
        if db_user.auth_provider == "password":
            db_user.auth_provider = auth_provider
        
        # Update name and avatar if missing
        if not db_user.full_name and full_name:
            db_user.full_name = full_name
        if not db_user.avatar and avatar:
            db_user.avatar = avatar
            
        session.add(db_user)
        session.commit()
        session.refresh(db_user)
        return db_user

    # Create new user for social login
    user_create = UserCreate(
        email=email,
        full_name=full_name,
        avatar=avatar,
        auth_provider=auth_provider,
        is_verified=True,  # OAuth users are considered verified
        password=secrets.token_urlsafe(32)  # Secure random password
    )
    
    return create_user(session=session, user_create=user_create)


def get_user_by_email(*, session: Session, email: str) -> User | None:
    statement = select(User).where(User.email == email)
    session_user = session.exec(statement).first()
    return session_user


def update_user_identity_role(*, session: Session, db_user: User, role_name: str) -> User:
    """
    Strictly updates the user's primary identity role by replacing any existing roles.
    """
    # Normalize role name (e.g. 'Platform Super Admin' -> 'platform_super_admin')
    normalized_name = role_name.lower().replace(" ", "_")
    
    role = session.exec(select(Role).where(Role.name == normalized_name)).first()
    if not role:
        raise ValueError(f"Role '{role_name}' does not exist.")

    # Update legacy superuser flag based on identity role
    admin_roles = ["super_admin", "admin"]
    db_user.is_superuser = role.name in admin_roles

    # Sync identity role (Strictly one role per identity-first model)
    db_user.user_roles = [UserRole(user_id=db_user.id, role_id=role.id)]
    session.add(db_user)
    
    # Organization logic removed

    # Commit and refresh
    # Log promotion/demotion (Audit Log Simulation)
    logger.info(f"AUDIT LOG: User {db_user.email} identity role updated to {normalized_name}")
    
    session.commit()
    session.refresh(db_user)
    
    return db_user


def authenticate(*, session: Session, email: str, password: str) -> User | None:
    db_user = get_user_by_email(session=session, email=email)
    if not db_user:
        return None
    if not verify_password(password, db_user.hashed_password):
        return None
    return db_user


def get_user_by_id(*, session: Session, user_id: uuid.UUID) -> User | None:
    """Get user by ID"""
    return session.get(User, user_id)


def get_users(
    *, session: Session, skip: int = 0, limit: int = 100
) -> list[User]:
    """Get multiple users with pagination"""
    statement = select(User).offset(skip).limit(limit)
    return list(session.exec(statement).all())


def delete_user(*, session: Session, user_id: uuid.UUID) -> bool:
    """Delete user by ID"""
    user = session.get(User, user_id)
    if not user:
        return False
    session.delete(user)
    session.commit()
    return True


