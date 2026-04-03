"""
RequestyAI Client Service

Handles all communication with the RequestyAI API, including:
- Chat completions
- Embeddings
- Content moderation
- Retry logic with exponential backoff
- Timeout handling
"""
import asyncio
import logging
from typing import Any, Dict, Optional
from decimal import Decimal

import httpx
from fastapi import HTTPException, status

from app.core.config import settings

logger = logging.getLogger(__name__)


class RequestyAIException(Exception):
    """Base exception for RequestyAI client errors"""
    pass


class RequestyAITimeoutException(RequestyAIException):
    """Raised when a request to RequestyAI times out"""
    pass


class RequestyAIRateLimitException(RequestyAIException):
    """Raised when rate limit is exceeded"""
    pass


class RequestyAIInvalidRequestException(RequestyAIException):
    """Raised when the request is invalid"""
    pass


class RequestyAIClient:
    """
    Async client for RequestyAI API

    Handles all external communication with RequestyAI endpoints:
    - /v1/chat/completions
    - /v1/embeddings
    - /v1/moderations
    """

    def __init__(self):
        """Initialize the RequestyAI client with configuration from settings"""
        self.base_url = settings.REQUESTY_AI_BASE_URL.rstrip("/")
        self.api_key = settings.REQUESTY_AI_API_KEY
        self.timeout = settings.REQUESTY_AI_TIMEOUT
        self.max_retries = settings.REQUESTY_AI_MAX_RETRIES

        # Validate configuration
        if not self.api_key:
            raise ValueError("REQUESTY_AI_API_KEY is not configured")
        if not self.base_url:
            raise ValueError("REQUESTY_AI_BASE_URL is not configured")

    async def _make_request(
        self,
        endpoint: str,
        method: str = "POST",
        payload: Optional[Dict[str, Any]] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Make an HTTP request to RequestyAI with retry logic

        Args:
            endpoint: API endpoint (e.g., "/v1/chat/completions")
            method: HTTP method (GET or POST)
            payload: Request payload for POST requests
            retry_count: Current retry attempt number

        Returns:
            Response JSON from RequestyAI

        Raises:
            RequestyAITimeoutException: On timeout
            RequestyAIRateLimitException: On rate limit (429)
            RequestyAIInvalidRequestException: On client error (4xx)
            RequestyAIException: On server error (5xx)
        """
        url = f"{self.base_url}{endpoint}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Making {method} request to RequestyAI: {endpoint}")
                if method.upper() == "GET":
                    response = await client.get(url, headers=headers)
                else:
                    logger.info(f"RequestyAI Request Payload: {payload}")
                    response = await client.post(url, json=payload, headers=headers)

                # Handle different response codes
                if response.status_code == 200:
                    return response.json()

                elif response.status_code == 429:
                    # Rate limit - retry with exponential backoff
                    if retry_count < self.max_retries:
                        wait_time = 2 ** retry_count  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(
                            f"Rate limit hit. Retrying in {wait_time}s (attempt {retry_count + 1}/{self.max_retries})"
                        )
                        await asyncio.sleep(wait_time)
                        return await self._make_request(endpoint, method, payload, retry_count + 1)
                    else:
                        raise RequestyAIRateLimitException(
                            f"Rate limit exceeded after {self.max_retries} retries"
                        )

                elif response.status_code == 402:
                    # Payment Required - insufficient RequestyAI account balance
                    try:
                        error_detail = response.json().get("error", {}).get("message", "Insufficient balance")
                    except:
                        error_detail = "Insufficient RequestyAI account balance"
                    logger.error(f"RequestyAI 402 error: {error_detail}")
                    raise HTTPException(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail=f"RequestyAI account has insufficient balance. Please top up at https://app.requesty.ai/settings"
                    )

                elif response.status_code == 404:
                    # Not found - log full details for debugging
                    logger.error(f"RequestyAI 404 error - URL: {url}, Response: {response.text}")
                    raise RequestyAIInvalidRequestException(
                        f"RequestyAI endpoint not found (404). URL: {url}. "
                        f"Please check REQUESTY_AI_BASE_URL configuration. Response: {response.text}"
                    )

                elif response.status_code in [400, 401, 403]:
                    # Client errors - don't retry
                    try:
                        error_detail = response.json().get("error", {}).get("message", "Unknown error")
                    except:
                        error_detail = response.text
                    logger.error(f"RequestyAI {response.status_code} error - Full response: {response.text}")
                    raise RequestyAIInvalidRequestException(
                        f"RequestyAI returned {response.status_code}: {error_detail}"
                    )

                elif response.status_code >= 500:
                    # Server errors - retry
                    logger.error(f"RequestyAI server error {response.status_code} - Full response: {response.text}")
                    if retry_count < self.max_retries:
                        wait_time = 2 ** retry_count
                        logger.warning(
                            f"Server error {response.status_code}. Retrying in {wait_time}s"
                        )
                        await asyncio.sleep(wait_time)
                        return await self._make_request(endpoint, method, payload, retry_count + 1)
                    else:
                        raise RequestyAIException(
                            f"Server error {response.status_code} after {self.max_retries} retries: {response.text}"
                        )

                else:
                    # Unexpected status code
                    raise RequestyAIException(
                        f"Unexpected status code {response.status_code}: {response.text}"
                    )

        except httpx.TimeoutException:
            if retry_count < self.max_retries:
                wait_time = 2 ** retry_count
                logger.warning(f"Timeout. Retrying in {wait_time}s")
                await asyncio.sleep(wait_time)
                return await self._make_request(endpoint, method, payload, retry_count + 1)
            else:
                raise RequestyAITimeoutException(
                    f"Request timed out after {self.max_retries} retries"
                )

        except httpx.RequestError as e:
            logger.error(f"Request error: {str(e)}")
            raise RequestyAIException(f"Request failed: {str(e)}")

    async def list_models(self) -> Dict[str, Any]:
        """
        Fetch the list of available models from RequestyAI
        """
        return await self._make_request("/models", method="GET")

    async def chat_completion(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Send a chat completion request to RequestyAI

        Args:
            payload: Chat completion request payload (messages, model, etc.)

        Returns:
            Chat completion response including usage information
        """
        # Ensure credit_mode is enabled for RequestyAI
        if "credit_mode" not in payload:
            payload["credit_mode"] = True

        return await self._make_request("/chat/completions", method="POST", payload=payload)

    async def create_embeddings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Create embeddings using RequestyAI

        Args:
            payload: Embeddings request payload (input, model, etc.)

        Returns:
            Embeddings response including usage information
        """
        return await self._make_request("/embeddings", method="POST", payload=payload)

    async def moderate_content(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Moderate content using RequestyAI

        Args:
            payload: Moderation request payload (input, etc.)

        Returns:
            Moderation response
        """
        return await self._make_request("/moderations", method="POST", payload=payload)

    @staticmethod
    def calculate_cost_from_usage(
        model: str,
        prompt_tokens: int,
        completion_tokens: int
    ) -> Decimal:
        """
        Calculate cost based on token usage

        This is a simple implementation. You may want to load pricing
        from a database or configuration file for more flexibility.

        Args:
            model: Model name used
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens

        Returns:
            Cost in USD as Decimal
        """
        # Pricing per 1M tokens (actual RequestyAI pricing)
        PRICING = {
            # OpenAI models
            "openai/gpt-5-mini": {"input": Decimal("0.00"), "output": Decimal("2.00")},
            "openai/gpt-5": {"input": Decimal("1.00"), "output": Decimal("10.00")},
            "openai/gpt-4o": {"input": Decimal("3.00"), "output": Decimal("10.00")},
            "openai/chatgpt-4o": {"input": Decimal("5.00"), "output": Decimal("15.00")},
            "openai/o1": {"input": Decimal("15.00"), "output": Decimal("60.00")},
            "openai/o3-mini": {"input": Decimal("1.00"), "output": Decimal("4.00")},

            # Anthropic models
            "anthropic/claude-3-opus": {"input": Decimal("15.00"), "output": Decimal("75.00")},
            "anthropic/claude-3-5-sonnet": {"input": Decimal("3.00"), "output": Decimal("15.00")},
            "anthropic/claude-3-5-haiku": {"input": Decimal("0.25"), "output": Decimal("1.25")},
            "anthropic/claude-3-7-sonnet": {"input": Decimal("3.00"), "output": Decimal("15.00")},
            "anthropic/claude-3-haiku": {"input": Decimal("0.25"), "output": Decimal("1.25")},

            # Google models
            "google/gemini-pro-1.5": {"input": Decimal("1.25"), "output": Decimal("5.00")},
            "google/gemini-flash-1.5": {"input": Decimal("0.075"), "output": Decimal("0.30")},
            "google/gemini-pro-2.0": {"input": Decimal("1.25"), "output": Decimal("5.00")},
            "google/gemini-flash-2.0": {"input": Decimal("0.075"), "output": Decimal("0.30")},

            # Default fallback
            "default": {"input": Decimal("1.00"), "output": Decimal("2.00")},
        }

        # Find pricing for model (flexible matching)
        # RequestyAI returns versioned names like "gpt-5-2025-08-07"
        # but our keys are like "openai/gpt-5"
        pricing = PRICING.get("default")
        model_lower = model.lower()

        # First try exact match
        if model in PRICING:
            pricing = PRICING[model]
        else:
            # Try partial match - extract base model name
            # e.g., "gpt-5-2025-08-07" -> "gpt-5", "claude-opus-4-5" -> "claude-opus"
            for model_key, model_pricing in PRICING.items():
                # Extract base name from both model key and model
                # "openai/gpt-5" -> ["openai", "gpt-5"]
                # "gpt-5-2025-08-07" -> ["gpt-5", "2025", "08", "07"]
                base_key = model_key.split("/")[-1].split("-")[0:2]  # ["gpt", "5"] or ["claude", "opus"]
                base_model = model_lower.split("-")[0:2]  # ["gpt", "5"]

                # Check if base names match
                if "-".join(base_key) in model_lower or "-".join(base_model) in model_key.lower():
                    pricing = model_pricing
                    break

        # Calculate cost (price per 1M tokens)
        input_cost = (Decimal(prompt_tokens) / Decimal(1_000_000)) * pricing["input"]
        output_cost = (Decimal(completion_tokens) / Decimal(1_000_000)) * pricing["output"]

        total_cost = input_cost + output_cost

        # Round to 4 decimal places
        return total_cost.quantize(Decimal("0.0001"))


# Singleton instance
requesty_ai_client = RequestyAIClient()
