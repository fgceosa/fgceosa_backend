"""
Monnify Payment Provider Implementation.

This module wraps the Monnify client to implement the PaymentProviderProtocol.
Provides plug-and-play support for Monnify as a payment gateway.
"""

import hmac
import hashlib
from typing import Dict, Any, Optional
from datetime import datetime, timedelta
from app.core.config import settings
from app.payments.providers.monnify.client import monnify_client


class MonnifyProvider:
    """
    Monnify payment provider implementation.

    Wraps Monnify client to match PaymentProviderProtocol interface.
    """

    provider_name = "monnify"

    def __init__(self):
        """Initialize Monnify provider."""
        self.client = monnify_client
        self.webhook_secret = settings.MONNIFY_WEBHOOK_SECRET

    async def initialize_payment(
        self,
        amount: float,
        user_id: str,
        email: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a Monnify payment (creates reserved account).

        Args:
            amount: Amount in Naira
            user_id: User's unique identifier
            email: User's email
            meta: Optional metadata

        Returns:
            Payment initialization details
        """
        reference = self._generate_reference(user_id)

        # Create or get reserved account
        account_details = await self.client.create_reserved_account(
            account_reference=user_id,
            account_name=meta.get("customer_name", email.split("@")[0]) if meta else email.split("@")[0],
            customer_email=email,
            customer_name=meta.get("customer_name", email.split("@")[0]) if meta else email.split("@")[0]
        )

        return {
            "reference": reference,
            "status": "initialized",
            "message": "Payment initialized successfully",
            "data": account_details
        }

    async def generate_bank_transfer_details(
        self,
        amount: float,
        user_id: str,
        email: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate bank transfer details using Monnify reserved account.

        Args:
            amount: Amount in Naira
            user_id: User's unique identifier
            email: User's email
            meta: Optional metadata

        Returns:
            Bank transfer details
        """
        reference = self._generate_reference(user_id)

        # Get or create reserved account
        account_details = await self.client.get_reserved_account(user_id)

        if not account_details:
            # Create new reserved account if doesn't exist
            account_details = await self.client.create_reserved_account(
                account_reference=user_id,
                account_name=meta.get("customer_name", email.split("@")[0]) if meta else email.split("@")[0],
                customer_email=email,
                customer_name=meta.get("customer_name", email.split("@")[0]) if meta else email.split("@")[0]
            )

        # Monnify accounts are permanent, so we use the first account
        accounts = account_details.get("accounts", [])
        account = accounts[0] if accounts else {}

        expires_at = datetime.utcnow() + timedelta(hours=24)

        return {
            "reference": reference,
            "account_number": account.get("accountNumber"),
            "bank_name": account.get("bankName"),
            "account_name": account.get("accountName"),
            "amount": amount,
            "expires_at": expires_at,
            "provider": self.provider_name,
            "account_reference": account_details.get("accountReference")
        }

    async def verify_payment(self, reference: str) -> Dict[str, Any]:
        """
        Verify a Monnify payment transaction.

        Args:
            reference: Payment reference

        Returns:
            Payment verification details
        """
        try:
            # Verify transaction using Monnify API
            transaction = await self.client.verify_transaction(reference)

            # Map Monnify status to our standard status
            monnify_status = transaction.get("paymentStatus", "").upper()
            our_status = self._map_status(monnify_status)

            return {
                "reference": reference,
                "status": our_status,
                "amount": float(transaction.get("amountPaid", 0)),
                "paid_at": datetime.fromisoformat(
                    transaction.get("paidOn").replace("Z", "+00:00")
                ) if transaction.get("paidOn") else None,
                "currency": transaction.get("currency", "NGN"),
                "customer_email": transaction.get("customerEmail"),
                "payment_method": transaction.get("paymentMethod"),
                "meta": transaction
            }

        except Exception as e:
            # If verification fails, return pending status
            return {
                "reference": reference,
                "status": "pending",
                "amount": 0,
                "paid_at": None,
                "currency": "NGN",
                "customer_email": None,
                "meta": {"error": str(e)}
            }

    async def validate_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Validate Monnify webhook signature using HMAC-SHA512.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature from webhook header

        Returns:
            True if signature is valid, False otherwise
        """
        try:
            # Calculate expected signature using HMAC-SHA512
            expected_signature = hmac.new(
                self.webhook_secret.encode('utf-8'),
                payload,
                hashlib.sha512
            ).hexdigest()

            return hmac.compare_digest(expected_signature, signature)

        except Exception as e:
            print(f"Error validating Monnify webhook signature: {str(e)}")
            return False

    async def get_transaction_details(self, reference: str) -> Dict[str, Any]:
        """
        Get detailed Monnify transaction information.

        Args:
            reference: Transaction reference

        Returns:
            Complete transaction details
        """
        return await self.client.get_transaction_details(reference)

    def _generate_reference(self, user_id: str) -> str:
        """
        Generate a unique payment reference.

        Args:
            user_id: User's unique identifier

        Returns:
            Unique payment reference
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        return f"QRB-MON-{user_id}-{timestamp}"

    def _map_status(self, monnify_status: str) -> str:
        """
        Map Monnify status to our standard status.

        Args:
            monnify_status: Monnify transaction status

        Returns:
            Standardized status string
        """
        status_map = {
            "PAID": "success",
            "OVERPAID": "success",
            "PARTIALLY_PAID": "pending",
            "PENDING": "pending",
            "ABANDONED": "failed",
            "CANCELLED": "failed",
            "FAILED": "failed",
            "REVERSED": "failed",
            "EXPIRED": "failed"
        }

        return status_map.get(monnify_status.upper(), "pending")
