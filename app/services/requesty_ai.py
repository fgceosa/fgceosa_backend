"""
RequestyAI service for AI chat integration with credit management
"""
import uuid
import logging
from decimal import Decimal
from typing import Dict, List, Optional
from sqlmodel import Session
from fastapi import HTTPException, status

from app.core.config import settings
from app.services.requesty_ai_client import RequestyAIClient
from app.services.web_search_service import web_search_service
from app.credit_repository import (
    check_sufficient_credits,
    process_ai_request_usage,
    get_user_credit_balance
)

logger = logging.getLogger(__name__)


# Free models available on RequestyAI (no credit deduction)
FREE_MODELS = {
    "smart/task",
    "deepseek/deepseek-chat",
    "deepseek-chat",
    "deepseek/deepseek-reasoner",
    "deepseek-reasoner",
    "alibaba/qwen-turbo",
    "qwen-turbo",
    "openai/gpt-5-nano",
    "gpt-5-nano",
    "meta-llama/llama-3.2-3b-instruct:free",
    "meta-llama/llama-3.1-8b-instruct:free",
    "google/gemini-2.0-flash-exp:free",
    "mistralai/mistral-7b-instruct:free",
    "gpt-4o-mini",
    "openai/gpt-4o-mini",
}


class RequestyAIService:
    """Service for interacting with RequestyAI API with credit management"""

    def __init__(self):
        self.client = RequestyAIClient()
        self.default_model = settings.AI_MODEL

    def _is_free_model(self, model: str) -> bool:
        """Check if a model is free (no credit deduction required)"""
        if not model:
            return False
        
        # Check direct match
        if model in FREE_MODELS:
            return True
            
        # Check without provider prefix
        if "/" in model:
            model_name = model.split("/", 1)[1]
            if model_name in FREE_MODELS:
                return True
                
        return False

    def _normalize_model(self, model: str) -> str:
        """
        Ensure model has provider prefix for RequestyAI
        e.g., 'gpt-4o' -> 'openai/gpt-4o'
        """
        if not model:
            return self.default_model

        # If already has provider prefix, just ensure formatting
        if "/" in model:
            provider, model_name = model.split("/", 1)
            return model
            
        model_lower = model.lower()
        
        # OpenAI models
        if "gpt" in model_lower or "o1" in model_lower or "o3" in model_lower:
            norm_model = model
            if not norm_model.startswith("openai/"):
                return f"openai/{norm_model}"
            return norm_model
            
        # Anthropic models
        if "claude" in model_lower:
            norm_model = model
            return f"anthropic/{norm_model}"
            
        # Gemini models
        if "gemini" in model_lower:
            norm_model = model
            if "flash" in model_lower:
                if "2.0" in model:
                    return "google/gemini-flash-2.0"
                return "google/gemini-flash-1.5"
            if "pro" in model_lower:
                if "2.0" in model:
                    return "google/gemini-pro-2.0"
                return "google/gemini-pro-1.5"
            return "google/gemini-pro-1.5"
            
        if "mistral" in model_lower:
            if "large" in model_lower:
                return "mistralai/mistral-large"
            return f"mistralai/{model}"
            
        if "deepseek" in model_lower:
            return f"deepseek/{model}"
            
        if "qwen" in model_lower:
            return f"alibaba/{model}"
            
        return model

    async def generate_response(
        self,
        messages: List[Dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        session: Optional[Session] = None,
        user_id: Optional[uuid.UUID] = None,
        organization_id: Optional[uuid.UUID] = None,
        workspace_id: Optional[uuid.UUID] = None
    ) -> Dict:
        """
        Generate AI response using RequestyAI with credit management
        """
        model = model or self.default_model
        model = self._normalize_model(model)

        # 1. Check Cache (Deduplication)
        # Only cache if temperature is relatively low (stable responses)
        from app.services.cache_service import cache_service
        use_cache = temperature <= 0.7 
        if use_cache:
            cached_result = await cache_service.get_llm_cache(model, messages)
            if cached_result:
                return cached_result

        # Credit management (if session and user_id provided)
        if session and user_id:
            # Check if model is free
            is_free = self._is_free_model(model)

            if not is_free:
                # Notice: We no longer auto-resolve organization_id for admins here.
                # Users should use their personal wallet by default.
                # Organization wallet is used only if explicitly provided (e.g. from Org dashboard)

                # For paid models, strictly enforce credit requirements
                balance = get_user_credit_balance(
                    session=session, 
                    user_id=user_id,
                    organization_id=organization_id
                )

                # Require minimum balance for paid models
                if balance < Decimal("0.01"):
                    raise HTTPException(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail={
                            "error": "insufficient_credits",
                            "message": f"Insufficient credits to use {model}. Please top up your account.",
                            "current_balance": float(balance),
                            "required_balance": 0.01,
                            "model": model
                        }
                    )
                
                # Check sufficient credits with estimated cost
                check_sufficient_credits(
                    session=session,
                    user_id=user_id,
                    organization_id=organization_id,
                    estimated_cost=Decimal("0.01")  # Minimum check
                )

        # Inject system message with current date/time and web search results
        from datetime import datetime, timezone, timedelta

        # Use WAT timezone (UTC+1) for Nigeria/Lagos time
        wat_timezone = timezone(timedelta(hours=1))
        current_datetime = datetime.now(wat_timezone)
        current_date = current_datetime.strftime("%B %d, %Y")
        current_time = current_datetime.strftime("%I:%M %p")  # 12-hour format with AM/PM
        current_day = current_datetime.strftime("%A")

        # Check if we should perform web search
        web_search_results = ""
        user_query = messages[-1]["content"] if messages else ""
        
        # If content is a list (vision content), extract the text part
        if isinstance(user_query, list):
            user_query = next((item["text"] for item in user_query if item.get("type") == "text"), "")

        performed_search = False
        if web_search_service.is_available() and web_search_service.should_search(user_query):
            # Perform web search
            search_data = await web_search_service.search(user_query, max_results=5)
            if search_data:
                web_search_results = "\n\n" + web_search_service.format_search_results(search_data)
                performed_search = True

        # Build system message based on search availability and results
        if performed_search:
            system_content = f"""You are Qorebit AI, a highly capable and intelligent AI assistant with integrated real-time web search capabilities.
            
CURRENT CONTEXT:
- Today's Date: {current_date}
- Current Day: {current_day}
- Current Time: {current_time} (West Africa Time, WAT/Lagos time)
{web_search_results}

CRITICAL INSTRUCTIONS FOR REAL-TIME INFORMATION:
1. KNOWLEDGE CUTOFF & REAL-TIME STATUS: While your internal training data has a cutoff, you are NOW operating in {current_datetime.year}. You have ACTIVE web access right now for this specific query.
2. WEB SEARCH AS PRIMARY SOURCE: If "WEB SEARCH RESULTS" are provided above, they are your ABSOLUTE source of truth for anything recent.
3. NO REFUSALS: Under NO circumstances should you say "I don't have real-time news access", "I cannot browse the live web", or ask the user for their topic. You ALREADY have the search results.
4. HALLUCINATION PREVENTION: Summarize the provided search results to answer the user accurately and directly. If the results are generic or unhelpful, state exactly what the results said instead of asking for clarification.
5. CITE SOURCES: Identify the sources from the results to build trust."""
        else:
             system_content = f"""You are Qorebit AI, a highly capable AI assistant.
            
CURRENT CONTEXT:
- Today's Date: {current_date}
- Current Day: {current_day}
- Current Time: {current_time} (West Africa Time, WAT/Lagos time)

KNOWLEDGE CUTOFF: Your internal training data has a cutoff. If the user asks for current events, try your best to answer from your internal knowledge. If you cannot, politely explain your knowledge limit."""

        # Prepend system message with context
        messages_with_context = [
            {
                "role": "system",
                "content": system_content
            }
        ] + messages

        # Build RequestyAI payload
        # RequestyAI expects full model IDs with provider prefix (e.g., "openai/gpt-5")
        payload = {
            "model": model,
            "messages": messages_with_context,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
            "credit_mode": not self._is_free_model(model)
        }

        try:
            # Call RequestyAI API
            response = await self.client.chat_completion(payload)

            if not response or "choices" not in response or not response["choices"]:
                logger.error(f"RequestyAI returned empty response: {response}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="AI provider returned an empty response. Please try again or choose a different model."
                )

            # Extract response data
            try:
                choice = response["choices"][0]
                message = choice.get("message", {})
                content = message.get("content", "")
                
                if not content:
                    # Check for finish_reason if content is empty
                    finish_reason = choice.get("finish_reason")
                    if finish_reason == "content_filter":
                        content = "[Message blocked by content filter]"
                    else:
                        content = "[Empty response from AI]"
            except (KeyError, IndexError) as e:
                logger.error(f"Failed to extract content from RequestyAI response: {e}, Response: {response}")
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to extract response from AI provider."
                )

            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            # Calculate cost
            cost_usd = Decimal("0.0")
            if session and user_id:
                is_free = self._is_free_model(model)
                if not is_free:
                    # Use RequestyAI client's cost calculation
                    try:
                        base_cost = self.client.calculate_cost_from_usage(
                            model=model,
                            prompt_tokens=prompt_tokens,
                            completion_tokens=completion_tokens
                        )

                        # Apply platform-wide markup
                        from app.models import PlatformSettings
                        from sqlmodel import select
                        
                        platform_settings = session.exec(select(PlatformSettings)).first()
                        markup_percent = 15 # Default fallback
                        
                        if platform_settings and "payments" in platform_settings.payments:
                            markup_percent = platform_settings.payments.get("defaultMarkup", 15)

                        # Add markup: cost = base * (1 + markup/100)
                        markup_multiplier = Decimal("1.0") + (Decimal(str(markup_percent)) / Decimal("100.0"))
                        cost_usd = (base_cost * markup_multiplier).quantize(Decimal("0.000001"))
                    except Exception as cost_err:
                        logger.error(f"Cost calculation failed: {cost_err}")
                        # Fallback to zero cost if calculation fails but request succeeded
                        cost_usd = Decimal("0.0")

                # Log usage (deducts 0 credits for free models)
                try:
                    process_ai_request_usage(
                        session=session,
                        user_id=user_id,
                        project_id=None,
                        model=model,
                        endpoint="/chat/completions",
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        cost=cost_usd,
                        response_time_ms=None,
                        organization_id=organization_id,
                        workspace_id=workspace_id
                    )
                except Exception as usage_err:
                    # Log usage error but don't fail the AI response
                    logger.error(f"Failed to log AI usage: {usage_err}")

            result = {
                "content": content,
                "model": response.get("model", model),
                "tokens_used": total_tokens,
                "cost_usd": float(cost_usd),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens
            }

            # 2. Store in Cache
            if use_cache:
                await cache_service.set_llm_cache(model, messages, result, expire=600) # 10 min cache

            return result

        except HTTPException:
            raise
        except Exception as e:
            # Re-raise with more context
            error_msg = str(e)
            logger.error(f"AI Generator Error: {error_msg}", exc_info=True)
            
            if "insufficient credits" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail={
                        "error": "insufficient_credits",
                        "message": "Insufficient credits to complete this request. Please top up your account.",
                        "model": model
                    }
                )

            elif "rate limit" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )
            elif "not found" in error_msg.lower() or "not supported" in error_msg.lower() or "404" in error_msg:
                # Model not supported — retry with a stable fallback model
                fallback_model = "openai/gpt-4o-mini"
                if model != fallback_model:
                    logger.warning(f"Model '{model}' not supported by provider. Falling back to '{fallback_model}'")
                    return await self.generate_response(
                        messages=messages,
                        model=fallback_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        session=session,
                        user_id=user_id,
                        organization_id=organization_id,
                        workspace_id=workspace_id
                    )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"AI model '{model}' is not available. Please update the copilot's model in settings."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"AI request failed: {error_msg if error_msg else type(e).__name__}"
                )
    
    async def generate_chat_title(
        self,
        first_message: str,
        session: Optional[Session] = None,
        user_id: Optional[uuid.UUID] = None
    ) -> str:
        """
        Generate a descriptive title for a chat based on the first message

        Args:
            first_message: The first user message
            session: Database session (optional, for credit management)
            user_id: User ID (optional, for credit management)

        Returns:
            Generated title string (max 50 chars)
        """
        messages = [
            {
                "role": "system",
                "content": "Generate a short, descriptive title (max 5 words) for a chat conversation based on the user's first message. Return only the title, nothing else."
            },
            {
                "role": "user",
                "content": first_message[:500]  # Limit to avoid token issues
            }
        ]

        try:
            # Use inexpensive model for title generation
            result = await self.generate_response(
                messages=messages,
                model="openai/gpt-4o-mini",
                temperature=0.5,
                max_tokens=30,
                session=session,
                user_id=user_id
            )
            title = result["content"].strip().strip('"').strip("'")
            # Ensure title is not too long
            return title[:50] if len(title) > 50 else title
        except Exception as e:
            # Fallback to simple title generation
            print(f"Title generation failed: {e}")
            words = first_message.split()[:5]
            title = " ".join(words)
            return (title[:47] + "...") if len(title) > 50 else title

    async def generate_response_with_tools(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8000,
        session: Optional[Session] = None,
        user_id: Optional[uuid.UUID] = None,
        organization_id: Optional[uuid.UUID] = None,
        workspace_id: Optional[uuid.UUID] = None
    ) -> Dict:
        """
        Generate AI response with function/tool calling support
        
        Args:
            messages: Conversation messages
            tools: List of tool definitions in OpenAI format
            model: Model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens
            session: Database session for credit management
            user_id: User ID for credit management
            
        Returns:
            Dict with content, tool_calls, and usage info
        """
        model = model or self.default_model
        model = self._normalize_model(model)

        # 1. Check Cache
        from app.services.cache_service import cache_service
        use_cache = temperature <= 0.7
        if use_cache:
            # We include tools in the cache identifier
            cache_id = {"messages": messages, "tools": tools}
            cached_result = await cache_service.get_llm_cache(model, cache_id)
            if cached_result:
                return cached_result

        # Credit management (same as generate_response)
        if session and user_id:
            is_free = self._is_free_model(model)
            if not is_free:
                # Notice: We no longer auto-resolve organization_id for admins here.
                # Users should use their personal wallet by default.
                # Organization wallet is used only if explicitly provided.

                balance = get_user_credit_balance(
                    session=session, 
                    user_id=user_id,
                    organization_id=organization_id
                )
                if balance < Decimal("0.01"):
                    raise HTTPException(
                        status_code=status.HTTP_402_PAYMENT_REQUIRED,
                        detail={
                            "error": "insufficient_credits",
                            "message": f"Insufficient credits to use {model}. Please top up your account.",
                            "current_balance": float(balance),
                            "required_balance": 0.01,
                            "model": model
                        }
                    )
                check_sufficient_credits(
                    session=session,
                    user_id=user_id,
                    organization_id=organization_id,
                    estimated_cost=Decimal("0.01")
                )

        # Build RequestyAI payload with tools
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"  # Let model decide when to use tools
            import logging
            logging.info(f"AI Request with tools: {[t.get('function', {}).get('name') for t in tools]}")

        try:
            # Call RequestyAI API
            response = await self.client.chat_completion(payload)

            # Extract response data
            message = response["choices"][0]["message"]
            content = message.get("content", "")
            tool_calls = message.get("tool_calls", [])
            
            usage = response.get("usage", {})
            prompt_tokens = usage.get("prompt_tokens", 0)
            completion_tokens = usage.get("completion_tokens", 0)
            total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

            # Calculate cost
            cost_usd = Decimal("0.0")
            if session and user_id:
                is_free = self._is_free_model(model)
                if not is_free:
                    base_cost = self.client.calculate_cost_from_usage(
                        model=model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens
                    )

                    # Apply platform markup
                    from app.models import PlatformSettings
                    from sqlmodel import select
                    
                    platform_settings = session.exec(select(PlatformSettings)).first()
                    markup_percent = 15
                    
                    if platform_settings and "payments" in platform_settings.payments:
                        markup_percent = platform_settings.payments.get("defaultMarkup", 15)

                    markup_multiplier = Decimal("1.0") + (Decimal(str(markup_percent)) / Decimal("100.0"))
                    cost_usd = (base_cost * markup_multiplier).quantize(Decimal("0.000001"))

                # Log usage
                process_ai_request_usage(
                    session=session,
                    user_id=user_id,
                    project_id=None,
                    model=model,
                    endpoint="/chat/completions",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    cost=cost_usd,
                    response_time_ms=None,
                    organization_id=organization_id,
                    workspace_id=workspace_id
                )

            result = {
                "content": content,
                "tool_calls": tool_calls,
                "model": response.get("model", model),
                "tokens_used": total_tokens,
                "cost_usd": float(cost_usd),
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens
            }

            # 2. Store in Cache
            if use_cache:
                cache_id = {"messages": messages, "tools": tools}
                await cache_service.set_llm_cache(model, cache_id, result, expire=600)

            return result

        except HTTPException:
            raise
        except Exception as e:
            error_msg = str(e)
            if "insufficient credits" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_402_PAYMENT_REQUIRED,
                    detail="Insufficient credits to complete request"
                )
            elif "rate limit" in error_msg.lower():
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail="Rate limit exceeded. Please try again later."
                )
            elif "not found" in error_msg.lower() or "not supported" in error_msg.lower() or "404" in error_msg:
                # Model not supported — retry with fallback
                fallback_model = "openai/gpt-4o-mini"
                if model != fallback_model:
                    logger.warning(f"Model '{model}' not supported by provider in tools mode. Falling back to '{fallback_model}'")
                    return await self.generate_response_with_tools(
                        messages=messages,
                        tools=tools,
                        model=fallback_model,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        session=session,
                        user_id=user_id,
                        organization_id=organization_id,
                        workspace_id=workspace_id
                    )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"AI model '{model}' is not available. Please update the copilot's model in settings."
                )
            else:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"AI request failed: {error_msg}"
                )


# Singleton instance
requesty_service = RequestyAIService()

