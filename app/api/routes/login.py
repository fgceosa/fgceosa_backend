from datetime import timedelta
import logging
from typing import Annotated, Any

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm

from app import user_repository
from app.api.deps import CurrentUser, SessionDep, get_current_active_superuser
from app.core import security
from app.core.config import settings
from app.core.security import get_password_hash
from app.models import Message, NewPassword, Token, UserPublic, SecurityEvent, UserSocialLogin
from app.utils.permissions import get_user_roles, get_user_permissions
from app.utils import (
    generate_password_reset_token,
    send_reset_password_email,
    verify_password_reset_token,
    send_email_verification,
    verify_email_verification_token,
)
from app.services.email_service import email_service

router = APIRouter(tags=["login"])


@router.post("/login/access-token")
def login_access_token(
    session: SessionDep, 
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    request: Request
) -> Token:
    """
    OAuth2 compatible token login, get an access token for future requests
    """
    try:
        user = user_repository.authenticate(
            session=session, email=form_data.username, password=form_data.password
        )
        
        # Check Platform Maintenance Mode
        from app.models import PlatformSettings
        from sqlmodel import select
        
        platform_settings = session.exec(select(PlatformSettings)).first()
        if platform_settings and (platform_settings.general or {}).get("systemStatus") == "maintenance":
            # We need to check roles to bypass maintenance
            # Since we haven't checked user status yet, we should probably do this check AFTER user is confirmed valid?
            # Or we can do it here if user exists.
            
            if user:
                 user_roles_check = get_user_roles(session, user)
                 # allowed_roles = ["platform_super_admin", "admin"] # Decide on roles
                 # If user does not have bypass permission:
                 if "platform_super_admin" not in user_roles_check and "admin" not in user_roles_check:
                     raise HTTPException(
                         status_code=503,
                         detail="Platform is currently under maintenance. Please try again later."
                     )
        
        if not user:
            # Log failed login attempt for Security Dashboard
            try:
                client_ip = request.client.host if request.client else "unknown"
                failed_event = SecurityEvent(
                    type="login_attempt",
                    severity="low",
                    description=f"Failed login attempt for email: {form_data.username}",
                    source_ip=client_ip,
                    status="open" # Open event, but effectively just a log
                )
                session.add(failed_event)
                session.commit()
            except Exception as e:
                print(f"Failed to log security event: {e}")

            raise HTTPException(
                status_code=401, 
                detail="the email or password you entered is incorrect, please check your credentials and try again"
            )
        
        # Check if user account is deactivated
        if user.status == "deactivated":
            raise HTTPException(
                status_code=403, 
                detail="your account has been deactivated, please contact our support team for help"
            )
        
        # Check if user account is inactive (not yet activated)
        if user.status != "active":
            raise HTTPException(
                status_code=403, 
                detail=f"your account is currently {user.status}, please contact our support team for assistance"
            )
            
        # Check if user email is verified
        if not user.is_verified:
            # Re-send verification email if they try to login and are not verified
            try:
                send_email_verification(email_to=user.email, username=user.full_name or user.email)
            except Exception as e:
                print(f"Failed to resend verification email: {e}")
                
            raise HTTPException(
                status_code=403,
                detail="your email address has not been verified yet. We have sent a new verification link to your email. Please check your inbox and verify your account to continue."
            )
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        # Log the error for debugging
        error_msg = str(e)
        print(f"❌ Login error: {error_msg}")
        
        # Determine if it's a known DB error
        detail = "we're having trouble signing you in right now"
        if "relation" in error_msg.lower() and "does not exist" in error_msg.lower():
            detail = f"System Error: A required database table is missing ({error_msg.split('relation ')[-1].split(' ')[0]}). Please contact support."
        elif "connection" in error_msg.lower():
            detail = "Database connection error. Please try again in a few moments."
        else:
            detail = f"An unexpected error occurred during login. Please contact support. (Ref: {error_msg[:50]}...)"

        raise HTTPException(
            status_code=500,
            detail=detail
        )
    
    # Update last login
    from datetime import datetime, timezone
    user.last_login = datetime.now(timezone.utc)
    session.add(user)
    session.commit()
    session.refresh(user)
    
    # Get user roles and permissions for authority and access control
    user_roles = get_user_roles(session, user)
    user_permissions = get_user_permissions(session, user)
    
    # Debug: Check if tag_number exists
    print(f"🏷️ Login - User tag_number: {user.tag_number}, User ID: {user.id}, Email: {user.email}")
    
    return Token(
        access_token=security.create_access_token(
            user.id, expires_delta=access_token_expires
        ),
        user={
            "userId": str(user.id),
            "userName": user.full_name or user.email,
            "authority": user_roles,
            "permissions": user_permissions,
            "avatar": "",  # Can be extended later
            "email": user.email,
            "tag_number": user.tag_number  # Include Qorebit tag
        }
    )


