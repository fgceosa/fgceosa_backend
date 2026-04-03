"""
Seed RBAC data - roles, permissions, and role-permission mappings
"""
import uuid
from sqlmodel import Session, select

from app.core.db import engine
from app.models import Role, Permission, RolePermission


def seed_rbac_data():
    """Seed the database with roles, permissions, and their mappings"""
    
    with Session(engine) as session:
        # Define roles
        roles_data = [
            {"name": "platform_super_admin", "description": "Platform Super Administrator with full system access"},
            {"name": "platform_admin", "description": "Platform Administrator with admin dashboard access"},
            {"name": "org_super_admin", "description": "Organization Super Administrator"},
            {"name": "org_admin", "description": "Organization Administrator with team management access"},
            {"name": "org_member", "description": "Organization Member with dashboard and usage access"},
            {"name": "staff", "description": "Staff member with limited access"},
            {"name": "user", "description": "Regular user with basic access"},
        ]
        
        # Define permissions
        permissions_data = [
            # Organization Management
            {"name": "organization:manage", "description": "Full administrative control over all organizations"},
            {"name": "organization:create", "description": "Create new organization workspaces"},
            {"name": "organization:edit", "description": "Modify existing organization details"},
            {"name": "organization:delete", "description": "Permanently remove organizations from platform"},
            {"name": "organization:view_all", "description": "Visibility into all platform organizations"},
            {"name": "organization:suspend", "description": "Restrict access for specific institutions"},
            {"name": "organization:settings", "description": "Manage global organization policy settings"},
            
            # Users & Access
            {"name": "user:manage", "description": "General user management capabilities"},
            {"name": "user:create", "description": "Provision new user accounts"},
            {"name": "user:delete", "description": "Deactivate or remove user entities"},
            {"name": "user:view_details", "description": "Access sensitive user profile information"},
            {"name": "platform:view_audit_logs", "description": "Review system-wide user activity logs"},
            {"name": "user:roles_assign", "description": "Update identity and system role assignments"},
            {"name": "user:impersonate", "description": "Securely access platform as another user"},
            {"name": "team:manage", "description": "Manage internal team memberships"},
            
            # Copilots
            {"name": "copilot:manage", "description": "Full control over AI copilot infrastructure"},
            {"name": "copilot:create", "description": "Deploy new AI copilots to the platform"},
            {"name": "copilot:edit", "description": "Update copilot personality and configurations"},
            {"name": "copilot:delete", "description": "Remove copilots from the ecosystem"},
            {"name": "copilot:view", "description": "Read-only access to copilot configurations"},
            {"name": "copilot:analytics", "description": "View deep usage analytics for specific copilots"},
            {"name": "copilot:documents_manage", "description": "Upload and manage knowledge base documents"},
            
            # Credits
            {"name": "credit:allocate", "description": "Distribute system credits to organizations"},
            {"name": "credit:view_balance", "description": "Monitor platform-wide credit liquidity"},
            {"name": "credit:transactions_view", "description": "Review all credit transfer histories"},
            {"name": "credit:treasury_manage", "description": "Direct control over the platform central treasury"},
            
            # Production Grade Billing (Wallet)
            {"name": "credit:can_top_up_org_wallet", "description": "Permission to top up organization wallet"},
            {"name": "credit:can_share_credit", "description": "Permission to share credits from organization to member"},
            {"name": "credit:can_view_org_wallet", "description": "Permission to view organization wallet balance"},
            {"name": "credit:can_manage_credit_rules", "description": "Permission to manage credit limits and rules"},
            {"name": "credit:can_use_org_credit", "description": "Permission to use organization credits for AI requests"},
            {"name": "system:view_audit_logs", "description": "Permission to view security and financial audit logs"},
            
            # Billing & Revenue
            {"name": "billing:manage", "description": "Configure pricing plans and billing cycles"},
            {"name": "revenue:view", "description": "Access financial overview dashboards"},
            {"name": "revenue:analytics", "description": "Detailed breakdown of revenue streams"},
            
            # Model Library
            {"name": "model:enable", "description": "Activate or deactivate AI models for organizations"},
            {"name": "model:configure", "description": "Manage model hyperparameters and routing"},
            {"name": "model:view", "description": "View available models and their technical specs"},
            {"name": "providers:manage", "description": "Manage API provider credentials (OpenRouter, OpenAI etc)"},
            
            # Analytics & Reporting
            {"name": "analytics:system", "description": "Access system-wide performance metrics"},
            {"name": "analytics:usage", "description": "View macro-level platform usage trends"},
            {"name": "analytics:export", "description": "Export audit and usage data to external files"},
            {"name": "dashboard:admin", "description": "Access the primary administrative command center"},
            
            # System Settings
            {"name": "enterprise:manage", "description": "Configure white-labeling and enterprise SSO"},
            {"name": "api:access", "description": "Allow usage of platform API for external integration"},
            {"name": "api:keys_manage", "description": "Create and revoke platform-wide API keys"},
            {"name": "playground:access", "description": "Access the AI Playground for prompt engineering"},
            {"name": "playground:configure", "description": "Change global playground model availability"},
            {"name": "system:health", "description": "Monitor server health and dependency status"},
            
            # Platform Settings
            {"name": "settings:general_manage", "description": "Manage general system configurations"},
            {"name": "settings:notifications_manage", "description": "Configure system-wide notifications"},
            {"name": "settings:payments_manage", "description": "Manage payment policies and settings"},
            {"name": "settings:gateways_manage", "description": "Configure payment gateway credentials"},
            {"name": "settings:email_manage", "description": "Manage SMTP and email configurations"},
            {"name": "settings:security_manage", "description": "Configure platform-wide security protocols"},
            {"name": "settings:rate_limiting_manage", "description": "Manage API rate limits"},
            {"name": "settings:integrations_manage", "description": "Configure system-level third-party integrations"},
            {"name": "settings:compliance_manage", "description": "Manage platform compliance and policies"},
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
            else:
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
            else:
                created_permissions[perm_data["name"]] = existing_perm
        
        # Define role-permission mappings
        role_permission_mappings = []
        
        # Platform Super Admin - ALL permissions
        for perm_name in created_permissions.keys():
            role_permission_mappings.append({"role": "platform_super_admin", "permission": perm_name, "allowed": True})
            
        # Add specific mappings for other roles
        additional_mappings = [
            # Platform Admin
            {"role": "platform_admin", "permission": "dashboard:admin", "allowed": True},
            {"role": "platform_admin", "permission": "revenue:view", "allowed": True},
            {"role": "platform_admin", "permission": "enterprise:manage", "allowed": True},
            {"role": "platform_admin", "permission": "user:view_details", "allowed": True},
            {"role": "platform_admin", "permission": "copilot:view", "allowed": True},
            {"role": "platform_admin", "permission": "analytics:system", "allowed": True},
            
            # Org Super Admin
            {"role": "org_super_admin", "permission": "organization:settings", "allowed": True},
            {"role": "org_super_admin", "permission": "user:manage", "allowed": True},
            {"role": "org_super_admin", "permission": "team:manage", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:view_balance", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:transactions_view", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:allocate", "allowed": True},
            {"role": "org_super_admin", "permission": "copilot:manage", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:can_top_up_org_wallet", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:can_share_credit", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:can_view_org_wallet", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:can_manage_credit_rules", "allowed": True},
            {"role": "org_super_admin", "permission": "credit:can_use_org_credit", "allowed": True},
            {"role": "org_super_admin", "permission": "system:view_audit_logs", "allowed": True},
            
            # Org Admin
            {"role": "org_admin", "permission": "team:manage", "allowed": True},
            {"role": "org_admin", "permission": "user:create", "allowed": True},
            {"role": "org_admin", "permission": "copilot:view", "allowed": True},
            {"role": "org_admin", "permission": "copilot:create", "allowed": True},
            {"role": "org_admin", "permission": "copilot:manage", "allowed": True},
            {"role": "org_admin", "permission": "copilot:delete", "allowed": True},
            {"role": "org_admin", "permission": "credit:transactions_view", "allowed": True},
            {"role": "org_admin", "permission": "credit:view_balance", "allowed": True},
            {"role": "org_admin", "permission": "credit:can_share_credit", "allowed": True},
            {"role": "org_admin", "permission": "credit:can_view_org_wallet", "allowed": True},
            {"role": "org_admin", "permission": "credit:can_manage_credit_rules", "allowed": True},
            {"role": "org_admin", "permission": "credit:can_use_org_credit", "allowed": True},
            
            # Staff
            {"role": "staff", "permission": "api:access", "allowed": True},
            {"role": "staff", "permission": "playground:access", "allowed": True},
            {"role": "staff", "permission": "copilot:view", "allowed": True},
            {"role": "staff", "permission": "credit:transactions_view", "allowed": True},
            
            # Org Member
            {"role": "org_member", "permission": "api:access", "allowed": True},
            {"role": "org_member", "permission": "playground:access", "allowed": True},
            {"role": "org_member", "permission": "credit:view_balance", "allowed": True},
            {"role": "org_member", "permission": "credit:transactions_view", "allowed": True},
            {"role": "org_member", "permission": "copilot:view", "allowed": True},

            # User
            {"role": "user", "permission": "api:access", "allowed": True},
            {"role": "user", "permission": "playground:access", "allowed": True},
            {"role": "user", "permission": "providers:manage", "allowed": True},
            {"role": "user", "permission": "credit:transactions_view", "allowed": True},
        ]
        
        role_permission_mappings.extend(additional_mappings)
        
        # Create role-permission mappings
        for mapping in role_permission_mappings:
            role = created_roles[mapping["role"]]
            permission = created_permissions[mapping["permission"]]
            
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
        print("RBAC data seeded successfully!")


if __name__ == "__main__":
    seed_rbac_data()