import asyncio
import httpx
from app.core.config import settings

async def main():
    async with httpx.AsyncClient() as client:
        payload = {
            "api_key": settings.TAVILY_API_KEY,
            "query": "Give me the latest news",
            "topic": "news",
            "days": 3
        }
        res = await client.post("https://api.tavily.com/search", json=payload)
        print(res.json())

asyncio.run(main())
