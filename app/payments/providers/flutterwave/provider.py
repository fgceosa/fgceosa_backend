"""
Flutterwave Payment Provider Implementation (V3 API).

This module implements the PaymentProviderProtocol for Flutterwave V3 API,
supporting virtual account (bank transfer) payments and webhooks.
"""

import hmac
import hashlib
import httpx
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.config import settings
from app.payments.providers.flutterwave.exceptions import (
    FlutterwaveException,
    FlutterwaveAuthenticationException,
    FlutterwavePaymentException
)


class FlutterwaveProvider:
    """
    Flutterwave V3 payment provider implementation.

    Handles virtual account creation, payment verification, and webhook processing.

    Supports both TEST and LIVE API keys:
    - TEST keys: FLWSECK_TEST-...
    - LIVE keys: FLWSECK-...
    """

    provider_name = "flutterwave"

    def __init__(self):
        """Initialize Flutterwave V3 provider with API credentials."""
        self.secret_key = settings.FLW_SECRET_KEY
        self.public_key = settings.FLW_PUBLIC_KEY
        self.base_url = settings.FLW_BASE_URL
        self.webhook_secret = settings.FLW_WEBHOOK_SECRET

        # Detect if using test or live keys
        self.is_test_mode = "TEST" in self.secret_key

        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }

        # Log initialization
        key_type = "TEST" if self.is_test_mode else "LIVE"
        print(f"✅ Flutterwave V3 Provider initialized ({key_type} mode)")
        print(f"   Base URL: {self.base_url}")

    async def initialize_payment(
        self,
        amount: float,
        user_id: str,
        email: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a Flutterwave payment.

        Args:
            amount: Amount in Naira
            user_id: User's unique identifier
            email: User's email
            meta: Optional metadata

        Returns:
            Payment initialization details
        """
        try:
            reference = self._generate_reference(user_id)

            payload = {
                "tx_ref": reference,
                "amount": str(amount),
                "currency": "NGN",
                "redirect_url": meta.get("redirect_url") if meta else None,
                "customer": {
                    "email": email,
                    "name": meta.get("customer_name", email.split("@")[0]) if meta else email.split("@")[0],
                },
                "customizations": {
                    "title": "Qorebit Credit Top-up",
                    "description": f"Add ₦{amount} to your Qorebit wallet",
                    "logo": meta.get("logo_url") if meta else None,
                },
                "meta": meta or {}
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/payments",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code != 200:
                    raise FlutterwavePaymentException(
                        f"Payment initialization failed: {response.text}"
                    )

                result = response.json()

                if result.get("status") != "success":
                    raise FlutterwavePaymentException(
                        f"Payment initialization failed: {result.get('message')}"
                    )

                return {
                    "reference": reference,
                    "status": "initialized",
                    "message": "Payment initialized successfully",
                    "data": result.get("data", {})
                }

        except httpx.HTTPError as e:
            raise FlutterwaveException(f"HTTP error during payment initialization: {str(e)}")
        except Exception as e:
            raise FlutterwaveException(f"Error initializing payment: {str(e)}")

    async def generate_bank_transfer_details(
        self,
        amount: float,
        user_id: str,
        email: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate virtual account for bank transfer payment.

        Flutterwave creates a unique virtual account number for the user
        to make bank transfers.

        Args:
            amount: Amount in Naira
            user_id: User's unique identifier
            email: User's email
            meta: Optional metadata

        Returns:
            Virtual account details for bank transfer
        """
        try:
            reference = self._generate_reference(user_id)

            # Create virtual account number for this transaction
            payload = {
                "email": email,
                "is_permanent": False,  # Temporary account for this transaction
                "tx_ref": reference,
                "amount": amount,
                "frequency": 1,  # Single use
                "narration": f"Qorebit Top-up - {reference}",
            }

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/virtual-account-numbers",
                    json=payload,
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code not in [200, 201]:
                    raise FlutterwavePaymentException(
                        f"Virtual account creation failed: {response.text}"
                    )

                result = response.json()

                if result.get("status") != "success":
                    raise FlutterwavePaymentException(
                        f"Virtual account creation failed: {result.get('message')}"
                    )

                data = result.get("data", {})

                # Calculate expiration (24 hours from now)
                expires_at = datetime.utcnow() + timedelta(hours=24)

                return {
                    "reference": reference,
                    "account_number": data.get("account_number"),
                    "bank_name": data.get("bank_name", "Wema Bank"),
                    "account_name": data.get("account_name", "Qorebit"),
                    "amount": amount,
                    "expires_at": expires_at,
                    "provider": self.provider_name,
                    "response_code": data.get("response_code"),
                    "order_ref": data.get("order_ref")
                }

        except httpx.HTTPError as e:
            raise FlutterwaveException(
                f"HTTP error during virtual account creation: {str(e)}"
            )
        except Exception as e:
            raise FlutterwaveException(
                f"Error generating bank transfer details: {str(e)}"
            )

    async def verify_payment(self, reference: str) -> Dict[str, Any]:
        """
        Verify a payment transaction using Flutterwave API.

        Args:
            reference: Payment transaction reference

        Returns:
            Payment verification details
        """
        try:
            async with httpx.AsyncClient() as client:
                print(f"DEBUG: Calling Flutterwave verify_by_reference for {reference}")
                # Verify using transaction reference
                response = await client.get(
                    f"{self.base_url}/transactions/verify_by_reference",
                    params={"tx_ref": reference},
                    headers=self.headers,
                    timeout=30.0
                )
                print(f"DEBUG: Flutterwave response status: {response.status_code}")

                if response.status_code != 200:
                    # Check if this is just a "not found" case (common for bank transfers that hasn't landed yet)
                    try:
                        error_data = response.json()
                        
                        # Fallback: Try searching the transaction list instead
                        # Sometimes transactions are found in the list even when verify_by_reference fails
                        list_response = await client.get(
                            f"{self.base_url}/transactions",
                            params={"tx_ref": reference},
                            headers=self.headers,
                            timeout=30.0
                        )
                        
                        if list_response.status_code == 200:
                            list_data = list_response.json()
                            transactions = list_data.get("data", [])
                            if transactions:
                                # Found at least one transaction for this reference
                                data = transactions[0]
                                print(f"DEBUG: Found transaction in fallback search for {reference}! ID: {data.get('id')}, Status: {data.get('status')}")
                                
                                flw_status = data.get("status", "").lower()
                                our_status = self._map_status(flw_status)
                                
                                return {
                                    "reference": reference,
                                    "status": our_status,
                                    "amount": float(data.get("amount", 0)),
                                    "paid_at": datetime.fromisoformat(
                                        data.get("created_at").replace("Z", "+00:00")
                                    ) if data.get("created_at") else None,
                                    "currency": data.get("currency", "NGN"),
                                    "customer_email": data.get("customer", {}).get("email"),
                                    "payment_type": data.get("payment_type"),
                                    "meta": data.get("meta", {})
                                }
                        
                        message = error_data.get("message", "")
                        if "No transaction was found" in message or "not found" in message.lower():
                            # Don't log as failure, this is expected for pending transfers
                            return {
                                "reference": reference,
                                "status": "pending",
                                "amount": 0,
                                "paid_at": None,
                                "currency": "NGN",
                                "customer_email": None,
                                "meta": {}
                            }
                    except Exception as json_err:
                        # Fallback to general error if JSON parsing fails
                        pass

                    raise FlutterwavePaymentException(
                        f"Payment verification failed with status {response.status_code}: {response.text}"
                    )

                result = response.json()

                if result.get("status") != "success":
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

                # Map Flutterwave status to our standard status
                flw_status = data.get("status", "").lower()
                our_status = self._map_status(flw_status)

                return {
                    "reference": reference,
                    "status": our_status,
                    "amount": float(data.get("amount", 0)),
                    "paid_at": datetime.fromisoformat(
                        data.get("created_at").replace("Z", "+00:00")
                    ) if data.get("created_at") else None,
                    "currency": data.get("currency", "NGN"),
                    "customer_email": data.get("customer", {}).get("email"),
                    "payment_type": data.get("payment_type"),
                    "meta": data.get("meta", {})
                }

        except httpx.HTTPError as e:
            raise FlutterwaveException(f"HTTP error during payment verification: {str(e)}")
        except Exception as e:
            raise FlutterwaveException(f"Error verifying payment: {str(e)}")

    async def validate_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Validate Flutterwave webhook signature.

        Flutterwave sends a signature in the 'verif-hash' header.
        We verify this matches our configured webhook secret.

        Args:
            payload: Raw webhook payload (not used for Flutterwave)
            signature: Signature from 'verif-hash' header

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Flutterwave uses a simple hash comparison
            # The signature should match the webhook secret hash
            return signature == self.webhook_secret

        except Exception as e:
            print(f"Error validating webhook signature: {str(e)}")
            return False

    async def get_transaction_details(self, reference: str) -> Dict[str, Any]:
        """
        Get detailed transaction information.

        Args:
            reference: Transaction reference

        Returns:
            Complete transaction details
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/transactions/verify_by_reference",
                    params={"tx_ref": reference},
                    headers=self.headers,
                    timeout=30.0
                )

                if response.status_code != 200:
                    raise FlutterwavePaymentException(
                        f"Failed to get transaction details: {response.text}"
                    )

                result = response.json()

                if result.get("status") != "success":
                    raise FlutterwavePaymentException(
                        f"Transaction not found: {reference}"
                    )

                return result.get("data", {})

        except httpx.HTTPError as e:
            raise FlutterwaveException(
                f"HTTP error getting transaction details: {str(e)}"
            )
        except Exception as e:
            raise FlutterwaveException(
                f"Error getting transaction details: {str(e)}"
            )

    def _generate_reference(self, user_id: str) -> str:
        """
        Generate a unique payment reference.

        Args:
            user_id: User's unique identifier

        Returns:
            Unique payment reference
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"QRB-FLW-{user_id}-{timestamp}"

    def _map_status(self, flw_status: str) -> str:
        """
        Map Flutterwave status to our standard status.

        Args:
            flw_status: Flutterwave transaction status

        Returns:
            Standardized status string
        """
        status_map = {
            "successful": "success",
            "success": "success",
            "completed": "success",
            "pending": "pending",
            "failed": "failed",
            "cancelled": "failed",
            "abandoned": "failed"
        }

        return status_map.get(flw_status.lower(), "pending")
