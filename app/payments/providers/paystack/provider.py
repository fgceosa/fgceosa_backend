"""
Paystack Payment Provider Implementation.

This module implements the PaymentProviderProtocol for Paystack API,
supporting transaction initialization, verification, and webhook processing.
"""

import hmac
import hashlib
import httpx
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.config import settings
from app.payments.providers.paystack.exceptions import (
    PaystackException,
    PaystackAuthenticationException,
    PaystackPaymentException
)


class PaystackProvider:
    """
    Paystack payment provider implementation.
    """

    provider_name = "paystack"

    def __init__(self, secret_key: Optional[str] = None, public_key: Optional[str] = None):
        """Initialize Paystack provider with API credentials."""
        self.secret_key = secret_key or settings.PAYSTACK_SECRET_KEY
        self.public_key = public_key or settings.PAYSTACK_PUBLIC_KEY
        self.base_url = settings.PAYSTACK_BASE_URL
        self.webhook_secret = settings.PAYSTACK_WEBHOOK_SECRET or self.secret_key

        self.is_test_mode = "test" in self.secret_key.lower() if self.secret_key else True

        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

        # Log initialization
        key_type = "TEST" if self.is_test_mode else "LIVE"
        print(f"✅ Paystack Provider initialized ({key_type} mode)")
        print(f"   Base URL: {self.base_url}")

    async def initialize_payment(
        self,
        amount: float,
        user_id: str,
        email: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a Paystack payment.
        """
        try:
            reference = self._generate_reference(user_id)

            payload = {
                "reference": reference,
                "amount": str(int(amount * 100)), # Paystack requires amount in kobo (base currency units)
                "email": email,
                "callback_url": meta.get("redirect_url") if meta else None,
                "metadata": meta or {}
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/transaction/initialize",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code != 200:
                    raise PaystackPaymentException(
                        f"Payment initialization failed: {response.text}"
                    )

                result = response.json()

                if not result.get("status"):
                    raise PaystackPaymentException(
                        f"Payment initialization failed: {result.get('message')}"
                    )

                data = result.get("data", {})

                return {
                    "reference": data.get("reference", reference),
                    "status": "initialized",
                    "message": "Payment initialized successfully",
                    "data": {
                        "authorization_url": data.get("authorization_url"),
                        "access_code": data.get("access_code"),
                        "reference": data.get("reference", reference)
                    }
                }

        except httpx.HTTPError as e:
            raise PaystackException(f"HTTP error during payment initialization: {str(e)}")
        except Exception as e:
            raise PaystackException(f"Error initializing payment: {str(e)}")

    async def generate_bank_transfer_details(
        self,
        amount: float,
        user_id: str,
        email: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate virtual account for bank transfer payment.
        Using Paystack Dedicated Virtual Account or similar API.
        For a one-off payment, Paystack requires using the charge API with bank transfer channel, 
        but usually it is handled via the initialized checkout. If specifically required,
        we return an exception or integrate Dedicated Virtual Accounts.
        """
        raise NotImplementedError("Bank transfer generation is typically handled via Paystack Checkout. Use initialize_payment instead.")

    async def verify_payment(self, reference: str) -> Dict[str, Any]:
        """
        Verify a payment transaction using Paystack API.
        """
        try:
            async with httpx.AsyncClient() as client:
                print(f"DEBUG: Calling Paystack verify for {reference}")
                response = await client.get(
                    f"{self.base_url}/transaction/verify/{reference}",
                    headers=self.headers,
                    timeout=30.0
                )
                print(f"DEBUG: Paystack response status: {response.status_code}")

                if response.status_code != 200:
                    try:
                        error_data = response.json()
                        message = error_data.get("message", "")
                        if "not found" in message.lower():
                            return {
                                "reference": reference,
                                "status": "pending",
                                "amount": 0,
                                "paid_at": None,
                                "currency": "NGN",
                                "customer_email": None,
                                "meta": {}
                            }
                    except Exception:
                        pass

                    raise PaystackPaymentException(
                        f"Payment verification failed with status {response.status_code}: {response.text}"
                    )

                result = response.json()

                if not result.get("status"):
                    return {
                        "reference": reference,
                        "status": "failed",
                        "amount": 0,
                        "paid_at": None,
                        "currency": "NGN",
                        "customer_email": None,
                        "meta": {}
                    }

                data = result.get("data", {})

                ps_status = data.get("status", "").lower()
                our_status = self._map_status(ps_status)
                
                paid_at = None
                if data.get("paid_at"):
                    paid_at = datetime.fromisoformat(data.get("paid_at").replace("Z", "+00:00"))

                return {
                    "reference": data.get("reference", reference),
                    "status": our_status,
                    "amount": float(data.get("amount", 0)) / 100.0, # Convert back to Naira
                    "paid_at": paid_at,
                    "currency": data.get("currency", "NGN"),
                    "customer_email": data.get("customer", {}).get("email"),
                    "payment_type": data.get("channel"),
                    "meta": data.get("metadata", {})
                }

        except httpx.HTTPError as e:
            raise PaystackException(f"HTTP error during payment verification: {str(e)}")
        except Exception as e:
            raise PaystackException(f"Error verifying payment: {str(e)}")

    async def validate_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Validate Paystack webhook signature.
        """
        try:
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()
            return hmac.compare_digest(expected_signature, signature)
        except Exception as e:
            print(f"Error validating webhook signature: {str(e)}")
            return False

    async def get_transaction_details(self, reference: str) -> Dict[str, Any]:
        """
        Get detailed transaction information.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/transaction/verify/{reference}",
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code != 200:
                    raise PaystackPaymentException(
                        f"Failed to get transaction details: {response.text}"
                    )

                result = response.json()

                if not result.get("status"):
                    raise PaystackPaymentException(
                        f"Transaction not found: {reference}"
                    )

                return result.get("data", {})

        except httpx.HTTPError as e:
            raise PaystackException(
                f"HTTP error getting transaction details: {str(e)}"
            )
        except Exception as e:
            raise PaystackException(
                f"Error getting transaction details: {str(e)}"
            )

    def _generate_reference(self, user_id: str) -> str:
        """Generate a unique payment reference."""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"FGCEOSA-PSTK-{user_id}-{timestamp}"

    def _map_status(self, status: str) -> str:
        """Map Paystack status to standard status."""
        status_map = {
            "success": "success",
            "abandoned": "failed",
            "failed": "failed",
            "pending": "pending",
            "reversed": "failed",
        }
        return status_map.get(status.lower(), "pending")
