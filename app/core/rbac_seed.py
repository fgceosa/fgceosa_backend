"""
RBAC seed logic for initializing roles and permissions.
"""
import logging
from sqlmodel import Session, select
from app.models import Role, Permission, RolePermission

logger = logging.getLogger(__name__)

# System roles that cannot be deleted or have name changed
SYSTEM_ROLES_DATA = [
    {"name": "super_admin", "description": "Complete oversight and ultimate authority across the platform"},
    {"name": "admin", "description": "Platform management, member operations, payment tracking"},
    {"name": "member", "description": "Regular alumni member"},
]

# Standard technical permissions
SYSTEM_PERMISSIONS_DATA = [
    # Members
    {"name": "member:manage", "description": "Manage all members"},
    {"name": "member:edit_profile", "description": "Edit own profile"},
    
    # User Management & Roles
    {"name": "user:roles_assign", "description": "Manage and assign roles to users"},
    
    # Payments
    {"name": "payment:manage", "description": "Manage all payments and dues"},
    {"name": "payment:pay", "description": "Make payments for dues/events"},
    
    # Announcements
    {"name": "announcement:manage", "description": "Create and manage announcements"},
    {"name": "announcement:view", "description": "View announcements"},
    
    # Events
    {"name": "event:manage", "description": "Create and manage events"},
    {"name": "event:view", "description": "View events"},
    
    # Dashboard
    {"name": "dashboard:admin", "description": "Access admin CRM dashboard"},
    {"name": "dashboard:member", "description": "Access member dashboard"},
    
    # System
    {"name": "system:settings", "description": "Manage system settings"},
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
    psa_role = created_roles.get("super_admin")
    if psa_role:
        all_perms = list(created_permissions.values())
        for perm in all_perms:
            if (psa_role.id, perm.id) not in rp_lookup:
                rp = RolePermission(role_id=psa_role.id, permission_id=perm.id, allowed=True)
                session.add(rp)
                rp_lookup.add((psa_role.id, perm.id))
    
    # Define specific mappings for other roles
    member_permissions = [
        "member:edit_profile",
        "payment:pay",
        "announcement:view",
        "event:view",
        "dashboard:member",
    ]

    admin_permissions = member_permissions + [
        "member:manage",
        "payment:manage",
        "announcement:manage",
        "event:manage",
        "dashboard:admin",
        "user:roles_assign",
        "system:settings",
    ]

    role_permission_mappings = [
        {"role": "admin", "permissions": admin_permissions},
        {"role": "member", "permissions": member_permissions},
    ]
    
    logger.info(f"Mapping permissions for {len(role_permission_mappings)} roles...")
    new_mappings_count = 0
    for mapping in role_permission_mappings:
        role_name = mapping["role"]
        role = created_roles.get(role_name)
        if not role:
            role = session.exec(select(Role).where(Role.name == role_name)).first()
            if not role:
                logger.warning(f"Role '{role_name}' not found during permission mapping. Skipping.")
                continue
            created_roles[role_name] = role
            
        for perm_name in mapping["permissions"]:
            perm = created_permissions.get(perm_name)
            if not perm:
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
