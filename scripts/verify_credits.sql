-- Verify credits were added to "Devscourt AI" workspace
-- Run this to confirm the database has the correct value

SELECT
    w.id,
    w.name,
    w.credits_balance as current_balance,
    w.status,
    u.email as owner_email,
    w.created_at,
    w.updated_at
FROM workspace w
LEFT JOIN "user" u ON u.id = w.owner_id
WHERE w.name = 'Devscourt AI';

-- Show recent credit transactions for this workspace
SELECT
    t.id,
    t.type,
    t.amount,
    t.balance as workspace_balance_after_transaction,
    t.description,
    t.status,
    t.created_at
FROM workspace_credit_transaction t
INNER JOIN workspace w ON w.id = t.workspace_id
WHERE w.name = 'Devscourt AI'
ORDER BY t.created_at DESC
LIMIT 10;