@router.post("/login/social", response_model=Token)
def login_social(
    session: SessionDep,
    social_data: UserSocialLogin,
    request: Request
) -> Token:
    """
    Login via social provider (GitHub, Google, etc.)
    Syncs the user with the backend database and returns a backend JWT.
    """
    try:
        # Get or Create the user in the backend
        user = user_repository.create_social_user(
            session=session,
            email=social_data.email,
            full_name=social_data.full_name,
            avatar=social_data.avatar,
            auth_provider=social_data.provider
        )
        
        if not user:
            raise HTTPException(status_code=500, detail="Failed to sync social user")
            
        # Check if user account is deactivated
        if user.status == "deactivated":
            raise HTTPException(
                status_code=403, 
                detail="your account has been deactivated, please contact our support team for help"
            )
            
        # Update last login
        from datetime import datetime, timezone
        user.last_login = datetime.now(timezone.utc)
        session.add(user)
        session.commit()
        session.refresh(user)
        
        # Get roles and permissions
        user_roles = get_user_roles(session, user)
        user_permissions = get_user_permissions(session, user)
        
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        return Token(
            access_token=security.create_access_token(
                user.id, expires_delta=access_token_expires
            ),
            user={
                "userId": str(user.id),
                "userName": user.full_name or user.email,
                "authority": user_roles,
                "permissions": user_permissions,
                "avatar": user.avatar or "",
                "email": user.email,
                "tag_number": user.tag_number
            }
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Social login error: {e}")
        raise HTTPException(status_code=500, detail=f"Internal server error during social login: {str(e)}")


@router.post("/login/test-token", response_model=UserPublic)
def test_token(current_user: CurrentUser) -> Any:
    """
    Test access token
    """
    return current_user


@router.post("/password-recovery/{email}")
def recover_password(email: str, session: SessionDep) -> Message:
    """
    Password Recovery
    """
    user = user_repository.get_user_by_email(session=session, email=email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this email does not exist in the system.",
        )
    password_reset_token = generate_password_reset_token(email=email)
    send_reset_password_email(
        email_to=user.email, email=email, token=password_reset_token
    )
    return Message(message="Password recovery email sent")


@router.post("/reset-password")
def reset_password(session: SessionDep, body: NewPassword) -> Message:
    """
    Reset password
    """
    email = verify_password_reset_token(token=body.token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid token")
    user = user_repository.get_user_by_email(session=session, email=email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this email does not exist in the system.",
        )
    elif user.status not in ["active", "pending"]:
        raise HTTPException(status_code=400, detail="Inactive user")
    
    hashed_password = get_password_hash(password=body.new_password)
    user.hashed_password = hashed_password
    
    # Implicitly verify email if not already verified
    user.is_verified = True
    if user.status == "pending":
        user.status = "active"
        
    session.add(user)
    session.commit()
    return Message(message="Password updated successfully")


@router.post(
    "/password-recovery-html-content/{email}",
    dependencies=[Depends(get_current_active_superuser)],
    response_class=HTMLResponse,
)
def recover_password_html_content(email: str, session: SessionDep) -> Any:
    """
    HTML Content for Password Recovery
    """
    user = user_repository.get_user_by_email(session=session, email=email)

    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this username does not exist in the system.",
        )
    password_reset_token = generate_password_reset_token(email=email)
    reset_link = f"{settings.FRONTEND_HOST}/reset-password?token={password_reset_token}"

    html_content = email_service.render_template(
        template_name="reset_password.html",
        context={
            "project_name": settings.PROJECT_NAME,
            "username": email,
            "email": user.email,
            "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
            "link": reset_link,
        },
    )

    return HTMLResponse(
        content=html_content,
        headers={"subject": f"{settings.PROJECT_NAME} - Password Recovery"}
    )


@router.post("/login/verify-email")
def verify_email(session: SessionDep, token: str) -> Message:
    """
    Verify email with token
    """
    email = verify_email_verification_token(token=token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired verification token")
    
    user = user_repository.get_user_by_email(session=session, email=email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this email does not exist in the system.",
        )
    
    if user.is_verified:
        return Message(message="Email already verified")
        
    user.is_verified = True
    # If account was pending, set it to active
    if user.status == "pending":
        user.status = "active"
        
    session.add(user)
    session.commit()
    
    return Message(message="Email verified successfully. You can now log in.")


@router.post("/login/resend-verification/{email}")
def resend_verification(email: str, session: SessionDep) -> Message:
    """
    Resend email verification link
    """
    user = user_repository.get_user_by_email(session=session, email=email)
    if not user:
        raise HTTPException(
            status_code=404,
            detail="The user with this email does not exist in the system.",
        )
    
    if user.is_verified:
        return Message(message="Email already verified")
        
    send_email_verification(email_to=user.email, username=user.full_name or user.email)
    return Message(message="Verification email sent")
