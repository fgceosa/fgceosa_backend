-- SQL Script to credit Devscourt AI workspace with 50 credits
-- Run this directly in your PostgreSQL database if the Python script doesn't work

-- Step 1: Check current balance
SELECT
    id,
    name,
    credits_balance,
    created_at
FROM workspace
WHERE name = 'Devscourt AI';

-- Step 2: Update workspace credits (add 50 credits)
UPDATE workspace
SET credits_balance = credits_balance + 50
WHERE name = 'Devscourt AI'
RETURNING id, name, credits_balance;

-- Step 3: Create transaction record
-- Note: Replace <workspace_id> with the actual UUID from the SELECT query above
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
    'Manual credit addition: 50 credits for initial setup',
    'completed',
    NOW(),
    NOW()
FROM workspace
WHERE name = 'Devscourt AI'
RETURNING id, workspace_id, amount, balance, description;

-- Step 4: Verify the changes
SELECT
    w.name as workspace_name,
    w.credits_balance,
    t.amount as last_transaction_amount,
    t.description as last_transaction_description,
    t.created_at as last_transaction_date
FROM workspace w
LEFT JOIN workspace_credit_transaction t ON t.workspace_id = w.id
WHERE w.name = 'Devscourt AI'
ORDER BY t.created_at DESC
LIMIT 1;
