#!/usr/bin/env python3
"""
Direct API test to verify what the audit logs endpoint is actually returning
"""
import requests
import json

# Test the audit logs API endpoint
url = "http://localhost:8000/api/v1/audit-logs/"

print("Testing Audit Logs API...")
print(f"URL: {url}")
print("-" * 50)

try:
    # Try without auth first to see the error
    response = requests.get(url)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")
except Exception as e:
    print(f"Error: {e}")

print("\n" + "=" * 50)
print("Note: If you see 'Not authenticated', this is expected.")
print("The frontend should be sending auth cookies/tokens.")
print("=" * 50)
