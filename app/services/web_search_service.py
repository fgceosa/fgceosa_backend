"""
Web Search Service for AI Chat

Provides web search capabilities using Tavily API for up-to-date information.
Tavily is specifically designed for AI applications with optimized results.
"""
import logging
from typing import List, Dict, Optional
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class WebSearchService:
    """
    Service for performing web searches to enhance AI responses with current information
    """

    def __init__(self):
        """Initialize the web search service"""
        # Tavily API configuration
        self.tavily_api_key = settings.TAVILY_API_KEY if hasattr(settings, 'TAVILY_API_KEY') else None
        self.tavily_base_url = "https://api.tavily.com"
        self.timeout = 10.0  # 10 second timeout for search requests

        if self.tavily_api_key:
            logger.info("Web search service initialized with Tavily API")
        else:
            logger.warning("Tavily API key not configured. Web search will be disabled.")

    def is_available(self) -> bool:
        """Check if web search is available (API key configured and not empty)"""
        return bool(self.tavily_api_key)

    def should_search(self, query: str) -> bool:
        """
        Determine if a query should trigger a web search.
        More aggressive logic to ensure 'What is X' always searches.
        """
        query_lower = query.strip().lower()
        if not query_lower:
            return False

        # 1. Check for question mark
        if "?" in query_lower:
            return True

        # 2. Check for common question starters
        question_starters = [
            "what", "who", "how", "when", "where", "why", "tell", "explain", "define",
            "is there", "are there", "do you know", "is it", "was there", "will there",
            "latest", "recent", "current", "news on", "info on", "information on"
        ]
        
        # Check if query starts with any question word
        words = query_lower.split()
        if words and words[0] in question_starters:
            return True
        
        # Check if any part of the query contains question-like phrasing
        if any(starter + " " in query_lower for starter in question_starters):
            return True

        # 3. Fallback to keyword triggers (aggressive for company news and latest events)
        search_triggers = [
            "news", "breaking", "update", "announcement", "price", "stock",
            "weather", "forecast", "launch", "release", "available", 
            "2024", "2025", "2026", "openclaw", "claw", "qorebit",
            "research", "search", "find", "look up", "look for", "information",
            "openai", "anthropic", "google", "meta", "gpt", "claude", "gemini", "llama",
            "last 5 days", "past week", "recent", "today", "yesterday", "now"
        ]

        return any(trigger in query_lower for trigger in search_triggers)

    async def search(
        self,
        query: str,
        max_results: int = 5,
        search_depth: str = "basic"
    ) -> Optional[Dict]:
        """
        Perform a web search using Tavily API

        Args:
            query: Search query
            max_results: Maximum number of results to return
            search_depth: "basic" or "advanced" (advanced is slower but more thorough)

        Returns:
            Search results dict with 'results' list, or None if search fails
        """
        if not self.is_available():
            logger.warning("Web search requested but Tavily API key not configured")
            return None

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                payload = {
                    "api_key": self.tavily_api_key,
                    "query": query,
                    "max_results": max_results,
                    "search_depth": search_depth,
                    "include_answer": True,  # Get AI-generated summary
                    "include_raw_content": False,  # Don't need full HTML
                    "include_images": False,  # Don't need images
                }
                
                # Use news topic to get better real-time articles instead of generic homepages
                if any(word in query.lower() for word in ["news", "latest", "breaking", "today", "yesterday", "recent"]):
                    payload["topic"] = "news"
                    payload["days"] = 3

                logger.info(f"Performing web search for: {query[:100]}")
                response = await client.post(
                    f"{self.tavily_base_url}/search",
                    json=payload
                )

                if response.status_code == 200:
                    data = response.json()
                    logger.info(f"Web search successful. Found {len(data.get('results', []))} results")
                    return data
                else:
                    logger.error(f"Web search failed with status {response.status_code}: {response.text}")
                    return None

        except httpx.TimeoutException:
            logger.error(f"Web search timed out for query: {query[:100]}")
            return None
        except Exception as e:
            logger.error(f"Web search error: {str(e)}")
            return None

    def format_search_results(self, search_data: Dict) -> str:
        """
        Format search results for inclusion in AI prompt

        Args:
            search_data: Raw search results from Tavily

        Returns:
            Formatted string with search results
        """
        if not search_data or not search_data.get("results"):
            return ""

        formatted = "WEB SEARCH RESULTS:\n\n"

        # Add AI-generated answer if available
        if search_data.get("answer"):
            formatted += f"Summary: {search_data['answer']}\n\n"

        # Add individual results
        formatted += "Sources:\n"
        for i, result in enumerate(search_data.get("results", [])[:5], 1):
            title = result.get("title", "No title")
            url = result.get("url", "")
            content = result.get("content", "")

            formatted += f"\n{i}. {title}\n"
            formatted += f"   URL: {url}\n"
            formatted += f"   {content[:300]}{'...' if len(content) > 300 else ''}\n"

        formatted += "\nPlease use the above web search results to provide an accurate, up-to-date response."

        return formatted


# Singleton instance
web_search_service = WebSearchService()
