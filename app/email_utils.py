"""
Modern Email Utils using Postmark Email Service
Replaces legacy SMTP-only implementation
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

import jwt
from jwt.exceptions import InvalidTokenError

from app.core import security
from app.core.config import settings
from app.services.email_service import email_service

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ============================================
# Token Management (kept from legacy)
# ============================================


def generate_password_reset_token(email: str) -> str:
    """Generate password reset JWT token"""
    delta = timedelta(hours=settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS)
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email},
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    return encoded_jwt


def verify_password_reset_token(token: str) -> str | None:
    """Verify password reset token and return email"""
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        return str(decoded_token["sub"])
    except InvalidTokenError:
        return None


def generate_email_verification_token(email: str) -> str:
    """Generate email verification JWT token"""
    delta = timedelta(hours=24)  # Verification token valid for 24 hours
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {"exp": exp, "nbf": now, "sub": email, "type": "email_verification"},
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    return encoded_jwt


def verify_email_verification_token(token: str) -> str | None:
    """Verify email verification token and return email"""
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        if decoded_token.get("type") == "email_verification":
            return str(decoded_token["sub"])
        return None
    except InvalidTokenError:
        return None



def generate_organization_invitation_token(email: str, organization_id: str) -> str:
    """Generate organization invitation JWT token"""
    delta = timedelta(days=7)  # Invitation token valid for 7 days
    now = datetime.now(timezone.utc)
    expires = now + delta
    exp = expires.timestamp()
    encoded_jwt = jwt.encode(
        {
            "exp": exp,
            "nbf": now,
            "sub": email,
            "organization_id": organization_id,
            "type": "organization_invitation"
        },
        settings.SECRET_KEY,
        algorithm=security.ALGORITHM,
    )
    return encoded_jwt


def verify_organization_invitation_token(token: str) -> Dict[str, str] | None:
    """Verify organization invitation token and return email and organization_id"""
    try:
        decoded_token = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[security.ALGORITHM]
        )
        if decoded_token.get("type") == "organization_invitation":
            return {
                "email": str(decoded_token["sub"]),
                "organization_id": str(decoded_token["organization_id"])
            }
        return None
    except InvalidTokenError:
        return None


# Alias for backward compatibility
generate_team_invitation_token = generate_organization_invitation_token
verify_team_invitation_token = verify_organization_invitation_token


# ============================================
# Email Sending Functions (using new service)
# ============================================


def send_test_email(email_to: str) -> Dict[str, Any]:
    """Send test email"""
    return email_service.send_test_email(email_to=email_to)


def send_reset_password_email(email_to: str, email: str, token: str) -> Dict[str, Any]:
    """Send password reset email"""
    return email_service.send_password_reset_email(
        email_to=email_to, email=email, token=token
    )


def send_new_account_email(email_to: str, username: str) -> Dict[str, Any]:
    """Send welcome email for new account"""
    return email_service.send_welcome_email(email_to=email_to, username=username)


def send_email_verification(email_to: str, username: str) -> Dict[str, Any]:
    """Send email verification link"""
    token = generate_email_verification_token(email_to)
    verification_link = f"{settings.FRONTEND_HOST}/verify-email?token={token}"
    try:
        result = email_service.send_email_verification(
            email_to=email_to, username=username, verification_token=token
        )
        # Attach verification link to result for debugging/local dev convenience
        if isinstance(result, dict):
            result.setdefault("verification_link", verification_link)
            result.setdefault("verification_token", token)
        # Log the verification link so it's easy to find in server logs
        logging.info(f"Email verification link for {email_to}: {verification_link}")
        return result
    except Exception as e:
        # Log error and still return the verification link so callers can surface it
        logging.error(f"Failed to send verification email to {email_to}: {e}")
        return {"status": "failed", "reason": str(e), "verification_link": verification_link, "verification_token": token}


# ============================================
# Additional Email Functions
# ============================================


def send_team_invitation_email(
    email_to: str,
    inviter_name: str,
    workspace_name: str,
    invitation_link: str,
    custom_message: str | None = None,
) -> Dict[str, Any]:
    """Send team/workspace invitation email.

    Note: older callers pass `workspace_name` and an optional `custom_message`.
    Map `workspace_name` to `team_name` expected by the underlying service.
    """
    if custom_message:
        logger.info("Custom invitation message provided for %s", email_to)

    return email_service.send_team_invitation(
        email_to=email_to,
        inviter_name=inviter_name,
        team_name=workspace_name,
        invitation_link=invitation_link,
        custom_message=custom_message,
    )


def send_workspace_notification_email(
    email_to: str,
    username: str,
    workspace_name: str,
    notification_title: str,
    notification_message: str,
    action_link: str | None = None,
) -> Dict[str, Any]:
    """Send workspace notification email"""
    return email_service.send_workspace_notification(
        email_to=email_to,
        username=username,
        workspace_name=workspace_name,
        notification_title=notification_title,
        notification_message=notification_message,
        action_link=action_link,
    )


def send_credit_low_alert_email(
    email_to: str, username: str, credits_remaining: float
) -> Dict[str, Any]:
    """Send low credit balance alert"""
    return email_service.send_credit_low_alert(
        email_to=email_to, username=username, credits_remaining=credits_remaining
    )


def send_credit_purchase_confirmation_email(
    email_to: str,
    username: str,
    credits_purchased: float,
    amount_paid: float,
    transaction_id: str,
) -> Dict[str, Any]:
    """Send credit purchase confirmation"""
    return email_service.send_credit_purchase_confirmation(
        email_to=email_to,
        username=username,
        credits_purchased=credits_purchased,
        amount_paid=amount_paid,
        transaction_id=transaction_id,
    )


def send_api_key_created_notification_email(
    email_to: str, username: str, api_key_name: str
) -> Dict[str, Any]:
    """Send API key creation notification"""
    return email_service.send_api_key_created_notification(
        email_to=email_to, username=username, api_key_name=api_key_name
    )


def send_credit_allocation_email(
    email_to: str,
    username: str,
    amount: int,
    reason: str,
    new_balance: float,
) -> Dict[str, Any]:
    """Send credit allocation notification to user"""
    return email_service.send_credit_received_notification(
        email_to=email_to,
        username=username,
        sender_name="Qorebit Platform Admin",
        amount=amount,
        message=reason,
        credits_balance=int(new_balance),
    )
