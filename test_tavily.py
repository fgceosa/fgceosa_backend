import asyncio
from app.services.web_search_service import web_search_service

async def main():
    res = await web_search_service.search("Give me the latest news")
    print(res)

asyncio.run(main())
