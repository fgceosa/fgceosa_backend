#!/usr/bin/env python3
"""
Test script to verify Requesty.AI API connection
"""
import asyncio
import httpx
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv("../.env")

async def test_requesty_api():
    api_key = os.getenv("REQUESTY_API_KEY")
    
    if not api_key:
        print("❌ REQUESTY_API_KEY not found in environment")
        return
    
    print(f"✅ API Key found: {api_key[:20]}...")
    
    # Test different endpoint variations
    endpoints = [
        "https://api.requesty.ai/v1/chat/completions",
        "https://api.requesty.ai/chat/completions",
        "https://requesty.ai/api/v1/chat/completions",
        "https://api.requesty.ai/v1/completions",
        "https://api.requesty.ai/completions",
        "https://gateway.ai.cloudflare.com/v1/requesty/openai/chat/completions",
    ]
    
    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {"role": "user", "content": "Say 'Hello, this is a test!'"}
        ],
        "max_tokens": 50
    }
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for url in endpoints:
            print(f"\n🔍 Testing: {url}")
            try:
                response = await client.post(url, json=payload, headers=headers)
                print(f"   Status: {response.status_code}")
                
                if response.status_code == 200:
                    data = response.json()
                    print(f"   ✅ SUCCESS!")
                    print(f"   Response: {data.get('choices', [{}])[0].get('message', {}).get('content', 'N/A')}")
                    return
                else:
                    print(f"   ❌ Error: {response.text[:200]}")
            except Exception as e:
                print(f"   ❌ Exception: {str(e)[:200]}")
    
    print("\n❌ All endpoints failed. Please check:")
    print("   1. Your API key is valid")
    print("   2. You have credits remaining")
    print("   3. The Requesty.AI service is operational")
    print("   4. Visit https://requesty.ai for documentation")

if __name__ == "__main__":
    asyncio.run(test_requesty_api())
