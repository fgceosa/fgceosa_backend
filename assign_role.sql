-- Assign platform_admin role to fola@gmail.com for testing
-- Run this in Adminer after the main RBAC script

INSERT INTO userrole (user_id, role_id)
SELECT u.id, r.id
FROM "user" u, role r
WHERE u.email = 'fola@gmail.com' 
AND r.name = 'platform_admin'
ON CONFLICT (user_id, role_id) DO NOTHING;

-- Check what roles the user now has
SELECT 
    u.email,
    u.full_name,
    r.name as role_name,
    r.description as role_description
FROM "user" u
JOIN userrole ur ON u.id = ur.user_id
JOIN role r ON ur.role_id = r.id
WHERE u.email = 'fola@gmail.com'
ORDER BY r.name;