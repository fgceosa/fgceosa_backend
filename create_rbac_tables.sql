-- Create RBAC tables manually
-- Run this SQL script in Adminer to create the RBAC tables

-- Create role table
CREATE TABLE IF NOT EXISTS role (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) UNIQUE NOT NULL,
    description VARCHAR(255),
    CONSTRAINT idx_role_name UNIQUE (name)
);

-- Create permission table  
CREATE TABLE IF NOT EXISTS permission (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) UNIQUE NOT NULL,
    description VARCHAR(255),
    CONSTRAINT idx_permission_name UNIQUE (name)
);

-- Create userrole junction table (many-to-many between user and role)
CREATE TABLE IF NOT EXISTS userrole (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES "user"(id) ON DELETE CASCADE,
    role_id UUID NOT NULL REFERENCES role(id) ON DELETE CASCADE,
    UNIQUE(user_id, role_id)
);

-- Create rolepermission junction table (many-to-many between role and permission)
CREATE TABLE IF NOT EXISTS rolepermission (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    role_id UUID NOT NULL REFERENCES role(id) ON DELETE CASCADE,
    permission_id UUID NOT NULL REFERENCES permission(id) ON DELETE CASCADE,
    allowed BOOLEAN DEFAULT TRUE,
    UNIQUE(role_id, permission_id)
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_userrole_user_id ON userrole(user_id);
CREATE INDEX IF NOT EXISTS idx_userrole_role_id ON userrole(role_id);
CREATE INDEX IF NOT EXISTS idx_rolepermission_role_id ON rolepermission(role_id);
CREATE INDEX IF NOT EXISTS idx_rolepermission_permission_id ON rolepermission(permission_id);

-- Insert the 6 roles
INSERT INTO role (name, description) VALUES
    ('platform_super_admin', 'Platform Super Administrator with full system access'),
    ('platform_admin', 'Platform Administrator with admin dashboard access'),
    ('org_super_admin', 'Organization Super Administrator'),
    ('org_admin', 'Organization Administrator with team management access'),
    ('staff', 'Staff member with limited access'),
    ('user', 'Regular user with basic access')
ON CONFLICT (name) DO NOTHING;

-- Insert permissions
INSERT INTO permission (name, description) VALUES
    ('organization:manage', 'Manage organizations'),
    ('user:manage', 'Manage users'),
    ('user:create', 'Create users'),
    ('team:manage', 'Manage team members'),
    ('dashboard:admin', 'Access admin dashboard'),
    ('revenue:view', 'View revenue data'),
    ('enterprise:manage', 'Manage enterprise features'),
    ('api:access', 'Access API endpoints'),
    ('playground:access', 'Access AI playground'),
    ('providers:manage', 'Manage API providers')
ON CONFLICT (name) DO NOTHING;

-- Insert role-permission mappings
-- Platform Super Admin - all permissions
INSERT INTO rolepermission (role_id, permission_id, allowed)
SELECT r.id, p.id, true
FROM role r, permission p
WHERE r.name = 'platform_super_admin'
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Platform Admin - admin dashboard, revenue, enterprise
INSERT INTO rolepermission (role_id, permission_id, allowed)
SELECT r.id, p.id, true
FROM role r, permission p
WHERE r.name = 'platform_admin' 
AND p.name IN ('dashboard:admin', 'revenue:view', 'enterprise:manage')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Org Super Admin - org and user management
INSERT INTO rolepermission (role_id, permission_id, allowed)
SELECT r.id, p.id, true
FROM role r, permission p
WHERE r.name = 'org_super_admin' 
AND p.name IN ('organization:manage', 'user:manage', 'user:create', 'team:manage')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Org Admin - team management
INSERT INTO rolepermission (role_id, permission_id, allowed)
SELECT r.id, p.id, true
FROM role r, permission p
WHERE r.name = 'org_admin' 
AND p.name IN ('team:manage', 'user:create')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Staff - basic access
INSERT INTO rolepermission (role_id, permission_id, allowed)
SELECT r.id, p.id, true
FROM role r, permission p
WHERE r.name = 'staff' 
AND p.name IN ('api:access', 'playground:access', 'providers:manage')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- User - basic user access
INSERT INTO rolepermission (role_id, permission_id, allowed)
SELECT r.id, p.id, true
FROM role r, permission p
WHERE r.name = 'user' 
AND p.name IN ('api:access', 'playground:access', 'providers:manage')
ON CONFLICT (role_id, permission_id) DO NOTHING;

-- Assign default 'user' role to all existing users who don't have roles yet
INSERT INTO userrole (user_id, role_id)
SELECT u.id, r.id
FROM "user" u, role r
WHERE r.name = 'user'
AND NOT EXISTS (
    SELECT 1 FROM userrole ur WHERE ur.user_id = u.id
)
ON CONFLICT (user_id, role_id) DO NOTHING;