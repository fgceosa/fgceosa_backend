"""
Payment Provider Protocol - Interface for all payment providers.

This protocol defines the contract that all payment providers must implement.
It ensures consistency across different payment gateways and allows for
easy switching between providers with minimal code changes.
"""

from typing import Protocol, Dict, Any, Optional
from datetime import datetime


class PaymentProviderProtocol(Protocol):
    """
    Protocol defining the interface for payment providers.

    All payment providers (Flutterwave, Monnify, Paystack, Stripe, etc.)
    must implement these methods to ensure consistent behavior.
    """

    provider_name: str

    async def initialize_payment(
        self,
        amount: float,
        user_id: str,
        email: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Initialize a payment transaction.

        Args:
            amount: Amount in Naira to be paid
            user_id: User's unique identifier
            email: User's email address
            meta: Optional metadata for the transaction

        Returns:
            Dictionary containing payment initialization details:
            {
                'reference': str,  # Unique payment reference
                'status': str,     # Payment status
                'message': str,    # Human-readable message
                'data': dict       # Provider-specific data
            }
        """
        ...

    async def generate_bank_transfer_details(
        self,
        amount: float,
        user_id: str,
        email: str,
        meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate virtual bank account details for bank transfer payment.

        Args:
            amount: Amount in Naira to be paid
            user_id: User's unique identifier
            email: User's email address
            meta: Optional metadata

        Returns:
            Dictionary containing bank transfer details:
            {
                'reference': str,           # Unique payment reference
                'account_number': str,      # Virtual account number
                'bank_name': str,           # Bank name
                'account_name': str,        # Account holder name
                'amount': float,            # Amount to pay
                'expires_at': datetime,     # Expiration time
                'provider': str             # Provider name
            }
        """
        ...

    async def verify_payment(self, reference: str) -> Dict[str, Any]:
        """
        Verify a payment transaction status.

        Args:
            reference: Payment reference to verify

        Returns:
            Dictionary containing payment verification details:
            {
                'reference': str,      # Payment reference
                'status': str,         # Payment status (success, pending, failed)
                'amount': float,       # Amount paid
                'paid_at': datetime,   # Payment date/time
                'currency': str,       # Currency code
                'customer_email': str, # Customer email
                'meta': dict           # Additional metadata
            }
        """
        ...

    async def validate_webhook_signature(
        self,
        payload: bytes,
        signature: str
    ) -> bool:
        """
        Validate webhook signature to ensure request authenticity.

        Args:
            payload: Raw webhook payload bytes
            signature: Signature header from webhook

        Returns:
            True if signature is valid, False otherwise
        """
        ...

    async def get_transaction_details(self, reference: str) -> Dict[str, Any]:
        """
        Get detailed information about a transaction.

        Args:
            reference: Payment reference

        Returns:
            Dictionary containing complete transaction details
        """
        ...
