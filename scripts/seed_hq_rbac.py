"""
Enhanced RBAC seed script for HQ Roles & Permissions Management
"""
import uuid
from sqlmodel import Session, select

from app.core.db import engine
from app.models import Role, Permission, RolePermission


def seed_hq_rbac_data():
    """Seed the database with HQ-specific roles, permissions, and their mappings"""
    
    with Session(engine) as session:
        # Define HQ roles
        roles_data = [
            {
                "name": "platform_super_admin",
                "description": "Complete oversight and ultimate authority across all platform systems and governance"
            },
            {
                "name": "platform_admin",
                "description": "Day-to-day platform management and organization setup"
            },
            {
                "name": "billing_revenue_admin",
                "description": "Focused on financial operations, revenue tracking, and credit treasury management"
            },
            {
                "name": "operations_admin",
                "description": "Responsible for organization support, onboarding, and workspace management"
            },
            {
                "name": "ai_copilot_admin",
                "description": "Manages platform AI models, copilot configurations, and usage analytics"
            },
            {
                "name": "support_admin",
                "description": "Read-only access to help desk and user troubleshooting data"
            },
            # Keep existing roles for backward compatibility
            {
                "name": "org_super_admin",
                "description": "Organization Super Administrator"
            },
            {
                "name": "org_admin",
                "description": "Organization Administrator with team management access"
            },
            {
                "name": "staff",
                "description": "Staff member with limited access"
            },
            {
                "name": "user",
                "description": "Regular user with basic access"
            },
        ]
        
        # Define HQ-specific permissions
        permissions_data = [
            # Organization Management
            {"name": "organization:view", "description": "View list and details of all organizations"},
            {"name": "organization:create", "description": "Create new organization workspaces"},
            {"name": "organization:suspend", "description": "Restrict access for organizations"},
            {"name": "organization:manage", "description": "Full organization management"},
            
            # Users & Access
            {"name": "platform:view_audit_logs", "description": "Review system-wide user activity logs"},
            {"name": "user:manage_hq", "description": "Create and edit platform administrators"},
            {"name": "user:manage", "description": "Manage users"},
            {"name": "user:create", "description": "Create users"},
            {"name": "user:view_audit", "description": "View system-wide security audit logs"},
            {"name": "role:manage", "description": "Edit custom role permissions"},
            {"name": "team:manage", "description": "Manage team members"},
            
            # Credits
            {"name": "credit:allocate", "description": "Distribute credits to organizations"},
            {"name": "credit:transactions_view", "description": "Review all credit transfer histories"},
            {"name": "credit:treasury_manage", "description": "Manage platform credit treasury"},
            
            # Billing & Revenue
            {"name": "revenue:view", "description": "Access platform revenue analytics"},
            {"name": "billing:manage_pricing", "description": "Update plan costs and credit rates"},
            
            # Copilots
            {"name": "copilot:view", "description": "View copilot configurations and list"},
            {"name": "copilot:create", "description": "Create new AI copilots"},
            {"name": "copilot:update", "description": "Update existing copilot configurations"},
            {"name": "copilot:delete", "description": "Delete AI copilots"},
            {"name": "copilot:publish", "description": "Publish and deploy copilots"},
            {"name": "copilot:manage", "description": "Full copilot management (Create/Edit/Delete/Publish)"}, # Kept for backward compat/super access
            {"name": "copilot:analytics", "description": "View performance data for all copilots"},
            
            # Model Library
            {"name": "model:enable", "description": "Activate AI models for users"},
            {"name": "model:provider_keys", "description": "Manage global API provider credentials"},
            {"name": "providers:manage", "description": "Manage API providers"},
            
            # Analytics
            {"name": "dashboard:admin", "description": "Access admin dashboard"},
            {"name": "analytics:platform", "description": "View platform-wide analytics"},
            
            # System Settings
            {"name": "enterprise:manage", "description": "Manage enterprise features"},
            {"name": "api:access", "description": "Access API endpoints"},
            {"name": "playground:access", "description": "Access AI playground"},
            
            # Platform Settings
            {"name": "settings:general_manage", "description": "Manage general system configurations and global constants"},
            {"name": "settings:notifications_manage", "description": "Configure system-wide notification templates and delivery rules"},
            {"name": "settings:payments_manage", "description": "Manage payment policies, tax rules, and currency settings"},
            {"name": "settings:gateways_manage", "description": "Configure payment gateway credentials (Monnify, Flutterwave, etc.)"},
            {"name": "settings:email_manage", "description": "Manage SMTP and email service provider configurations"},
            {"name": "settings:security_manage", "description": "Configure platform-wide security protocols and multi-factor auth"},
            {"name": "settings:rate_limiting_manage", "description": "Manage API rate limits and throttling policies"},
            {"name": "settings:integrations_manage", "description": "Configure system-level third-party integrations (Slack, Google HL, etc.)"},
            {"name": "settings:compliance_manage", "description": "Manage platform compliance, data retention, and privacy policies"},
        ]
        
        # Create roles if they don't exist
        created_roles = {}
        for role_data in roles_data:
            existing_role = session.exec(select(Role).where(Role.name == role_data["name"])).first()
            if not existing_role:
                role = Role(**role_data)
                session.add(role)
                session.commit()
                session.refresh(role)
                created_roles[role_data["name"]] = role
                print(f"✓ Created role: {role_data['name']}")
            else:
                # Update description if changed
                if existing_role.description != role_data["description"]:
                    existing_role.description = role_data["description"]
                    session.add(existing_role)
                    session.commit()
                    print(f"✓ Updated role: {role_data['name']}")
                created_roles[role_data["name"]] = existing_role
                
        # Create permissions if they don't exist
        created_permissions = {}
        for perm_data in permissions_data:
            existing_perm = session.exec(select(Permission).where(Permission.name == perm_data["name"])).first()
            if not existing_perm:
                permission = Permission(**perm_data)
                session.add(permission)
                session.commit()
                session.refresh(permission)
                created_permissions[perm_data["name"]] = permission
                print(f"✓ Created permission: {perm_data['name']}")
            else:
                created_permissions[perm_data["name"]] = existing_perm
        
        # Define role-permission mappings for HQ roles
        role_permission_mappings = [
            # Platform Super Admin (Platform Owner) - all permissions
            {"role": "platform_super_admin", "permission": "organization:view", "allowed": True},
            {"role": "platform_super_admin", "permission": "organization:create", "allowed": True},
            {"role": "platform_super_admin", "permission": "organization:suspend", "allowed": True},
            {"role": "platform_super_admin", "permission": "organization:manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "user:manage_hq", "allowed": True},
            {"role": "platform_super_admin", "permission": "user:manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "user:create", "allowed": True},
            {"role": "platform_super_admin", "permission": "user:view_audit", "allowed": True},
            {"role": "platform_super_admin", "permission": "role:manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "team:manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "credit:allocate", "allowed": True},
            {"role": "platform_super_admin", "permission": "credit:treasury_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "revenue:view", "allowed": True},
            {"role": "platform_super_admin", "permission": "billing:manage_pricing", "allowed": True},
            # Copilot Permissions
            {"role": "platform_super_admin", "permission": "copilot:view", "allowed": True},
            {"role": "platform_super_admin", "permission": "copilot:create", "allowed": True},
            {"role": "platform_super_admin", "permission": "copilot:update", "allowed": True},
            {"role": "platform_super_admin", "permission": "copilot:delete", "allowed": True},
            {"role": "platform_super_admin", "permission": "copilot:publish", "allowed": True},
            {"role": "platform_super_admin", "permission": "copilot:manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "copilot:analytics", "allowed": True},
            
            {"role": "platform_super_admin", "permission": "model:enable", "allowed": True},
            {"role": "platform_super_admin", "permission": "model:provider_keys", "allowed": True},
            {"role": "platform_super_admin", "permission": "providers:manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "dashboard:admin", "allowed": True},
            {"role": "platform_super_admin", "permission": "analytics:platform", "allowed": True},
            {"role": "platform_super_admin", "permission": "enterprise:manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "api:access", "allowed": True},
            {"role": "platform_super_admin", "permission": "playground:access", "allowed": True},
            
            # Platform Settings
            {"role": "platform_super_admin", "permission": "settings:general_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "settings:notifications_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "settings:payments_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "settings:gateways_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "settings:email_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "settings:security_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "settings:rate_limiting_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "settings:integrations_manage", "allowed": True},
            {"role": "platform_super_admin", "permission": "settings:compliance_manage", "allowed": True},
            
            # Platform Admin - day-to-day management (no billing/credits)
            {"role": "platform_admin", "permission": "organization:view", "allowed": True},
            {"role": "platform_admin", "permission": "organization:create", "allowed": True},
            {"role": "platform_admin", "permission": "user:manage", "allowed": True},
            {"role": "platform_admin", "permission": "user:create", "allowed": True},
            # Copilot Permissions
            {"role": "platform_admin", "permission": "copilot:view", "allowed": True},
            {"role": "platform_admin", "permission": "copilot:create", "allowed": True},
            {"role": "platform_admin", "permission": "copilot:update", "allowed": True},
            {"role": "platform_admin", "permission": "copilot:delete", "allowed": True},
            {"role": "platform_admin", "permission": "copilot:publish", "allowed": True},
            {"role": "platform_admin", "permission": "copilot:manage", "allowed": True},
            {"role": "platform_admin", "permission": "copilot:analytics", "allowed": True},
            
            {"role": "platform_admin", "permission": "model:enable", "allowed": True},
            {"role": "platform_admin", "permission": "dashboard:admin", "allowed": True},
            {"role": "platform_admin", "permission": "analytics:platform", "allowed": True},
            
            # Billing & Revenue Admin
            {"role": "billing_revenue_admin", "permission": "revenue:view", "allowed": True},
            {"role": "billing_revenue_admin", "permission": "billing:manage_pricing", "allowed": True},
            {"role": "billing_revenue_admin", "permission": "credit:allocate", "allowed": True},
            {"role": "billing_revenue_admin", "permission": "credit:treasury_manage", "allowed": True},
            {"role": "billing_revenue_admin", "permission": "dashboard:admin", "allowed": True},
            
            # Operations Admin
            {"role": "operations_admin", "permission": "organization:view", "allowed": True},
            {"role": "operations_admin", "permission": "organization:create", "allowed": True},
            {"role": "operations_admin", "permission": "organization:manage", "allowed": True},
            {"role": "operations_admin", "permission": "user:manage", "allowed": True},
            {"role": "operations_admin", "permission": "revenue:view", "allowed": True},
            
            # AI / Copilot Admin
            # Copilot Permissions
            {"role": "ai_copilot_admin", "permission": "copilot:view", "allowed": True},
            {"role": "ai_copilot_admin", "permission": "copilot:create", "allowed": True},
            {"role": "ai_copilot_admin", "permission": "copilot:update", "allowed": True},
            {"role": "ai_copilot_admin", "permission": "copilot:delete", "allowed": True},
            {"role": "ai_copilot_admin", "permission": "copilot:publish", "allowed": True},
            {"role": "ai_copilot_admin", "permission": "copilot:manage", "allowed": True},
            {"role": "ai_copilot_admin", "permission": "copilot:analytics", "allowed": True},
            
            {"role": "ai_copilot_admin", "permission": "model:enable", "allowed": True},
            {"role": "ai_copilot_admin", "permission": "model:provider_keys", "allowed": True},
            {"role": "ai_copilot_admin", "permission": "providers:manage", "allowed": True},
            
            # Support Admin (read-only)
            {"role": "support_admin", "permission": "organization:view", "allowed": True},
            {"role": "support_admin", "permission": "user:view_audit", "allowed": True},
            {"role": "support_admin", "permission": "analytics:platform", "allowed": True},
            {"role": "support_admin", "permission": "copilot:view", "allowed": True}, # Can view copilots

            
            # Org Super Admin
            {"role": "org_super_admin", "permission": "organization:manage", "allowed": True},
            {"role": "org_super_admin", "permission": "user:manage", "allowed": True},
            {"role": "org_super_admin", "permission": "user:create", "allowed": True},
            {"role": "org_super_admin", "permission": "team:manage", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:allocate", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:transactions_view", "allowed": True},
            
            # Org Admin
            {"role": "org_admin", "permission": "team:manage", "allowed": True},
            {"role": "org_admin", "permission": "user:create", "allowed": True},
            {"role": "org_admin", "permission": "credit:transactions_view", "allowed": True},
            
            # Staff
            {"role": "staff", "permission": "api:access", "allowed": True},
            {"role": "staff", "permission": "playground:access", "allowed": True},
            {"role": "staff", "permission": "providers:manage", "allowed": True},
            {"role": "staff", "permission": "credit:transactions_view", "allowed": True},
            
            # User
            {"role": "user", "permission": "api:access", "allowed": True},
            {"role": "user", "permission": "playground:access", "allowed": True},
            {"role": "user", "permission": "providers:manage", "allowed": True},
            {"role": "user", "permission": "credit:transactions_view", "allowed": True},
        ]
        
        # Create role-permission mappings
        for mapping in role_permission_mappings:
            role = created_roles.get(mapping["role"])
            permission = created_permissions.get(mapping["permission"])
            
            if not role or not permission:
                print(f"⚠ Skipping mapping: {mapping['role']} -> {mapping['permission']} (not found)")
                continue
            
            # Check if mapping already exists
            existing_mapping = session.exec(
                select(RolePermission)
                .where(RolePermission.role_id == role.id)
                .where(RolePermission.permission_id == permission.id)
            ).first()
            
            if not existing_mapping:
                role_permission = RolePermission(
                    role_id=role.id,
                    permission_id=permission.id,
                    allowed=mapping["allowed"]
                )
                session.add(role_permission)
        
        session.commit()
        print("\n✅ HQ RBAC data seeded successfully!")
        print(f"   Roles: {len(created_roles)}")
        print(f"   Permissions: {len(created_permissions)}")
        print(f"   Mappings: {len(role_permission_mappings)}")


if __name__ == "__main__":
    seed_hq_rbac_data()
