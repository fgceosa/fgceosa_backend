"""
RBAC seed logic for initializing roles and permissions.
"""
import logging
from sqlmodel import Session, select
from app.models import Role, Permission, RolePermission

logger = logging.getLogger(__name__)

# System roles that cannot be deleted or have name changed
SYSTEM_ROLES_DATA = [
    {"name": "platform_super_admin", "description": "Complete oversight and ultimate authority across all platform systems and governance"},
    {"name": "platform_admin", "description": "Day-to-day platform management and organization setup"},
    {"name": "billing_revenue_admin", "description": "Focused on financial operations, revenue tracking, and credit treasury management"},
    {"name": "operations_admin", "description": "Responsible for organization support, onboarding, and workspace management"},
    {"name": "ai_copilot_admin", "description": "Manages platform AI models, copilot configurations, and usage analytics"},
    {"name": "support_admin", "description": "Read-only access to help desk and user troubleshooting data"},
    {"name": "org_super_admin", "description": "Organization Super Administrator"},
    {"name": "org_admin", "description": "Organization Administrator with team management access"},
    {"name": "org_member", "description": "Organization Member with dashboard and usage access"},
    {"name": "staff", "description": "Staff member with limited access"},
    {"name": "user", "description": "Regular user with basic access"},
]

# Standard technical permissions
SYSTEM_PERMISSIONS_DATA = [
    # Organization Management
    {"name": "organization:view", "description": "View list and details of all organizations"},
    {"name": "organization:create", "description": "Create new organization workspaces"},
    {"name": "organization:suspend", "description": "Restrict access for organizations"},
    {"name": "organization:manage", "description": "Full organization management"},
    {"name": "organization:edit", "description": "Modify existing organization details"},
    {"name": "organization:delete", "description": "Permanently remove organizations from platform"},
    {"name": "organization:view_all", "description": "Visibility into all platform organizations"},
    {"name": "organization:settings", "description": "Manage global organization policy settings"},
    
    # Users & Access
    {"name": "user:manage", "description": "General user management capabilities"},
    {"name": "user:create", "description": "Provision new user accounts"},
    {"name": "user:delete", "description": "Deactivate or remove user entities"},
    {"name": "user:view_details", "description": "Access sensitive user profile information"},
    {"name": "user:roles_assign", "description": "Update identity and system role assignments"},
    {"name": "user:impersonate", "description": "Securely access platform as another user"},
    {"name": "user:manage_hq", "description": "Create and edit platform administrators"},
    {"name": "user:view_audit", "description": "View system-wide security audit logs"},
    {"name": "platform:view_audit_logs", "description": "Review system-wide user activity logs"},
    {"name": "role:manage", "description": "Edit custom role permissions"},
    {"name": "team:manage", "description": "Manage team members"},
    
    # Copilot Permissions
    {"name": "copilot:manage", "description": "Full control over AI copilot infrastructure"},
    {"name": "copilot:create", "description": "Deploy new AI copilots to the platform"},
    {"name": "copilot:edit", "description": "Update copilot personality and configurations"},
    {"name": "copilot:update", "description": "Update existing copilot configurations"},
    {"name": "copilot:delete", "description": "Remove copilots from the ecosystem"},
    {"name": "copilot:view", "description": "Read-only access to copilot configurations"},
    {"name": "copilot:publish", "description": "Publish and deploy copilots"},
    {"name": "copilot:analytics", "description": "View deep usage analytics for specific copilots"},
    {"name": "copilot:documents_manage", "description": "Upload and manage knowledge base documents"},
    
    # Credits & Wallet
    {"name": "credit:allocate", "description": "Distribute system credits to organizations"},
    {"name": "credit:view_balance", "description": "Monitor platform-wide credit liquidity"},
    {"name": "credit:transactions_view", "description": "Review all credit transfer histories"},
    {"name": "credit:treasury_manage", "description": "Direct control over the platform central treasury"},
    {"name": "credit:can_top_up_org_wallet", "description": "Permission to top up organization wallet"},
    {"name": "credit:can_share_credit", "description": "Permission to share credits from organization to member"},
    {"name": "credit:can_view_org_wallet", "description": "Permission to view organization wallet balance"},
    {"name": "credit:can_manage_credit_rules", "description": "Permission to manage credit limits and rules"},
    {"name": "credit:can_use_org_credit", "description": "Permission to use organization credits for AI requests"},
    {"name": "system:view_audit_logs", "description": "Permission to view security and financial audit logs"},
    
    # Billing & Revenue
    {"name": "billing:manage", "description": "Configure pricing plans and billing cycles"},
    {"name": "billing:manage_pricing", "description": "Update plan costs and credit rates"},
    {"name": "revenue:view", "description": "Access financial overview dashboards"},
    {"name": "revenue:analytics", "description": "Detailed breakdown of revenue streams"},
    
    # Model Library
    {"name": "model:enable", "description": "Activate or deactivate AI models for organizations"},
    {"name": "model:configure", "description": "Manage model hyperparameters and routing"},
    {"name": "model:view", "description": "View available models and their technical specs"},
    {"name": "model:provider_keys", "description": "Manage global API provider credentials"},
    {"name": "providers:manage", "description": "Manage API provider credentials (OpenRouter, OpenAI etc)"},
    
    # Analytics & Reporting
    {"name": "analytics:platform", "description": "View platform-wide analytics"},
    {"name": "analytics:system", "description": "Access system-wide performance metrics"},
    {"name": "analytics:usage", "description": "View macro-level platform usage trends"},
    {"name": "analytics:export", "description": "Export audit and usage data to external files"},
    {"name": "dashboard:admin", "description": "Access the primary administrative command center"},
    
    # System & Enterprise Settings
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

    # Frontend compatibility permissions
    {"name": "org:view", "description": "View organization details"},
    {"name": "org:update", "description": "Update organization settings"},
    {"name": "org:billing", "description": "Manage organization billing"},
    {"name": "team:view", "description": "View team members"},
    {"name": "team:invite", "description": "Invite team members"},
    {"name": "team:remove", "description": "Remove team members"},
    {"name": "workspace:view", "description": "View workspaces"},
    {"name": "workspace:create", "description": "Create workspaces"},
    {"name": "workspace:delete", "description": "Delete workspaces"},
    {"name": "models:view", "description": "View models"},
    {"name": "models:create", "description": "Create models"},
    {"name": "copilot:use", "description": "Use AI copilots"},
]

