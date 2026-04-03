from locust import HttpUser, task, between
import uuid
import random

class QorebitUser(HttpUser):
    wait_time = between(1, 4)  # Simulate 1 to 4 seconds between requests
    token = None
    
    def on_start(self):
        """Perform login on session start"""
        # Using environment variables or hardcoded test credentials
        auth_data = {
            "username": "admin@gmail.com",
            "password": "admin1234"
        }
        
        # FastAPI OAuth2 login endpoint
        response = self.client.post("/api/v1/login/access-token", data=auth_data)
        if response.status_code == 200:
            self.token = response.json().get("access_token")
            self.headers = {"Authorization": f"Bearer {self.token}"}
        else:
            print(f"Login failed: {response.status_code}")

    copilot_ids = []

    def ensure_copilot_exists(self):
        """Ensure at least one copilot exists for chatting"""
        if self.token and not self.copilot_ids:
            # Check list again
            response = self.client.get("/api/v1/copilots", headers=self.headers)
            if response.status_code == 200:
                data = response.json().get("copilots", []) # It returns "copilots" in CopilotsPublic
                if data:
                    self.copilot_ids = [c["id"] for c in data]
                    return

            # Create one if list is empty
            copilot_data = {
                "name": "Load Test Copilot",
                "description": "Standard agent for performance testing",
                "model": "openai/gpt-4o-mini",
                "system_prompt": "You are a helpful assistant for load testing.",
                "visibility": "public"
            }
            create_resp = self.client.post("/api/v1/copilots", json=copilot_data, headers=self.headers)
            if create_resp.status_code == 201:
                self.copilot_ids = [create_resp.json().get("id")]
                print(f"Created seed copilot: {self.copilot_ids[0]}")

    @task(3)
    def view_balance(self):
        """Most common task: users checking credits"""
        if self.token:
            self.client.get("/api/v1/credits/balance", headers=self.headers)

    @task(2)
    def list_copilots(self):
        """Users browsing agents"""
        if self.token:
            response = self.client.get("/api/v1/copilots", headers=self.headers)
            if response.status_code == 200:
                data = response.json().get("copilots", [])
                self.copilot_ids = [c["id"] for c in data]

    @task(2) # Increased weight for AI chat
    def chat_with_copilot(self):
        """AI Chat Performance: Sending messages to agents"""
        self.ensure_copilot_exists()
        if self.token and self.copilot_ids:
            copilot_id = random.choice(self.copilot_ids)
            chat_data = {
                "content": "What are your core capabilities as an AI assistant? Please be brief.",
                "stream": False # Measure full E2E latency (non-streaming)
            }
            self.client.post(f"/api/v1/copilots/{copilot_id}/chat", json=chat_data, headers=self.headers, name="/copilots/[id]/chat")

    @task(1)
    def transfer_credits(self):
        """Higher-weight transaction: transferring credits"""
        if self.token:
            # Note: Using query params as expected by the backend
            params = {
                "recipient_identifier": "admin@gmail.com",
                "amount": 10
            }
            self.client.post("/api/v1/credits/transfer", params=params, headers=self.headers)

    @task(1)
    def check_health(self):
        """Global health check"""
        self.client.get("/api/v1/utils/health-check")

# Configuration hints:
# Run locally with: locust -f locustfile.py --host http://localhost:8000
# Run headless with: locust -f locustfile.py --host http://localhost:8000 --headless -u 10 -r 1 --run-time 1m
