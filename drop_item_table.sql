-- Drop the item table since we're removing item CRUD functionality
-- Run this in Adminer after setting up RBAC

-- Drop the item table (this will also drop any foreign key constraints automatically)
DROP TABLE IF EXISTS item CASCADE;

-- Verify the table is gone
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
AND table_name = 'item';