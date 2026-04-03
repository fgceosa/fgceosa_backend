#!/bin/bash

# RequestYAI Credit Mode - Quick Test Script
# This script tests all backend endpoints

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}🚀 RequestYAI Credit Mode - Backend Test Suite${NC}\n"

# Configuration
BASE_URL="http://localhost:8000/api/v1"
TOKEN=""

# Test 1: Models List (No Auth)
echo -e "${YELLOW}Test 1: Models List (Public Endpoint)${NC}"
RESPONSE=$(curl -s "$BASE_URL/ai/v1/models")
if echo "$RESPONSE" | jq -e '.models' > /dev/null 2>&1; then
    TOTAL=$(echo "$RESPONSE" | jq -r '.total')
    echo -e "${GREEN}✓ PASS${NC} - Found $TOTAL models\n"
else
    echo -e "${RED}✗ FAIL${NC} - Models endpoint failed\n"
    echo "Response: $RESPONSE\n"
fi

# Test 2: Login to get token
echo -e "${YELLOW}Test 2: Authentication${NC}"
echo "Enter your email: "
read -r EMAIL
echo "Enter your password: "
read -rs PASSWORD
echo

LOGIN_RESPONSE=$(curl -s -X POST "$BASE_URL/login/access-token" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=$EMAIL&password=$PASSWORD")

TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token // empty')

if [ -n "$TOKEN" ] && [ "$TOKEN" != "null" ]; then
    echo -e "${GREEN}✓ PASS${NC} - Logged in successfully\n"
else
    echo -e "${RED}✗ FAIL${NC} - Login failed"
    echo "Response: $LOGIN_RESPONSE\n"
    exit 1
fi

# Test 3: Health Check
echo -e "${YELLOW}Test 3: AI Engine Health${NC}"
HEALTH=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/ai/v1/health")
STATUS=$(echo "$HEALTH" | jq -r '.status // empty')
if [ "$STATUS" = "healthy" ]; then
    BALANCE=$(echo "$HEALTH" | jq -r '.credit_balance')
    echo -e "${GREEN}✓ PASS${NC} - Service healthy, balance: \$$BALANCE\n"
else
    echo -e "${RED}✗ FAIL${NC} - Health check failed\n"
    echo "Response: $HEALTH\n"
fi

# Test 4: Get Credit Balance
echo -e "${YELLOW}Test 4: Credit Balance${NC}"
BALANCE_RESP=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/credits/balance")
AI_CREDITS=$(echo "$BALANCE_RESP" | jq -r '.ai_credits // empty')
if [ -n "$AI_CREDITS" ]; then
    NAIRA=$(echo "$BALANCE_RESP" | jq -r '.naira_equivalent')
    RATE=$(echo "$BALANCE_RESP" | jq -r '.conversion_rate')
    echo -e "${GREEN}✓ PASS${NC}"
    echo "  AI Credits: $AI_CREDITS"
    echo "  Naira Equivalent: ₦$NAIRA"
    echo "  Conversion Rate: ₦$RATE = 1 credit\n"
else
    echo -e "${RED}✗ FAIL${NC} - Balance check failed\n"
    echo "Response: $BALANCE_RESP\n"
fi

# Test 5: Initiate Top-Up
echo -e "${YELLOW}Test 5: Initiate Top-Up (₦1000)${NC}"
TOPUP_RESP=$(curl -s -X POST "$BASE_URL/credits/top-up" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"amount": 1000, "payment_method": "bank_transfer"}')

TOPUP_ID=$(echo "$TOPUP_RESP" | jq -r '.id // empty')
if [ -n "$TOPUP_ID" ] && [ "$TOPUP_ID" != "null" ]; then
    ACCOUNT=$(echo "$TOPUP_RESP" | jq -r '.account_number')
    BANK=$(echo "$TOPUP_RESP" | jq -r '.bank_name')
    REFERENCE=$(echo "$TOPUP_RESP" | jq -r '.payment_reference')
    CREDITS=$(echo "$TOPUP_RESP" | jq -r '.ai_credits')

    echo -e "${GREEN}✓ PASS${NC}"
    echo "  Top-up ID: $TOPUP_ID"
    echo "  Account: $ACCOUNT"
    echo "  Bank: $BANK"
    echo "  Reference: $REFERENCE"
    echo "  Will receive: $CREDITS credits\n"

    # Save for later tests
    export TOPUP_ID
else
    echo -e "${RED}✗ FAIL${NC} - Top-up creation failed\n"
    echo "Response: $TOPUP_RESP\n"
fi

# Test 6: Check Top-Up Status
if [ -n "$TOPUP_ID" ]; then
    echo -e "${YELLOW}Test 6: Check Top-Up Status${NC}"
    STATUS_RESP=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/credits/top-up/$TOPUP_ID/status")
    TOPUP_STATUS=$(echo "$STATUS_RESP" | jq -r '.status // empty')

    if [ -n "$TOPUP_STATUS" ]; then
        echo -e "${GREEN}✓ PASS${NC} - Status: $TOPUP_STATUS\n"
    else
        echo -e "${RED}✗ FAIL${NC} - Status check failed\n"
        echo "Response: $STATUS_RESP\n"
    fi
fi

# Test 7: Create API Key
echo -e "${YELLOW}Test 7: Create API Key${NC}"
APIKEY_RESP=$(curl -s -X POST "$BASE_URL/api-keys" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Test Key", "expires_in_days": 30}')

API_KEY=$(echo "$APIKEY_RESP" | jq -r '.key // empty')
if [ -n "$API_KEY" ] && [ "$API_KEY" != "null" ]; then
    KEY_ID=$(echo "$APIKEY_RESP" | jq -r '.id')
    echo -e "${GREEN}✓ PASS${NC}"
    echo "  Key ID: $KEY_ID"
    echo -e "  ${YELLOW}⚠️  API Key (SAVE THIS - shown only once):${NC}"
    echo "  $API_KEY\n"

    export API_KEY_ID=$KEY_ID
else
    echo -e "${RED}✗ FAIL${NC} - API key creation failed\n"
    echo "Response: $APIKEY_RESP\n"
fi

# Test 8: List API Keys
echo -e "${YELLOW}Test 8: List API Keys${NC}"
KEYS_RESP=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/api-keys")
TOTAL_KEYS=$(echo "$KEYS_RESP" | jq -r '.total // empty')

if [ -n "$TOTAL_KEYS" ]; then
    echo -e "${GREEN}✓ PASS${NC} - Found $TOTAL_KEYS API key(s)\n"
else
    echo -e "${RED}✗ FAIL${NC} - List keys failed\n"
    echo "Response: $KEYS_RESP\n"
fi

# Test 9: Get Transaction History
echo -e "${YELLOW}Test 9: Transaction History${NC}"
TRANS_RESP=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/credits/transactions?limit=10")
TRANS_TOTAL=$(echo "$TRANS_RESP" | jq -r '.total // empty')

if [ -n "$TRANS_TOTAL" ]; then
    echo -e "${GREEN}✓ PASS${NC} - Found $TRANS_TOTAL transaction(s)\n"
else
    echo -e "${RED}✗ FAIL${NC} - Transaction history failed\n"
    echo "Response: $TRANS_RESP\n"
fi

# Test 10: Get Top-Up History
echo -e "${YELLOW}Test 10: Top-Up History${NC}"
TOPUP_HIST=$(curl -s -H "Authorization: Bearer $TOKEN" "$BASE_URL/credits/top-ups?limit=10")
TOPUP_TOTAL=$(echo "$TOPUP_HIST" | jq -r '.total // empty')

if [ -n "$TOPUP_TOTAL" ]; then
    echo -e "${GREEN}✓ PASS${NC} - Found $TOPUP_TOTAL top-up(s)\n"
else
    echo -e "${RED}✗ FAIL${NC} - Top-up history failed\n"
    echo "Response: $TOPUP_HIST\n"
fi

# Summary
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}✅ Test Suite Complete!${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"

echo -e "${YELLOW}📝 Next Steps:${NC}"
echo "1. Test payment by transferring to the account shown above"
echo "2. Use the API key in your applications"
echo "3. Check the frontend at http://localhost:3000/billing"
echo "4. Monitor the logs for webhook callbacks"
echo ""
echo -e "${YELLOW}🔗 Useful URLs:${NC}"
echo "  Backend API Docs: http://localhost:8000/docs"
echo "  Frontend: http://localhost:3000"
echo "  Billing Page: http://localhost:3000/billing"
echo ""
