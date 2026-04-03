-- Quick script to add 50 credits to a workspace
-- INSTRUCTIONS:
-- 1. First, find your workspace ID by running the check script
-- 2. Replace 'YOUR_WORKSPACE_ID_HERE' with the actual UUID
-- 3. Run this script

-- Step 1: Check current balance
SELECT
    id,
    name,
    credits_balance,
    owner_id
FROM workspace
WHERE id = 'YOUR_WORKSPACE_ID_HERE';

-- Step 2: Add 50 credits
UPDATE workspace
SET credits_balance = credits_balance + 50
WHERE id = 'YOUR_WORKSPACE_ID_HERE'
RETURNING id, name, credits_balance as new_balance;

-- Step 3: Create transaction record
INSERT INTO workspace_credit_transaction (
    id,
    workspace_id,
    type,
    amount,
    balance,
    description,
    status,
    created_at,
    updated_at
)
SELECT
    gen_random_uuid(),
    id,
    'purchase',
    50,
    credits_balance,
    'Manual credit addition: 50 credits',
    'completed',
    NOW(),
    NOW()
FROM workspace
WHERE id = 'YOUR_WORKSPACE_ID_HERE'
RETURNING id, workspace_id, amount, balance;
