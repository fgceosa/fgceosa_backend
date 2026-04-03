#!/usr/bin/env python3
"""
Test the complete chat flow: create chat -> send message -> get AI response
"""
import asyncio
import httpx
import os
from dotenv import load_dotenv

load_dotenv("../.env")

BASE_URL = "http://localhost:8000/api/v1"

async def test_chat_flow():
    print("🧪 Testing AI Chat Flow\n")
    
    # Step 1: Login to get token
    print("1️⃣ Logging in...")
    async with httpx.AsyncClient() as client:
        login_data = {
            "username": os.getenv("FIRST_SUPERUSER", "admin@gmail.com"),
            "password": os.getenv("FIRST_SUPERUSER_PASSWORD", "admin1234")
        }
        
        response = await client.post(
            f"{BASE_URL}/login/access-token",
            data=login_data
        )
        
        if response.status_code != 200:
            print(f"❌ Login failed: {response.status_code}")
            print(response.text)
            return
        
        token = response.json()["access_token"]
        print(f"✅ Logged in successfully\n")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # Step 2: Create a new chat
        print("2️⃣ Creating new chat...")
        response = await client.post(
            f"{BASE_URL}/ai-chat",
            json={"title": "Test Chat"},
            headers=headers
        )
        
        if response.status_code != 201:
            print(f"❌ Failed to create chat: {response.status_code}")
            print(response.text)
            return
        
        chat = response.json()
        chat_id = chat["id"]
        print(f"✅ Chat created: {chat_id}\n")
        
        # Step 3: Send a message
        print("3️⃣ Sending message to AI...")
        print("   Message: 'Hello! Say hi back in one sentence.'")
        print("   Model: 'deepseek/deepseek-chat'\n")
        
        response = await client.post(
            f"{BASE_URL}/ai-chat/{chat_id}/messages",
            json={
                "message": "Hello! Say hi back in one sentence.",
                "model": "deepseek/deepseek-chat"
            },
            headers=headers
        )
        
        if response.status_code == 429:
            print("⚠️  Rate limit hit!")
            error_data = response.json()
            print(f"   {error_data.get('detail', {}).get('message', 'Too many requests')}")
            print(f"   Retry after: {error_data.get('detail', {}).get('retry_after', 60)} seconds")
            return
        
        if response.status_code != 200:
            print(f"❌ Failed to send message: {response.status_code}")
            print(response.text)
            return
        
        result = response.json()
        print(f"✅ Message sent successfully!\n")
        
        # Display results
        print("📝 USER MESSAGE:")
        print(f"   {result['user_message']['content']}\n")
        
        print("🤖 AI RESPONSE:")
        print(f"   {result['assistant_message']['content']}\n")
        
        print("📊 METADATA:")
        print(f"   Model: {result['assistant_message']['model']}")
        print(f"   Tokens: {result['assistant_message']['tokens_used']}")
        
        print("\n✅ Test completed successfully!")

if __name__ == "__main__":
    asyncio.run(test_chat_flow())