def seed_rbac(session: Session) -> None:
    """Seed the database with roles, permissions, and their mappings"""
    logger.info("Seeding RBAC data...")
    
    # 1. Create roles if they don't exist
    created_roles = {}
    for role_data in SYSTEM_ROLES_DATA:
        existing_role = session.exec(select(Role).where(Role.name == role_data["name"])).first()
        if not existing_role:
            role = Role(**role_data)
            session.add(role)
            session.flush()
            created_roles[role_data["name"]] = role
        else:
            created_roles[role_data["name"]] = existing_role
            
    # 2. Create permissions if they don't exist
    created_permissions = {}
    for perm_data in SYSTEM_PERMISSIONS_DATA:
        existing_perm = session.exec(select(Permission).where(Permission.name == perm_data["name"])).first()
        if not existing_perm:
            permission = Permission(**perm_data)
            session.add(permission)
            session.flush()
            created_permissions[perm_data["name"]] = permission
        else:
            created_permissions[perm_data["name"]] = existing_perm
    
    # 3. Pre-fetch all existing RolePermission mappings to avoid N+1 queries
    existing_rp_data = session.exec(select(RolePermission)).all()
    # Create a set of (role_id, permission_id) for fast lookup
    rp_lookup = {(rp.role_id, rp.permission_id) for rp in existing_rp_data}
    
    # 4. Define mapping logic for Super Admin
    # Platform Super Admin gets EVERY permission in the database
    psa_role = created_roles.get("platform_super_admin")
    if psa_role:
        all_perms = list(created_permissions.values())
        for perm in all_perms:
            if (psa_role.id, perm.id) not in rp_lookup:
                rp = RolePermission(role_id=psa_role.id, permission_id=perm.id, allowed=True)
                session.add(rp)
                # Update lookup in case we use it later in the same function
                rp_lookup.add((psa_role.id, perm.id))
    
    # Define specific mappings for other roles
    # 1. Base permissions for every authenticated user (Members/Users)
    member_permissions = [
        "api:access", 
        "playground:access", 
        "model:view", 
        "credit:can_view_org_wallet",
        "credit:can_use_org_credit", 
        "copilot:view", 
        "copilot:use", 
        "org:view", 
        "team:view",
        "workspace:view", 
        "models:view"
    ]

    # 2. Builder/Staff permissions (more advanced usage but no high-level management)
    staff_permissions = member_permissions + [
        "api:keys_manage",
        "playground:configure",
        "copilot:create",
        "copilot:edit",
        "copilot:publish",
        "copilot:documents_manage",
        "models:create"
    ]

    # 3. Admin permissions (organization level management)
    admin_permissions = staff_permissions + [
        "team:manage",
        "team:invite",
        "team:remove",
        "workspace:create",
        "credit:can_share_credit",
        "organization:edit",
        "analytics:usage"
    ]

    # 4. Super Admin permissions (Full control)
    super_admin_permissions = admin_permissions + [
        "organization:manage",
        "workspace:delete",
        "credit:allocate",
        "credit:can_top_up_org_wallet",
        "system:view_audit_logs",
        "user:create"
    ]

    role_permission_mappings = [
        # Platform Admin: Global visibility + Full suite
        {"role": "platform_admin", "permissions": super_admin_permissions + ["organization:view", "organization:create", "user:manage", "user:create", "user:roles_assign", "dashboard:admin", "analytics:platform"]},
        
        # Org Super Admin: Full org control
        {"role": "org_super_admin", "permissions": super_admin_permissions},
        
        # Org Admin: Admin level management
        {"role": "org_admin", "permissions": admin_permissions},

        # Org Member: Standard usage only
        {"role": "org_member", "permissions": member_permissions},

        # Staff: Limited advanced access
        {"role": "staff", "permissions": staff_permissions},
        
        # User: Basic access
        {"role": "user", "permissions": member_permissions},
    ]
    
    logger.info(f"Mapping permissions for {len(role_permission_mappings)} roles...")
    new_mappings_count = 0
    for mapping in role_permission_mappings:
        role_name = mapping["role"]
        role = created_roles.get(role_name)
        if not role:
            # Try to fetch it directly if not in created_roles cache
            role = session.exec(select(Role).where(Role.name == role_name)).first()
            if not role:
                logger.warning(f"Role '{role_name}' not found during permission mapping. Skipping.")
                continue
            created_roles[role_name] = role
            
        for perm_name in mapping["permissions"]:
            perm = created_permissions.get(perm_name)
            if not perm:
                # Try to fetch it directly
                perm = session.exec(select(Permission).where(Permission.name == perm_name)).first()
                if not perm:
                    logger.warning(f"Permission '{perm_name}' not found. Skipping mapping to {role_name}.")
                    continue
                created_permissions[perm_name] = perm

            if (role.id, perm.id) in rp_lookup:
                continue
                
            rp = RolePermission(role_id=role.id, permission_id=perm.id, allowed=True)
            session.add(rp)
            rp_lookup.add((role.id, perm.id))
            new_mappings_count += 1
            
    if new_mappings_count > 0:
        logger.info(f"Added {new_mappings_count} new role-permission mappings.")
    
    session.commit()
    logger.info("RBAC seeding complete.")
