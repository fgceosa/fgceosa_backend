-- ============================================================
-- Check and Credit Devscourt AI Workspace
-- For user: hello@devscourtai.com
-- ============================================================

-- Step 1: Find user by email
SELECT
    id as user_id,
    email,
    first_name,
    last_name,
    created_at
FROM "user"
WHERE email = 'hello@devscourtai.com';

-- Step 2: Find all workspaces for this user
SELECT
    w.id as workspace_id,
    w.name as workspace_name,
    w.credits_balance,
    w.owner_id,
    w.status,
    wm.role as user_role,
    wm.credits_allocated as member_allocated_credits,
    u.email as owner_email
FROM workspace w
INNER JOIN workspace_member wm ON wm.workspace_id = w.id
INNER JOIN "user" u ON u.id = wm.user_id
WHERE u.email = 'hello@devscourtai.com';

-- Step 3: Show all workspaces with name containing 'Devscourt'
SELECT
    id,
    name,
    credits_balance,
    owner_id,
    status,
    created_at
FROM workspace
WHERE LOWER(name) LIKE LOWER('%Devscourt%')
   OR LOWER(name) LIKE LOWER('%DevsCourt%');

-- ============================================================
-- If workspace exists, add 50 credits
-- ============================================================

-- Check current balance first
SELECT
    id,
    name,
    credits_balance as current_balance
FROM workspace
WHERE LOWER(name) = LOWER('Devscourt AI')
   OR LOWER(name) = LOWER('DevsCourt AI');

-- Add 50 credits (uncomment and run after verifying workspace name above)
-- UPDATE workspace
-- SET credits_balance = credits_balance + 50
-- WHERE LOWER(name) = LOWER('Devscourt AI')
-- RETURNING id, name, credits_balance as new_balance;

-- Create transaction record (uncomment after updating credits)
-- INSERT INTO workspace_credit_transaction (
--     id,
--     workspace_id,
--     type,
--     amount,
--     balance,
--     description,
--     status,
--     created_at,
--     updated_at
-- )
-- SELECT
--     gen_random_uuid(),
--     id,
--     'purchase',
--     50,
--     credits_balance,
--     'Manual credit addition: 50 credits for initial setup',
--     'completed',
--     NOW(),
--     NOW()
-- FROM workspace
-- WHERE LOWER(name) = LOWER('Devscourt AI')
-- RETURNING id, workspace_id, amount, balance, description;

-- ============================================================
-- Alternative: Add credits to ANY workspace by ID
-- ============================================================

-- Replace <workspace_id> with actual UUID from queries above
-- UPDATE workspace
-- SET credits_balance = credits_balance + 50
-- WHERE id = '<workspace_id>'
-- RETURNING id, name, credits_balance;

-- ============================================================
-- Verify the final result
-- ============================================================

SELECT
    w.name as workspace_name,
    w.credits_balance,
    w.status,
    u.email as owner_email,
    COUNT(wm.id) as member_count
FROM workspace w
LEFT JOIN "user" u ON u.id = w.owner_id
LEFT JOIN workspace_member wm ON wm.workspace_id = w.id
WHERE u.email = 'hello@devscourtai.com'
   OR LOWER(w.name) LIKE LOWER('%Devscourt%')
GROUP BY w.id, w.name, w.credits_balance, w.status, u.email;
