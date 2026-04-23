import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from decimal import Decimal
from sqlmodel import Session, select

from app.core.config import settings
from app.models import Payment, User
from app.payments.payment_factory import PaymentFactory

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.provider = PaymentFactory.get_provider()
        self.provider_name = PaymentFactory.get_provider_name()

    async def initialize_payment(
        self, 
        session: Session, 
        user: User, 
        amount: Decimal, 
        description: str,
        callback_url: str
    ) -> Dict[str, Any]:
        """
        Initialize a payment with the active provider (Paystack)
        """
        # Create pending payment record
        # Note: We generate the reference via the provider in its own logic or here
        # For consistency with the existing flow, we'll let the provider handle it or pass one
        
        meta = {
            "redirect_url": callback_url,
            "customer_name": user.full_name or user.email,
            "description": description
        }

        try:
            result = await self.provider.initialize_payment(
                amount=float(amount),
                user_id=str(user.id),
                email=user.email,
                meta=meta
            )
            
            tx_ref = result["reference"]
            
            db_payment = Payment(
                user_id=user.id,
                amount=amount,
                transaction_reference=tx_ref,
                description=description,
                status="pending",
                payment_method=self.provider_name
            )
            session.add(db_payment)
            session.commit()
            session.refresh(db_payment)

            # Map to the format the frontend expects
            payment_data = result.get("data", {})
            payment_url = payment_data.get("authorization_url") or payment_data.get("link")

            return {
                "status": "success",
                "payment_url": payment_url,
                "transaction_reference": tx_ref
            }
        except Exception as e:
            logger.error(f"Payment initialization error: {e}")
            return {"status": "error", "message": str(e)}

    async def verify_transaction(self, session: Session, transaction_id: str) -> Dict[str, Any]:
        """
        Verify a transaction with the active provider using their transaction reference/ID
        """
        try:
            # Paystack usually returns the reference in the URL as 'reference'
            # The frontend should pass this as 'transaction_id' to this endpoint
            verification = await self.provider.verify_payment(transaction_id)

            if verification["status"] == "success":
                amount = Decimal(str(verification["amount"]))
                tx_ref = verification["reference"]
                
                # Find payment in DB
                statement = select(Payment).where(Payment.transaction_reference == tx_ref)
                db_payment = session.exec(statement).first()
                
                if not db_payment:
                    # Fallback: maybe the transaction_id itself is in our DB?
                    statement = select(Payment).where(Payment.transaction_reference == transaction_id)
                    db_payment = session.exec(statement).first()

                if db_payment:
                    if db_payment.status != "completed":
                        db_payment.status = "completed"
                        # Use paystack_id instead of flutterwave_id
                        if hasattr(db_payment, "paystack_id"):
                            db_payment.paystack_id = str(transaction_id)
                        db_payment.payment_method = verification.get("payment_type") or self.provider_name
                        db_payment.updated_at = datetime.now(timezone.utc)
                        session.add(db_payment)
                        
                        # Notify Admins
                        try:
                            from app.utils.notifications import notify_admins
                            user = session.get(User, db_payment.user_id)
                            notify_admins(
                                session=session,
                                title="Online Payment Received",
                                description=f"{user.full_name or user.email} paid ₦{amount:,.0f} via {db_payment.payment_method}.",
                                notification_type="success",
                                metadata={
                                    "payment_id": str(db_payment.id),
                                    "user_id": str(user.id),
                                    "type": "online_payment"
                                }
                            )
                        except Exception as notif_err:
                            logger.error(f"Failed to notify admins: {notif_err}")

                        # Notify Member
                        try:
                            from app.utils.notifications import create_notification
                            create_notification(
                                session=session,
                                user_id=db_payment.user_id,
                                title="Payment Confirmed",
                                description=f"Your payment of ₦{amount:,.0f} has been successfully verified. Thank you!",
                                notification_type="success",
                                metadata={
                                    "payment_id": str(db_payment.id),
                                    "type": "payment_confirmed"
                                }
                            )
                        except Exception as member_notif_err:
                            logger.error(f"Failed to notify member: {member_notif_err}")

                        session.commit()
                        session.refresh(db_payment)
                    
                    return {"status": "success", "payment": db_payment}
                else:
                    return {"status": "error", "message": "Payment record not found"}
            else:
                return {"status": "error", "message": verification.get("message", "Verification failed")}
        except Exception as e:
            logger.error(f"Transaction verification error: {e}")
            return {"status": "error", "message": str(e)}

payment_service = PaymentService()

