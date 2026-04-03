#!/usr/bin/env python3
"""
Test script to verify OpenRouter API connection
"""
import asyncio
import httpx
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv("../.env")

async def test_openrouter():
    api_key = os.getenv("OPENROUTER_API_KEY")
    model = os.getenv("AI_MODEL", "google/gemini-flash-1.5")
    
    if not api_key:
        print("❌ OPENROUTER_API_KEY not found in environment")
        return
    
    print(f"✅ API Key found: {api_key[:20]}...")
    print(f"🤖 Using model: {model}")
    
    url = "https://openrouter.ai/api/v1/chat/completions"
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": "Say 'Hello! OpenRouter is working!'"}
        ],
        "max_tokens": 50
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "http://localhost:3000",
        "X-Title": "Qorebit Application"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        print(f"\n🔍 Testing: {url}")
        try:
            response = await client.post(url, json=payload, headers=headers)
            print(f"   Status: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ SUCCESS!")
                content = data.get('choices', [{}])[0].get('message', {}).get('content', 'N/A')
                print(f"   Response: {content}")
                print(f"   Model: {data.get('model', 'N/A')}")
                print(f"   Tokens: {data.get('usage', {}).get('total_tokens', 'N/A')}")
            else:
                print(f"   ❌ Error: {response.text[:300]}")
        except Exception as e:
            print(f"   ❌ Exception: {str(e)[:300]}")

if __name__ == "__main__":
    asyncio.run(test_openrouter())
