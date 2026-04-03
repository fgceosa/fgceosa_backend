import asyncio
from app.services.web_search_service import web_search_service
from app.services.requesty_ai import requesty_service

async def main():
    messages = [{"role": "user", "content": "What is the latest news today?"}]
    res = await requesty_service.generate_response(messages)
    print(res["content"])

asyncio.run(main())
