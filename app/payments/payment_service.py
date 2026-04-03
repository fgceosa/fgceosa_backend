"""
Payment Service - Business Logic Layer.

This service provides a clean interface for payment operations,
abstracting away provider-specific details.
"""

from typing import Dict, Any, Optional
from datetime import datetime
from sqlmodel import Session, select
from app.payments.payment_factory import PaymentFactory
from app.models import TopUp, User, Workspace, WorkspaceCreditTransaction, TopUpStatus
from app.credit_repository import add_credits, log_api_request
from app.core.config import settings
from app.notification_repository import create_notification



class PaymentService:
    """
    Payment service for handling payment operations.

    This service encapsulates all payment-related business logic and
    uses the PaymentFactory to work with the configured provider.
    """

    def __init__(self):
        """Initialize payment service with the active provider."""
        self.provider = PaymentFactory.get_provider()
        self.provider_name = PaymentFactory.get_provider_name()

    def _apply_topup_credits(self, db: Session, topup: TopUp, provider_name: str, reference: str):
        """Helper to apply credits to either workspace or user wallet."""
        from app.models import User
        if topup.organization_id:
            # Credit organization wallet
            print(f"DEBUG: Applying top-up of {topup.ai_credits} credits to ORGANIZATION {topup.organization_id}")
            from app.services.organization_credit_service import OrganizationCreditService
            OrganizationCreditService.process_transaction(
                session=db,
                org_id=topup.organization_id,
                amount=topup.ai_credits,
                transaction_type="topup",
                description=f"Top-up via {provider_name} - ₦{topup.amount_naira:,.2f}",
                workspace_id=topup.workspace_id,
                user_id=topup.user_id
            )
        elif topup.workspace_id:
            # Credit workspace wallet
            print(f"DEBUG: Applying top-up of {topup.ai_credits} credits to WORKSPACE {topup.workspace_id}")
            workspace = db.get(Workspace, topup.workspace_id)
            if workspace:
                workspace.credits_balance += topup.ai_credits
                
                # Record workspace transaction
                transaction = WorkspaceCreditTransaction(
                    workspace_id=topup.workspace_id,
                    type="purchase",
                    amount=topup.ai_credits,
                    balance=workspace.credits_balance,
                    description=f"Top-up via {provider_name} - ₦{topup.amount_naira:,.2f}",
                    status="completed",
                )
                db.add(workspace)
                db.add(transaction)
            else:
                # Fallback to user if workspace not found (shouldn't happen)
                print(f"DEBUG: Workspace {topup.workspace_id} not found, falling back to USER {topup.user_id}")
                add_credits(
                    session=db,
                    user_id=topup.user_id,
                    amount=topup.ai_credits,
                    description=f"Top-up via {provider_name} - ₦{topup.amount_naira:,.2f} (Workspace {topup.workspace_id} not found)",
                    reference_id=reference
                )
        else:
            # Credit personal user wallet
            print(f"DEBUG: Applying top-up of {topup.ai_credits} credits to USER {topup.user_id}")
            add_credits(
                session=db,
                user_id=topup.user_id,
                amount=topup.ai_credits,
                description=f"Top-up via {provider_name} - ₦{topup.amount_naira:,.2f}",
                reference_id=reference
            )

        # Create in-app notification for successful top-up
        try:
            create_notification(
                session=db,
                user_id=topup.user_id,
                title="Top-up Successful! 💰",
                description=f"Your top-up of ₦{topup.amount_naira:,.2f} has been processed. {topup.ai_credits:,.2f} credits added.",
                type="topup_success",
                metadata={
                    "topup_id": str(topup.id),
                    "amount_naira": float(topup.amount_naira),
                    "credits": float(topup.ai_credits),
                    "workspace_id": str(topup.workspace_id) if topup.workspace_id else None
                }
            )
        except Exception as e:
            print(f"Failed to create top-up notification: {e}")

        # Send email confirmation
        try:
            from app.services.email_service import email_service
            user = db.get(User, topup.user_id)
            if user:
                email_service.send_credit_purchase_confirmation(
                    email_to=user.email,
                    username=user.full_name or user.email,
                    credits_purchased=float(topup.ai_credits),
                    amount_paid=float(topup.amount_naira),
                    transaction_id=str(topup.id)
                )
        except Exception as e:
            print(f"Failed to send top-up email: {e}")


    async def initiate_topup(
        self,
        amount: float,
        user_id: str,
        email: str,
        db: Session,
        workspace_id: Optional[str] = None,
        organization_id: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initiate a top-up payment.

        Creates bank transfer details and stores the transaction in the database.

        Args:
            amount: Amount in Naira to top up
            user_id: User's unique identifier
            email: User's email address
            db: Database session
            meta: Optional metadata for the transaction

        Returns:
            Dictionary containing bank transfer details and transaction info

        Raises:
            ValueError: If amount is invalid
            Exception: If payment initialization fails
        """
        # Validate amount
        if amount < 100:  # Minimum top-up amount
            raise ValueError("Minimum top-up amount is ₦100")

        # Generate bank transfer details from provider
        transfer_details = await self.provider.generate_bank_transfer_details(
            amount=amount,
            user_id=user_id,
            email=email,
            meta=meta
        )

        # Fetch dynamic rate from platform settings
        from app.models import PlatformSettings
        platform_settings = db.exec(select(PlatformSettings)).first()
        exchange_rate = 1650.0  # Default fallback
        if platform_settings and "payments" in platform_settings.payments:
            exchange_rate = float(platform_settings.payments.get("nairaToCreditRate", 1650.0))
        
        # Calculate AI credits based on conversion rate
        ai_credits = amount / exchange_rate

        # Create TopUp record in database
        topup = TopUp(
            user_id=user_id,
            workspace_id=workspace_id,
            organization_id=organization_id,
            amount_naira=amount,
            ai_credits=ai_credits,
            status=TopUpStatus.PENDING,
            payment_reference=transfer_details["reference"],
            account_number=transfer_details["account_number"],
            bank_name=transfer_details["bank_name"],
            payment_method="bank_transfer",
            expires_at=transfer_details["expires_at"],
            # Store provider-specific data
            monnify_reference=transfer_details.get("order_ref"),  # For compatibility
        )

        db.add(topup)
        db.commit()
        db.refresh(topup)

        print(f"DEBUG: Top-up record created: {topup.id} for user {user_id}. Reference: {topup.payment_reference}, Org: {topup.organization_id}")

        return {
            "topup_id": topup.id,
            "reference": transfer_details["reference"],
            "account_number": transfer_details["account_number"],
            "bank_name": transfer_details["bank_name"],
            "account_name": transfer_details.get("account_name", "Qorebit"),
            "amount": amount,
            "ai_credits": ai_credits,
            "expires_at": transfer_details["expires_at"],
            "provider": self.provider_name,
            "status": TopUpStatus.PENDING,
            "message": f"Transfer ₦{amount:,.2f} to the account above to complete your top-up"
        }

    async def verify_topup(
        self,
        reference: str,
        db: Session
    ) -> Dict[str, Any]:
        """
        Verify a top-up payment and credit the user's account if successful.

        Args:
            reference: Payment reference to verify
            db: Database session

        Returns:
            Dictionary containing verification results

        Raises:
            ValueError: If reference is not found
            Exception: If verification fails
        """
        # Get top-up from database
        topup = db.exec(
            select(TopUp).where(TopUp.payment_reference == reference)
        ).first()

        if not topup:
            # Try once more with col() case-insensitivity or trim if needed
            topup = db.exec(
                select(TopUp).where(TopUp.payment_reference == reference.strip())
            ).first()

        if not topup:
            print(f"DEBUG: Top-up NOT found for reference: {reference}")
            raise ValueError(f"Top-up not found for reference: {reference}")

        # If already completed, return existing status
        if topup.status == TopUpStatus.COMPLETED or topup.status == "completed":
            return {
                "reference": reference,
                "status": "already_completed",
                "message": "This top-up has already been processed",
                "amount": topup.amount_naira,
                "ai_credits": topup.ai_credits
            }

        print(f"DEBUG: Verifying top-up {topup.id}. Current status: {topup.status}, Reference: {reference}")

        # Verify payment with provider
        verification = await self.provider.verify_payment(reference)

        # Update top-up based on verification result
        if verification["status"] == "success":
            topup.status = TopUpStatus.COMPLETED
            topup.paid_at = verification.get("paid_at") or datetime.utcnow()

            # Credit account (workspace or user)
            self._apply_topup_credits(db, topup, self.provider_name, reference)

            db.add(topup)
            db.commit()
            db.refresh(topup)

            return {
                "reference": reference,
                "status": "success",
                "message": f"Payment verified! {topup.ai_credits:,.2f} AI credits added to your account",
                "amount": topup.amount_naira,
                "ai_credits": topup.ai_credits,
                "paid_at": topup.paid_at
            }

        elif verification["status"] == "failed":
            topup.status = TopUpStatus.FAILED
            db.add(topup)
            db.commit()

            return {
                "reference": reference,
                "status": "failed",
                "message": "Payment verification failed",
                "amount": topup.amount_naira
            }

        else:  # pending
            return {
                "reference": reference,
                "status": "pending",
                "message": "Payment is still pending. Please complete the transfer.",
                "amount": topup.amount_naira
            }

    async def process_webhook(
        self,
        payload: Dict[str, Any],
        signature: str,
        raw_payload: bytes,
        db: Session
    ) -> Dict[str, Any]:
        """
        Process incoming webhook from payment provider with Redis deduplication.
        """
        from app.core.redis import redis_client
        import json
        
        # 1. Unpack reference early for deduplication
        if self.provider_name == "flutterwave":
             reference = payload.get("data", {}).get("tx_ref")
        else: # monnify
             reference = payload.get("eventData", {}).get("transactionReference")
             
        if reference:
            # Use Redis as a fast deduplication lock (expires in 12 hours)
            lock_key = f"webhook_lock:{reference}"
            if await redis_client.get(lock_key):
                print(f"DEBUG: Webhook {reference} already being processed or completed (Redis lock hit). Ignoring.")
                return {"status": "ignored", "message": "Duplicate event processed via Redis", "reference": reference}
            
            # Set a transient lock while processing
            await redis_client.set(lock_key, "processing", ex=43200)

        # 2. Validate webhook signature
        is_valid = await self.provider.validate_webhook_signature(
            payload=raw_payload,
            signature=signature
        )

        if not is_valid:
            raise ValueError("Invalid webhook signature")

        # Extract transaction reference based on provider
        if self.provider_name == "flutterwave":
            reference = payload.get("data", {}).get("tx_ref")
            status = payload.get("data", {}).get("status", "").lower()
            amount = float(payload.get("data", {}).get("amount", 0))

        elif self.provider_name == "monnify":
            transaction_data = payload.get("eventData", {})
            reference = transaction_data.get("transactionReference")
            status = transaction_data.get("paymentStatus", "").upper()
            amount = float(transaction_data.get("amountPaid", 0))

        else:
            raise ValueError(f"Unsupported provider: {self.provider_name}")

        if not reference:
            raise ValueError("No transaction reference found in webhook payload")

        # Map provider status to our standard status
        if self.provider_name == "flutterwave":
            our_status = "success" if status == "successful" else "pending"
        else:  # monnify
            our_status = "success" if status == "PAID" else "pending"

        # Only process successful payments
        if our_status != "success":
            return {
                "status": "ignored",
                "message": f"Webhook received but payment not successful: {status}",
                "reference": reference
            }

        # Find matching top-up
        topup = db.exec(
            select(TopUp).where(TopUp.payment_reference == reference)
        ).first()

        print(f"DEBUG: Webhook lookup for reference {reference}. Found: {topup.id if topup else 'None'}")

        # For Monnify, the webhook reference is Monnify's internal transaction ID,
        # which won't match our generated TopUp payment_reference.
        # We must find the user's pending top-up matching the paid amount.
        if not topup and self.provider_name == "monnify":
            transaction_data = payload.get("eventData", {})
            # For reserved accounts, product.reference contains our user_id
            product_ref = transaction_data.get("product", {}).get("reference")
            customer_email = transaction_data.get("customer", {}).get("email")
            
            # Find a pending topup for this user (or email) and exact amount
            if product_ref:
                topup = db.exec(
                    select(TopUp)
                    .where(TopUp.user_id == product_ref)
                    .where(TopUp.amount_naira == amount)
                    .where(TopUp.status == TopUpStatus.PENDING)
                    .order_by(TopUp.created_at.desc())
                ).first()
        if topup:
            # If already completed, return existing status
            if topup.status == TopUpStatus.COMPLETED or topup.status == "completed":
                return {
                    "status": "already_processed",
                    "message": "This payment has already been processed",
                    "reference": reference
                }
        else:
            print(f"DEBUG: Webhook lookup FAILED for reference {reference}. Checking Flutterwave fallback...")

        # Fallback for Flutterwave as well if reference doesn't match
        if not topup and self.provider_name == "flutterwave":
            customer_email = payload.get("data", {}).get("customer", {}).get("email")
            print(f"DEBUG: Flutterwave webhook fallback checking email: {customer_email}, amount: {amount}")
            if customer_email:
                # Find the user by email
                from app.models import User
                user = db.exec(select(User).where(User.email == customer_email)).first()
                if user:
                    # Find a pending topup for this user and exact amount
                    # Using abs() for amount to handle slight floating point differences if any (though Decimal is used in DB)
                    statement = select(TopUp).where(
                        TopUp.user_id == user.id,
                        TopUp.status == TopUpStatus.PENDING,
                    ).order_by(TopUp.created_at.desc())
                    
                    found_topups = db.exec(statement).all()
                    for t in found_topups:
                        # Allow 1 Naira difference for rounding if necessary (though usually exact)
                        if abs(float(t.amount_naira) - amount) < 1.0:
                            topup = t
                            print(f"DEBUG: Found top-up {topup.id} via fallback email lookup for {customer_email}. Amount match: {t.amount_naira} ~= {amount}")
                            break
                    
                    if not topup:
                        print(f"DEBUG: Fallback search found user {user.id} but no pending top-up with amount {amount}")

        if not topup:
            print(f"DEBUG: CRITICAL - Webhook could not be associated with any TopUp record. Reference: {reference}, Email: {payload.get('data', {}).get('customer', {}).get('email')}")
            # Fetch dynamic rate from platform settings
            from app.models import PlatformSettings
            platform_settings = db.exec(select(PlatformSettings)).first()
            exchange_rate = 1650.0  # Default fallback
            if platform_settings and "payments" in platform_settings.payments:
                exchange_rate = float(platform_settings.payments.get("nairaToCreditRate", 1650.0))

            ai_credits = amount / exchange_rate

            # Get user from webhook
            user_id = "unknown"
            if self.provider_name == "monnify":
                user_id = payload.get("eventData", {}).get("product", {}).get("reference") or "unknown"
            else:
                # For Flutterwave, if topup not found, try to extract user_id from tx_ref
                # tx_ref format is QRB-FLW-{user_id}-{timestamp}
                if reference and reference.startswith("QRB-FLW-"):
                    parts = reference.split("-")
                    if len(parts) >= 4:
                        # QRB, FLW, UUID, TIMESTAMP -> parts[2] is user_id
                        user_id = parts[2]
                
                # If extraction failed, fallback to customer email lookup if possible
                if user_id == "unknown":
                    customer_email = payload.get("data", {}).get("customer", {}).get("email")
                    if customer_email:
                        from app.models import User
                        user = db.exec(select(User).where(User.email == customer_email)).first()
                        if user:
                            user_id = str(user.id)
                
                # If still unknown, we have a problem, but let's not use the FLW integer ID
                if user_id == "unknown":
                    user_id = payload.get("data", {}).get("customer", {}).get("id") or "unknown"
                
            topup = TopUp(
                user_id=user_id,
                amount_naira=amount,
                ai_credits=ai_credits,
                status=TopUpStatus.COMPLETED,
                payment_reference=reference,
                paid_at=datetime.utcnow(),
                payment_method="bank_transfer"
            )
            db.add(topup)

        # Update top-up status
        topup.status = TopUpStatus.COMPLETED
        topup.paid_at = datetime.utcnow()

        # Credit account (workspace or user)
        self._apply_topup_credits(db, topup, self.provider_name, reference)

        db.add(topup)
        db.commit()
        db.refresh(topup)

        return {
            "status": "success",
            "message": f"Payment processed successfully. {topup.ai_credits:,.2f} credits added.",
            "reference": reference,
            "amount": topup.amount_naira,
            "ai_credits": topup.ai_credits
        }

    async def get_topup_status(
        self,
        topup_id: int,
        db: Session
    ) -> Dict[str, Any]:
        """
        Get the status of a top-up transaction.

        Args:
            topup_id: Top-up transaction ID
            db: Database session

        Returns:
            Dictionary containing top-up status

        Raises:
            ValueError: If top-up not found
        """
        topup = db.get(TopUp, topup_id)

        if not topup:
            raise ValueError(f"Top-up not found: {topup_id}")

        # If still pending, check with provider
        if topup.status == TopUpStatus.PENDING or topup.status == "pending":
            try:
                verification = await self.provider.verify_payment(
                    topup.payment_reference
                )

                if verification["status"] == "success":
                    # Payment was completed, update record
                    topup.status = TopUpStatus.COMPLETED
                    topup.paid_at = verification.get("paid_at") or datetime.utcnow()

                    # Credit account (workspace or user)
                    self._apply_topup_credits(db, topup, self.provider_name, topup.payment_reference)

                    db.add(topup)
                    db.commit()
                    db.refresh(topup)
                elif verification["status"] == "failed":
                    # Explicitly mark as failed if the provider says so
                    topup.status = TopUpStatus.FAILED
                    db.add(topup)
                    db.commit()

            except Exception as e:
                # If verification fails, keep current status (PENDING)
                # Use a cleaner log message without stack trace for expected polling errors
                pass 

        return {
            "topup_id": topup.id,
            "reference": topup.payment_reference,
            "status": topup.status,
            "amount": topup.amount_naira,
            "ai_credits": topup.ai_credits,
            "account_number": topup.account_number,
            "bank_name": topup.bank_name,
            "created_at": topup.created_at,
            "paid_at": topup.paid_at,
            "expires_at": topup.expires_at,
            "provider": self.provider_name
        }


# Singleton instance for easy access
payment_service = PaymentService()
