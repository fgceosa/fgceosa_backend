"""
Comprehensive Email Service using Postmark
Handles all email functionality with retry logic, logging, and error handling
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Template
from postmarker.core import PostmarkClient
from postmarker.exceptions import PostmarkerException
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class EmailType(str, Enum):
    """Email types for tracking and analytics"""

    WELCOME = "welcome"
    PASSWORD_RESET = "password_reset"
    EMAIL_VERIFICATION = "email_verification"
    TEAM_INVITATION = "team_invitation"
    WORKSPACE_NOTIFICATION = "workspace_notification"
    TRANSACTION_ALERT = "transaction_alert"
    CREDIT_LOW = "credit_low"
    CREDIT_PURCHASED = "credit_purchased"
    API_KEY_CREATED = "api_key_created"
    TEST = "test"
    PAYMENT_REMINDER = "payment_reminder"


@dataclass
class EmailData:
    """Email data structure"""

    html_content: str
    subject: str
    email_type: EmailType
    metadata: Optional[Dict[str, Any]] = None


class EmailService:
    """
    Comprehensive email service with Postmark integration
    Supports both Postmark and SMTP fallback
    """

    def __init__(self):
        self.postmark_client: Optional[PostmarkClient] = None
        self.provider = settings.EMAIL_PROVIDER

        # Initialize Postmark client if configured
        if self.provider == "postmark" and settings.POSTMARK_SERVER_TOKEN:
            try:
                self.postmark_client = PostmarkClient(
                    server_token=settings.POSTMARK_SERVER_TOKEN
                )
                logger.info("Postmark email service initialized successfully")
            except Exception as e:
                logger.error(f"Failed to initialize Postmark client: {e}")
                self.postmark_client = None

    @retry(
        retry=retry_if_exception_type(PostmarkerException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def send_email(
        self,
        *,
        email_to: str,
        subject: str,
        html_content: str,
        text_content: str | None = None,
        email_type: EmailType = EmailType.TRANSACTION_ALERT,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Send email with retry logic and comprehensive error handling

        Args:
            email_to: Recipient email address
            subject: Email subject
            html_content: HTML content of the email
            email_type: Type of email for tracking
            cc: List of CC recipients
            bcc: List of BCC recipients
            reply_to: Reply-to email address
            attachments: List of attachments
            metadata: Additional metadata for tracking

        Returns:
            Dict containing send result and metadata
        """
        if not settings.emails_enabled:
            logger.warning("Email service is not enabled. Skipping email send.")
            return {
                "status": "skipped",
                "reason": "Email service not configured",
            }

        try:
            if self.provider == "postmark" and self.postmark_client:
                result = self._send_via_postmark(
                    email_to=email_to,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                    email_type=email_type,
                    cc=cc,
                    bcc=bcc,
                    reply_to=reply_to,
                    attachments=attachments,
                    metadata=metadata,
                )
            else:
                result = self._send_via_smtp(
                    email_to=email_to,
                    subject=subject,
                    html_content=html_content,
                    text_content=text_content,
                )

            logger.info(
                f"Email sent successfully to {email_to} | Type: {email_type} | Provider: {self.provider}"
            )
            return result

        except Exception as e:
            logger.error(
                f"Failed to send email to {email_to} | Type: {email_type} | Error: {str(e)}"
            )
            raise

    def _send_via_postmark(
        self,
        *,
        email_to: str,
        subject: str,
        html_content: str,
        text_content: str | None,
        email_type: EmailType,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Send email via Postmark"""
        if not self.postmark_client:
            raise ValueError("Postmark client not initialized")

        # Prepare email data
        email_data: Dict[str, Any] = {
            "From": f"{settings.EMAILS_FROM_NAME} <{settings.EMAILS_FROM_EMAIL}>",
            "To": email_to,
            "Subject": subject,
            "HtmlBody": html_content,
            # include TextBody for non-HTML clients
            **({"TextBody": text_content} if text_content else {}),
            "MessageStream": settings.POSTMARK_MESSAGE_STREAM,
            "Tag": email_type.value,
        }

        # Add optional fields
        if cc:
            email_data["Cc"] = ", ".join(cc)
        if bcc:
            email_data["Bcc"] = ", ".join(bcc)
        if reply_to:
            email_data["ReplyTo"] = reply_to
        if attachments:
            email_data["Attachments"] = attachments

        # Add metadata for tracking
        if metadata:
            email_data["Metadata"] = metadata

        # Send email
        response = self.postmark_client.emails.send(**email_data)

        return {
            "status": "sent",
            "provider": "postmark",
            "message_id": response.get("MessageID"),
            "submitted_at": response.get("SubmittedAt"),
            "to": email_to,
            "email_type": email_type.value,
        }

    def _send_via_smtp(
        self, *, email_to: str, subject: str, html_content: str
    , text_content: str | None = None) -> Dict[str, Any]:
        """Send email via SMTP (fallback)"""
        import emails  # type: ignore

        message = emails.Message(
            subject=subject,
            html=html_content,
            text=text_content or None,
            mail_from=(settings.EMAILS_FROM_NAME, settings.EMAILS_FROM_EMAIL),
        )

        smtp_options = {"host": settings.SMTP_HOST, "port": settings.SMTP_PORT}
        if settings.SMTP_TLS:
            smtp_options["tls"] = True
        elif settings.SMTP_SSL:
            smtp_options["ssl"] = True
        if settings.SMTP_USER:
            smtp_options["user"] = settings.SMTP_USER
        if settings.SMTP_PASSWORD:
            smtp_options["password"] = settings.SMTP_PASSWORD

        response = message.send(to=email_to, smtp=smtp_options)

        return {
            "status": "sent" if response.status_code == 250 else "failed",
            "provider": "smtp",
            "response": str(response),
            "to": email_to,
        }

    @staticmethod
    def render_template(*, template_name: str, context: Dict[str, Any]) -> str:
        """
        Render email template with context

        Args:
            template_name: Name of the template file
            context: Template context variables

        Returns:
            Rendered HTML content
        """
        template_path = (
            Path(__file__).resolve().parent.parent / "email-templates" / "build" / template_name
        )
        
        # logger.info(f"Looking for template at: {template_path}")

        if not template_path.exists():
            logger.warning(
                f"Template {template_name} not found at {template_path}. Using fallback."
            )
            
            # Special fallback for team invitation to ensure link is sent
            if template_name == "team_invitation.html":
                return f"""
                <!DOCTYPE html>
                <html>
                <body style="font-family: Arial, sans-serif; padding: 20px;">
                    <h2>{context.get('inviter_name', 'Someone')} invited you to join {context.get('team_name', 'their team')}</h2>
                    <p>Click the link below to join:</p>
                    <p><a href="{context.get('invitation_link', '#')}">{context.get('invitation_link', 'Join Team')}</a></p>
                    {f"<p>Message: {context.get('message')}</p>" if context.get('message') else ""}
                </body>
                </html>
                """

            if template_name == "payment_reminder.html":
                return f"""
                <!DOCTYPE html>
                <html>
                <body style="font-family: 'Inter', Arial, sans-serif; padding: 40px; background-color: #f9f9f9;">
                    <div style="max-width: 600px; margin: 0 auto; background: white; padding: 40px; border-radius: 24px; border: 1px solid #eee;">
                        <h2 style="color: #8B0000; font-size: 24px; font-weight: 800; margin-bottom: 24px;">Action Required: Payment Reminder</h2>
                        <p style="font-size: 16px; color: #444; line-height: 1.6;">Hello <strong>{context.get('username', 'Member')}</strong>,</p>
                        <p style="font-size: 16px; color: #444; line-height: 1.6;">This is a friendly reminder regarding your outstanding dues for <strong>{context.get('description', 'the association')}</strong>.</p>
                        
                        <div style="margin: 32px 0; padding: 24px; background-color: #fef2f2; border-radius: 16px; border: 1px solid #fee2e2;">
                            <div style="font-size: 12px; font-weight: 800; color: #8B0000; text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 8px;">Outstanding Balance</div>
                            <div style="font-size: 32px; font-weight: 900; color: #8B0000;">₦{float(context.get('amount', 0)):,.2f}</div>
                        </div>

                        <p style="font-size: 15px; color: #666; margin-bottom: 32px;">Please click the button below to settle your balance and maintain your active membership status.</p>
                        
                        <a href="{context.get('payment_link', '#')}" style="display: inline-block; background-color: #8B0000; color: white; padding: 16px 32px; border-radius: 12px; text-decoration: none; font-weight: 800; font-size: 14px; text-transform: uppercase; letter-spacing: 0.05em; box-shadow: 0 10px 15px -3px rgba(139, 0, 0, 0.2);">Clear Balance Now</a>
                        
                        <hr style="border: 0; border-top: 1px solid #eee; margin: 40px 0;">
                        <p style="font-size: 12px; color: #999; text-align: center;">If you have already made this payment, please disregard this notice.</p>
                    </div>
                </body>
                </html>
                """

            # Return a simple fallback template
            return f"""
            <!DOCTYPE html>
            <html>
            <head><meta charset="UTF-8"></head>
            <body>
                <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
                    <h2>{context.get('subject', 'Notification')}</h2>
                    <p>{context.get('message', 'This is a notification from ' + settings.PROJECT_NAME)}</p>
                    <hr style="border: 1px solid #eee; margin: 20px 0;">
                    <p style="color: #666; font-size: 12px;">
                        This email was sent by {settings.PROJECT_NAME}
                    </p>
                </div>
            </body>
            </html>
            """

        template_str = template_path.read_text()
        html_content = Template(template_str).render(context)
        return html_content

    # ============================================
    # Pre-defined Email Templates
    # ============================================

    def send_welcome_email(self, *, email_to: str, username: str) -> Dict[str, Any]:
        """Send welcome email to new user"""
        html_content = self.render_template(
            template_name="welcome_email.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": username,
                "email": email_to,
                "login_link": f"{settings.FRONTEND_HOST}/login",
                "dashboard_link": f"{settings.FRONTEND_HOST}/dashboard",
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=f"Welcome to {settings.PROJECT_NAME}!",
            html_content=html_content,
            email_type=EmailType.WELCOME,
            metadata={"username": username, "timestamp": datetime.utcnow().isoformat()},
        )

    def send_password_reset_email(
        self, *, email_to: str, email: str, token: str
    ) -> Dict[str, Any]:
        """Send password reset email"""
        reset_link = f"{settings.FRONTEND_HOST}/reset-password?token={token}"

        html_content = self.render_template(
            template_name="reset_password.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": email,
                "email": email_to,
                "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
                "link": reset_link,
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=f"{settings.PROJECT_NAME} - Password Recovery",
            html_content=html_content,
            email_type=EmailType.PASSWORD_RESET,
            metadata={"email": email, "timestamp": datetime.utcnow().isoformat()},
        )

    def send_email_verification(
        self, *, email_to: str, username: str, verification_token: str
    ) -> Dict[str, Any]:
        """Send email verification link"""
        verification_link = (
            f"{settings.FRONTEND_HOST}/verify-email?token={verification_token}"
        )

        html_content = self.render_template(
            template_name="verify_email.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": username,
                "email": email_to,
                "verification_link": verification_link,
                "valid_hours": 24,
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=f"Verify your {settings.PROJECT_NAME} email",
            html_content=html_content,
            email_type=EmailType.EMAIL_VERIFICATION,
            metadata={"username": username, "timestamp": datetime.utcnow().isoformat()},
        )

    def send_team_invitation(
        self,
        *,
        email_to: str,
        inviter_name: str,
        team_name: str,
        invitation_link: str,
        custom_message: str | None = None,
    ) -> Dict[str, Any]:
        """Send team invitation email (legacy alias — delegates to send_organization_invitation)"""
        return self.send_organization_invitation(
            email_to=email_to,
            inviter_name=inviter_name,
            organization_name=team_name,
            invitation_link=invitation_link,
            custom_message=custom_message,
        )

    def send_organization_invitation(
        self,
        *,
        email_to: str,
        inviter_name: str,
        organization_name: str,
        invitation_link: str,
        custom_message: str | None = None,
    ) -> Dict[str, Any]:
        """Send organization invitation email with HTML template and plaintext fallback"""
        context = {
            "project_name": settings.PROJECT_NAME,
            "inviter_name": inviter_name,
            "team_name": organization_name,  # template variable reuse
            "organization_name": organization_name,
            "email": email_to,
            "invitation_link": invitation_link,
            "valid_days": 7,
            "logo_url": getattr(settings, "EMAILS_LOGO_URL", "") or "",
            "year": datetime.utcnow().year,
            "message": custom_message,
        }

        html_content = self.render_template(
            template_name="team_invitation.html",
            context=context,
        )

        # Plaintext fallback for non-HTML clients
        lines = [f"{inviter_name} invited you to join {organization_name}", ""]
        if custom_message:
            lines.extend(["Message:", custom_message, ""])
        lines.append(f"Accept your invitation here: {invitation_link}")
        lines.append("")
        lines.append(f"This invitation is valid for {context['valid_days']} days.")
        text_body = "\n".join(lines)

        return self.send_email(
            email_to=email_to,
            subject=f"{inviter_name} invited you to join {organization_name}",
            html_content=html_content,
            text_content=text_body,
            email_type=EmailType.TEAM_INVITATION,
            metadata={
                "inviter": inviter_name,
                "organization": organization_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def send_workspace_notification(
        self,
        *,
        email_to: str,
        username: str,
        workspace_name: str,
        notification_title: str,
        notification_message: str,
        action_link: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send workspace notification"""
        html_content = self.render_template(
            template_name="workspace_notification.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": username,
                "workspace_name": workspace_name,
                "notification_title": notification_title,
                "notification_message": notification_message,
                "action_link": action_link,
                "dashboard_link": f"{settings.FRONTEND_HOST}/workspace",
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=f"{workspace_name}: {notification_title}",
            html_content=html_content,
            email_type=EmailType.WORKSPACE_NOTIFICATION,
            metadata={
                "workspace": workspace_name,
                "notification": notification_title,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def send_credit_low_alert(
        self, *, email_to: str, username: str, credits_remaining: float
    ) -> Dict[str, Any]:
        """Send low credit balance alert"""
        html_content = self.render_template(
            template_name="credit_low_alert.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": username,
                "credits_remaining": credits_remaining,
                "topup_link": f"{settings.FRONTEND_HOST}/billing",
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=f"Low Credit Balance Alert - {settings.PROJECT_NAME}",
            html_content=html_content,
            email_type=EmailType.CREDIT_LOW,
            metadata={
                "username": username,
                "credits_remaining": str(credits_remaining),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def send_credit_purchase_confirmation(
        self,
        *,
        email_to: str,
        username: str,
        credits_purchased: float,
        amount_paid: float,
        transaction_id: str,
    ) -> Dict[str, Any]:
        """Send credit purchase confirmation"""
        html_content = self.render_template(
            template_name="credit_purchased.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": username,
                "credits_purchased": credits_purchased,
                "amount_paid": amount_paid,
                "transaction_id": transaction_id,
                "dashboard_link": f"{settings.FRONTEND_HOST}/dashboard",
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=f"Credit Purchase Confirmation - {settings.PROJECT_NAME}",
            html_content=html_content,
            email_type=EmailType.CREDIT_PURCHASED,
            metadata={
                "username": username,
                "credits": str(credits_purchased),
                "amount": str(amount_paid),
                "transaction_id": transaction_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def send_api_key_created_notification(
        self, *, email_to: str, username: str, api_key_name: str
    ) -> Dict[str, Any]:
        """Send API key creation notification"""
        html_content = self.render_template(
            template_name="api_key_created.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": username,
                "api_key_name": api_key_name,
                "created_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
                "security_link": f"{settings.FRONTEND_HOST}/settings/security",
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=f"New API Key Created - {settings.PROJECT_NAME}",
            html_content=html_content,
            email_type=EmailType.API_KEY_CREATED,
            metadata={
                "username": username,
                "api_key_name": api_key_name,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def send_test_email(self, *, email_to: str) -> Dict[str, Any]:
        """Send test email"""
        html_content = self.render_template(
            template_name="test_email.html",
            context={"project_name": settings.PROJECT_NAME, "email": email_to},
        )

        return self.send_email(
            email_to=email_to,
            subject=f"{settings.PROJECT_NAME} - Test Email",
            html_content=html_content,
            email_type=EmailType.TEST,
            metadata={"timestamp": datetime.utcnow().isoformat()},
        )

    def send_credit_received_notification(
        self,
        *,
        email_to: str,
        username: str,
        sender_name: str,
        amount: int,
        message: str | None = None,
        credits_balance: int | None = None,
    ) -> Dict[str, Any]:
        """Send credit received notification"""
        html_content = self.render_template(
            template_name="credit_received.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": username,
                "sender_name": sender_name,
                "amount": amount,
                "message": message,
                "credits_balance": credits_balance,
                "date": datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC"),
                "dashboard_link": f"{settings.FRONTEND_HOST}/dashboard",
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=f"You received {amount} credits from {sender_name}",
            html_content=html_content,
            email_type=EmailType.TRANSACTION_ALERT,
            metadata={
                "username": username,
                "sender": sender_name,
                "amount": str(amount),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def send_credit_adjustment_notification(
        self,
        *,
        email_to: str,
        org_name: str,
        adjustment_type: str,
        amount: float,
        reason: str,
        new_balance: float
    ) -> Dict[str, Any]:
        """Send notification to organization super admin about credit adjustment"""
        type_str = "added to" if adjustment_type == "add" else "deducted from"
        subject = f"Credit Adjustment Notification - {org_name}"
        
        html_content = self.render_template(
            template_name="credit_adjustment.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "org_name": org_name,
                "adjustment_type": adjustment_type,
                "type_display": type_str,
                "amount": amount,
                "reason": reason,
                "new_balance": new_balance,
                "date": datetime.utcnow().strftime("%B %d, %Y at %I:%M %p UTC"),
                "dashboard_link": f"{settings.FRONTEND_HOST}/dashboard",
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=subject,
            html_content=html_content,
            email_type=EmailType.TRANSACTION_ALERT,
            metadata={
                "org_name": org_name,
                "adjustment_type": adjustment_type,
                "amount": str(amount),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    def send_organization_setup_email(
        self,
        *,
        email_to: str,
        username: str,
        org_name: str,
        setup_link: str
    ) -> Dict[str, Any]:
        """Send organization setup email to new admin"""
        subject = f"Welcome to {settings.PROJECT_NAME} - Setup your organization"
        
        # Use a template or fallback logic
        html_content = self.render_template(
            template_name="organization_setup.html",
            context={
                "project_name": settings.PROJECT_NAME,
                "username": username,
                "org_name": org_name,
                "email": email_to,
                "setup_link": setup_link,
                "valid_hours": settings.EMAIL_RESET_TOKEN_EXPIRE_HOURS,
                "year": datetime.utcnow().year,
            },
        )

        return self.send_email(
            email_to=email_to,
            subject=subject,
            html_content=html_content,
            email_type=EmailType.WELCOME,
            metadata={
                "org_name": org_name,
                "username": username, 
                "timestamp": datetime.utcnow().isoformat()
            },
        )
    def send_payment_reminder(
        self,
        *,
        email_to: str,
        username: str,
        amount: float,
        due_date: str | None = None,
        description: str | None = None,
        payment_link: str | None = None,
    ) -> Dict[str, Any]:
        """Send payment reminder email"""
        context = {
            "project_name": settings.PROJECT_NAME,
            "username": username,
            "amount": amount,
            "due_date": due_date,
            "description": description or "Annual Alumni Dues",
            "payment_link": payment_link or f"{settings.FRONTEND_HOST}/dashboard/payments",
            "year": datetime.utcnow().year,
        }

        # Use fallback rendering since template might not exist yet
        html_content = self.render_template(
            template_name="payment_reminder.html",
            context=context,
        )

        return self.send_email(
            email_to=email_to,
            subject=f"Action Required: Payment Reminder - {settings.PROJECT_NAME}",
            html_content=html_content,
            email_type=EmailType.PAYMENT_REMINDER,
            metadata={
                "username": username,
                "amount": str(amount),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )


# Create singleton instance
email_service = EmailService()
