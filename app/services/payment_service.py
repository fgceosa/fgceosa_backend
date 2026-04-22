import logging
import uuid
import httpx
from datetime import datetime, timezone
from typing import Any, Dict, Optional
from decimal import Decimal
from sqlmodel import Session, select
from app.core.config import settings
from app.models import Payment, User

logger = logging.getLogger(__name__)

class PaymentService:
    def __init__(self):
        self.base_url = settings.FLW_BASE_URL
        self.secret_key = settings.FLW_SECRET_KEY
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

    async def initialize_payment(
        self, 
        session: Session, 
        user: User, 
        amount: Decimal, 
        description: str,
        callback_url: str
    ) -> Dict[str, Any]:
        """
        Initialize a payment with Flutterwave
        """
        tx_ref = f"FGCEOSA-{uuid.uuid4().hex[:8].upper()}-{int(datetime.now().timestamp())}"
        
        # Create pending payment record
        db_payment = Payment(
            user_id=user.id,
            amount=amount,
            transaction_reference=tx_ref,
            description=description,
            status="pending"
        )
        session.add(db_payment)
        session.commit()
        session.refresh(db_payment)

        payload = {
            "tx_ref": tx_ref,
            "amount": str(amount),
            "currency": "NGN",
            "redirect_url": callback_url,
            "customer": {
                "email": user.email,
                "name": user.full_name or user.email,
                "phonenumber": user.phone or ""
            },
            "customizations": {
                "title": "FGCEOSA Payments",
                "description": description,
                "logo": f"{settings.FRONTEND_HOST}/logo.png"
            }
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/payments",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()
                
                if data.get("status") == "success":
                    return {
                        "status": "success",
                        "payment_url": data["data"]["link"],
                        "transaction_reference": tx_ref
                    }
                else:
                    logger.error(f"Flutterwave initialization failed: {data}")
                    return {"status": "error", "message": "Could not initialize payment"}
            except Exception as e:
                logger.error(f"Payment initialization error: {e}")
                return {"status": "error", "message": str(e)}

    async def verify_transaction(self, session: Session, transaction_id: str) -> Dict[str, Any]:
        """
        Verify a transaction with Flutterwave using their transaction ID
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{self.base_url}/transactions/{transaction_id}/verify",
                    headers=self.headers,
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                if data.get("status") == "success" and data["data"]["status"] == "successful":
                    flw_data = data["data"]
                    tx_ref = flw_data["tx_ref"]
                    amount = Decimal(str(flw_data["amount"]))
                    
                    # Find payment in DB
                    statement = select(Payment).where(Payment.transaction_reference == tx_ref)
                    db_payment = session.exec(statement).first()
                    
                    if db_payment:
                        if db_payment.status != "completed":
                            db_payment.status = "completed"
                            db_payment.flutterwave_id = str(transaction_id)
                            db_payment.payment_method = flw_data.get("payment_type")
                            db_payment.updated_at = datetime.now(timezone.utc)
                            session.add(db_payment)
                            
                            # Notify Admins of successful online payment
                            try:
                                from app.utils.notifications import notify_admins
                                # Get user for name
                                user = session.get(User, db_payment.user_id)
                                notify_admins(
                                    session=session,
                                    title="Online Payment Received",
                                    description=f"{user.full_name or user.email} paid ₦{amount:,.0f} via {db_payment.payment_method or 'Online Payment'}.",
                                    notification_type="success",
                                    metadata={
                                        "payment_id": str(db_payment.id),
                                        "user_id": str(user.id),
                                        "type": "online_payment"
                                    }
                                )
                            except Exception as notif_err:
                                logger.error(f"Failed to notify admins of online payment: {notif_err}")

                            # Notify Member
                            try:
                                from app.utils.notifications import create_notification
                                create_notification(
                                    session=session,
                                    user_id=user.id,
                                    title="Payment Confirmed",
                                    description=f"Your payment of ₦{amount:,.0f} has been successfully verified. Thank you!",
                                    notification_type="success",
                                    metadata={
                                        "payment_id": str(db_payment.id),
                                        "type": "payment_confirmed"
                                    }
                                )
                            except Exception as member_notif_err:
                                logger.error(f"Failed to notify member of payment confirmation: {member_notif_err}")

                            session.commit()
                            session.refresh(db_payment)
                            logger.info(f"Payment {tx_ref} verified and marked as completed.")
                        
                        return {"status": "success", "payment": db_payment}
                    else:
                        logger.warning(f"Payment with ref {tx_ref} not found in database during verification.")
                        return {"status": "error", "message": "Payment record not found"}
                else:
                    return {"status": "error", "message": "Transaction verification failed or unsuccessful"}
            except Exception as e:
                logger.error(f"Transaction verification error: {e}")
                return {"status": "error", "message": str(e)}

payment_service = PaymentService()
from datetime import datetime, timezone
