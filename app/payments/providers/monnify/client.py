"""
Monnify Payment Service Client

Handles integration with Monnify API for:
- Generating reserved accounts for users
- Initiating bank transfers
- Verifying payments
- Handling webhooks

Documentation: https://developers.monnify.com/
"""
import logging
import base64
from typing import Any, Dict, Optional
from decimal import Decimal
from datetime import datetime, timedelta

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class MonnifyException(Exception):
    """Base exception for Monnify client errors"""
    pass


class MonnifyAuthenticationException(MonnifyException):
    """Raised when authentication fails"""
    pass


class MonnifyPaymentException(MonnifyException):
    """Raised when payment operations fail"""
    pass


class MonnifyClient:
    """
    Async client for Monnify API

    Handles:
    - Authentication with Monnify
    - Reserved account creation
    - Payment initialization
    - Transaction verification
    """

    def __init__(self):
        """Initialize the Monnify client with configuration from settings"""
        self.base_url = settings.MONNIFY_BASE_URL.rstrip("/")
        self.api_key = settings.MONNIFY_API_KEY
        self.secret_key = settings.MONNIFY_SECRET_KEY
        self.contract_code = settings.MONNIFY_CONTRACT_CODE
        self.timeout = 30  # 30 seconds timeout

        # Validate configuration
        if not self.api_key or not self.secret_key:
            raise ValueError("MONNIFY_API_KEY and MONNIFY_SECRET_KEY must be configured")
        if not self.contract_code:
            raise ValueError("MONNIFY_CONTRACT_CODE must be configured")

        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    async def _get_access_token(self) -> str:
        """
        Get or refresh Monnify access token

        Returns:
            Valid access token

        Raises:
            MonnifyAuthenticationException: If authentication fails
        """
        # Return cached token if still valid
        if self._access_token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at:
                return self._access_token

        # Encode credentials for Basic Auth
        credentials = f"{self.api_key}:{self.secret_key}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v1/auth/login",
                    headers={
                        "Authorization": f"Basic {encoded_credentials}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code != 200:
                    raise MonnifyAuthenticationException(
                        f"Authentication failed: {response.text}"
                    )

                data = response.json()
                if not data.get("requestSuccessful"):
                    raise MonnifyAuthenticationException(
                        f"Authentication failed: {data.get('responseMessage')}"
                    )

                self._access_token = data["responseBody"]["accessToken"]
                # Token expires in 1 hour, refresh 5 minutes before
                self._token_expires_at = datetime.utcnow() + timedelta(minutes=55)

                logger.info("Successfully authenticated with Monnify")
                return self._access_token

        except httpx.RequestError as e:
            logger.error(f"Network error during Monnify authentication: {str(e)}")
            raise MonnifyAuthenticationException(f"Network error: {str(e)}")

    async def create_reserved_account(
        self,
        account_reference: str,
        account_name: str,
        customer_email: str,
        customer_name: str,
        bvn: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a reserved account for a customer

        This generates a dedicated virtual account number that the customer
        can use to make payments via bank transfer.

        Args:
            account_reference: Unique reference for the account (e.g., user_id)
            account_name: Name to display for the account
            customer_email: Customer's email address
            customer_name: Customer's full name
            bvn: Optional Bank Verification Number

        Returns:
            Dict containing account details including account number and bank name

        Raises:
            MonnifyPaymentException: If account creation fails
        """
        token = await self._get_access_token()

        payload = {
            "accountReference": account_reference,
            "accountName": account_name,
            "currencyCode": "NGN",
            "contractCode": self.contract_code,
            "customerEmail": customer_email,
            "customerName": customer_name,
            "getAllAvailableBanks": True,  # Get all available bank accounts
        }

        if bvn:
            payload["bvn"] = bvn

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/v2/bank-transfer/reserved-accounts",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                )

                if response.status_code != 200:
                    raise MonnifyPaymentException(
                        f"Failed to create reserved account: {response.text}"
                    )

                data = response.json()
                if not data.get("requestSuccessful"):
                    raise MonnifyPaymentException(
                        f"Failed to create reserved account: {data.get('responseMessage')}"
                    )

                logger.info(f"Created reserved account for {account_reference}")
                return data["responseBody"]

        except httpx.RequestError as e:
            logger.error(f"Network error creating reserved account: {str(e)}")
            raise MonnifyPaymentException(f"Network error: {str(e)}")

    async def get_reserved_account(self, account_reference: str) -> Optional[Dict[str, Any]]:
        """
        Get details of an existing reserved account

        Args:
            account_reference: Unique reference for the account

        Returns:
            Account details or None if not found
        """
        token = await self._get_access_token()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v2/bank-transfer/reserved-accounts/{account_reference}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code == 404:
                    return None

                if response.status_code != 200:
                    raise MonnifyPaymentException(
                        f"Failed to get reserved account: {response.text}"
                    )

                data = response.json()
                if not data.get("requestSuccessful"):
                    return None

                return data["responseBody"]

        except httpx.RequestError as e:
            logger.error(f"Network error getting reserved account: {str(e)}")
            raise MonnifyPaymentException(f"Network error: {str(e)}")

    async def verify_transaction(self, transaction_reference: str) -> Dict[str, Any]:
        """
        Verify a transaction by reference

        Args:
            transaction_reference: Monnify transaction reference

        Returns:
            Transaction details including status and amount

        Raises:
            MonnifyPaymentException: If verification fails
        """
        token = await self._get_access_token()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v2/transactions/{transaction_reference}",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                )

                if response.status_code != 200:
                    raise MonnifyPaymentException(
                        f"Failed to verify transaction: {response.text}"
                    )

                data = response.json()
                if not data.get("requestSuccessful"):
                    raise MonnifyPaymentException(
                        f"Failed to verify transaction: {data.get('responseMessage')}"
                    )

                return data["responseBody"]

        except httpx.RequestError as e:
            logger.error(f"Network error verifying transaction: {str(e)}")
            raise MonnifyPaymentException(f"Network error: {str(e)}")

    async def get_transaction_by_reference(self, payment_reference: str) -> Dict[str, Any]:
        """
        Get transaction details by payment reference

        Args:
            payment_reference: Your custom payment reference

        Returns:
            Transaction details

        Raises:
            MonnifyPaymentException: If transaction not found
        """
        token = await self._get_access_token()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(
                    f"{self.base_url}/api/v1/merchant/transactions/query",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    params={"paymentReference": payment_reference},
                )

                if response.status_code != 200:
                    raise MonnifyPaymentException(
                        f"Failed to get transaction: {response.text}"
                    )

                data = response.json()
                if not data.get("requestSuccessful"):
                    raise MonnifyPaymentException(
                        f"Failed to get transaction: {data.get('responseMessage')}"
                    )

                return data["responseBody"]

        except httpx.RequestError as e:
            logger.error(f"Network error getting transaction: {str(e)}")
            raise MonnifyPaymentException(f"Network error: {str(e)}")


# Singleton instance
monnify_client = MonnifyClient()
