-- SQL Script to verify tag number status for all users
-- Run this to see which users have tags and which don't

-- Summary: Count of users with and without tags
SELECT
    CASE
        WHEN tag_number IS NULL OR tag_number = '' THEN 'Without Tag'
        ELSE 'With Tag'
    END as tag_status,
    COUNT(*) as user_count
FROM "user"
GROUP BY tag_status;

-- List all users and their tag numbers
SELECT
    id,
    email,
    full_name,
    tag_number,
    CASE
        WHEN tag_number IS NULL OR tag_number = '' THEN '❌ Missing'
        ELSE '✅ Has Tag'
    END as status,
    created_at
FROM "user"
ORDER BY
    CASE
        WHEN tag_number IS NULL OR tag_number = '' THEN 0
        ELSE 1
    END,
    created_at DESC;

-- Users WITHOUT tag numbers (need backfill)
SELECT
    id,
    email,
    full_name,
    created_at
FROM "user"
WHERE tag_number IS NULL OR tag_number = ''
ORDER BY created_at DESC;

-- Users WITH tag numbers (already processed)
SELECT
    id,
    email,
    full_name,
    tag_number,
    created_at
FROM "user"
WHERE tag_number IS NOT NULL AND tag_number != ''
ORDER BY created_at DESC;

-- Check for duplicate tag numbers (should be none)
SELECT
    tag_number,
    COUNT(*) as count
FROM "user"
WHERE tag_number IS NOT NULL AND tag_number != ''
GROUP BY tag_number
HAVING COUNT(*) > 1;
