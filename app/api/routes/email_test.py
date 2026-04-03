"""
Email Testing API Routes
Endpoints for testing the email service functionality
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr

from app.email_utils import (
    generate_email_verification_token,
    generate_password_reset_token,
    send_api_key_created_notification_email,
    send_credit_low_alert_email,
    send_credit_purchase_confirmation_email,
    send_email_verification,
    send_new_account_email,
    send_reset_password_email,
    send_team_invitation_email,
    send_test_email,
    send_workspace_notification_email,
)
from app.services.email_service import email_service

router = APIRouter()


# ============================================
# Request Models
# ============================================


class TestEmailRequest(BaseModel):
    email: EmailStr


class WelcomeEmailRequest(BaseModel):
    email: EmailStr
    username: str


class PasswordResetRequest(BaseModel):
    email: EmailStr


class EmailVerificationRequest(BaseModel):
    email: EmailStr
    username: str


class TeamInvitationRequest(BaseModel):
    email: EmailStr
    inviter_name: str
    team_name: str
    invitation_link: str


class WorkspaceNotificationRequest(BaseModel):
    email: EmailStr
    username: str
    workspace_name: str
    notification_title: str
    notification_message: str
    action_link: str | None = None


class CreditLowAlertRequest(BaseModel):
    email: EmailStr
    username: str
    credits_remaining: float


class CreditPurchaseRequest(BaseModel):
    email: EmailStr
    username: str
    credits_purchased: float
    amount_paid: float
    transaction_id: str


class APIKeyNotificationRequest(BaseModel):
    email: EmailStr
    username: str
    api_key_name: str


# ============================================
# Email Testing Endpoints
# ============================================


@router.post("/test-email")
def test_email_endpoint(request: TestEmailRequest) -> Any:
    """
    Send a test email to verify email service configuration

    Example:
    ```
    POST /api/v1/email/test-email
    {
        "email": "test@example.com"
    }
    ```
    """
    try:
        result = send_test_email(request.email)
        return {
            "message": "Test email sent successfully",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send test email: {str(e)}"
        )


@router.post("/welcome-email")
def send_welcome_email_endpoint(request: WelcomeEmailRequest) -> Any:
    """
    Send welcome email to new user

    Example:
    ```
    POST /api/v1/email/welcome-email
    {
        "email": "user@example.com",
        "username": "John Doe"
    }
    ```
    """
    try:
        result = send_new_account_email(request.email, request.username)
        return {
            "message": "Welcome email sent successfully",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send welcome email: {str(e)}"
        )


@router.post("/password-reset")
def send_password_reset_endpoint(request: PasswordResetRequest) -> Any:
    """
    Send password reset email

    Example:
    ```
    POST /api/v1/email/password-reset
    {
        "email": "user@example.com"
    }
    ```
    """
    try:
        token = generate_password_reset_token(request.email)
        result = send_reset_password_email(request.email, request.email, token)
        return {
            "message": "Password reset email sent successfully",
            "token": token,  # Don't return token in production!
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send password reset email: {str(e)}"
        )


@router.post("/email-verification")
def send_verification_endpoint(request: EmailVerificationRequest) -> Any:
    """
    Send email verification link

    Example:
    ```
    POST /api/v1/email/email-verification
    {
        "email": "user@example.com",
        "username": "John Doe"
    }
    ```
    """
    try:
        result = send_email_verification(request.email, request.username)
        return {
            "message": "Verification email sent successfully",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send verification email: {str(e)}"
        )


@router.post("/team-invitation")
def send_team_invitation_endpoint(request: TeamInvitationRequest) -> Any:
    """
    Send team invitation email

    Example:
    ```
    POST /api/v1/email/team-invitation
    {
        "email": "newmember@example.com",
        "inviter_name": "Jane Smith",
        "team_name": "Engineering Team",
        "invitation_link": "https://yourdomain.com/invitations/abc123"
    }
    ```
    """
    try:
        result = send_team_invitation_email(
            request.email,
            request.inviter_name,
            request.team_name,
            request.invitation_link,
        )
        return {
            "message": "Team invitation sent successfully",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send team invitation: {str(e)}"
        )


@router.post("/workspace-notification")
def send_workspace_notification_endpoint(request: WorkspaceNotificationRequest) -> Any:
    """
    Send workspace notification email

    Example:
    ```
    POST /api/v1/email/workspace-notification
    {
        "email": "user@example.com",
        "username": "John Doe",
        "workspace_name": "My Workspace",
        "notification_title": "New Project Created",
        "notification_message": "A new project has been created.",
        "action_link": "https://yourdomain.com/workspace/projects/123"
    }
    ```
    """
    try:
        result = send_workspace_notification_email(
            request.email,
            request.username,
            request.workspace_name,
            request.notification_title,
            request.notification_message,
            request.action_link,
        )
        return {
            "message": "Workspace notification sent successfully",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send workspace notification: {str(e)}",
        )


@router.post("/credit-low-alert")
def send_credit_low_alert_endpoint(request: CreditLowAlertRequest) -> Any:
    """
    Send low credit balance alert

    Example:
    ```
    POST /api/v1/email/credit-low-alert
    {
        "email": "user@example.com",
        "username": "John Doe",
        "credits_remaining": 5.0
    }
    ```
    """
    try:
        result = send_credit_low_alert_email(
            request.email, request.username, request.credits_remaining
        )
        return {
            "message": "Credit low alert sent successfully",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to send credit low alert: {str(e)}"
        )


@router.post("/credit-purchase-confirmation")
def send_credit_purchase_endpoint(request: CreditPurchaseRequest) -> Any:
    """
    Send credit purchase confirmation

    Example:
    ```
    POST /api/v1/email/credit-purchase-confirmation
    {
        "email": "user@example.com",
        "username": "John Doe",
        "credits_purchased": 100.0,
        "amount_paid": 2500.00,
        "transaction_id": "TXN-123456789"
    }
    ```
    """
    try:
        result = send_credit_purchase_confirmation_email(
            request.email,
            request.username,
            request.credits_purchased,
            request.amount_paid,
            request.transaction_id,
        )
        return {
            "message": "Credit purchase confirmation sent successfully",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send credit purchase confirmation: {str(e)}",
        )


@router.post("/api-key-notification")
def send_api_key_notification_endpoint(request: APIKeyNotificationRequest) -> Any:
    """
    Send API key creation notification

    Example:
    ```
    POST /api/v1/email/api-key-notification
    {
        "email": "user@example.com",
        "username": "John Doe",
        "api_key_name": "Production API Key"
    }
    ```
    """
    try:
        result = send_api_key_created_notification_email(
            request.email, request.username, request.api_key_name
        )
        return {
            "message": "API key notification sent successfully",
            "result": result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to send API key notification: {str(e)}",
        )


@router.get("/service-status")
def get_email_service_status() -> Any:
    """
    Get email service configuration status

    Example:
    ```
    GET /api/v1/email/service-status
    ```
    """
    from app.core.config import settings

    return {
        "email_provider": settings.EMAIL_PROVIDER,
        "emails_enabled": settings.emails_enabled,
        "postmark_configured": bool(settings.POSTMARK_SERVER_TOKEN),
        "smtp_configured": bool(settings.SMTP_HOST),
        "from_email": settings.EMAILS_FROM_EMAIL,
        "from_name": settings.EMAILS_FROM_NAME,
    }
