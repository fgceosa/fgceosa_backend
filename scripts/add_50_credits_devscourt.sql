-- Add 50 credits to "Devscourt AI" workspace
-- Ready to run - no modifications needed!

-- Step 1: Check current state
SELECT
    id,
    name,
    credits_balance as current_balance,
    owner_id,
    status,
    created_at
FROM workspace
WHERE name = 'Devscourt AI';

-- Step 2: Add 50 credits
UPDATE workspace
SET credits_balance = credits_balance + 50
WHERE name = 'Devscourt AI'
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
    'Manual credit addition: 50 credits for initial setup',
    'completed',
    NOW(),
    NOW()
FROM workspace
WHERE name = 'Devscourt AI'
RETURNING
    id as transaction_id,
    workspace_id,
    amount,
    balance as workspace_balance_after,
    description,
    created_at;

-- Step 4: Verify final state
SELECT
    w.id as workspace_id,
    w.name as workspace_name,
    w.credits_balance as current_balance,
    w.status,
    u.email as owner_email,
    COUNT(t.id) as transaction_count,
    MAX(t.created_at) as last_transaction_date
FROM workspace w
LEFT JOIN "user" u ON u.id = w.owner_id
LEFT JOIN workspace_credit_transaction t ON t.workspace_id = w.id
WHERE w.name = 'Devscourt AI'
GROUP BY w.id, w.name, w.credits_balance, w.status, u.email;
