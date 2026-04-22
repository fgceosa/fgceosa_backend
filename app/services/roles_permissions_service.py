"""
Service layer for Roles and Permissions management
"""
from uuid import UUID
import logging
from sqlmodel import Session, select, func
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)

from app.models import Role, Permission, RolePermission, UserRole
from app.schemas.roles_permissions import (
    RoleCreate,
    RoleUpdate,
    RolePublic,
    PermissionPublic,
    PermissionGroupPublic,
    PermissionCreate
)


# System roles that cannot be deleted or have name changed
SYSTEM_ROLES = {
    "super_admin",
    "admin",
    "member"
}

# Permission categories for grouping
PERMISSION_CATEGORIES = {
    "member:": "Members & Access",
    "user:": "Members & Access",
    "role:": "Members & Access",
    "payment:": "Payments & Dues",
    "announcement:": "Announcements",
    "event:": "Events",
    "dashboard:": "Analytics",
    "system:": "System Settings",
}


def get_permission_category(permission_name: str) -> str:
    """Determine category for a permission based on its name"""
    for prefix, category in PERMISSION_CATEGORIES.items():
        if permission_name.startswith(prefix):
            return category
    return "System Settings"


def get_all_roles(session: Session) -> list[RolePublic]:
    """Get all roles with their permissions grouped by category"""
    roles = session.exec(select(Role)).all()
    logger.info(f"Retrieved {len(roles)} roles from database")
    
    result = []
    for role in roles:
        # Get user count for this role
        user_count = session.exec(
            select(func.count(UserRole.id)).where(UserRole.role_id == role.id)
        ).one()
        
        # Get all permissions and check if enabled for this role
        # We use outerjoin to get ALL permissions, even if not assigned to the role
        results = session.exec(
            select(Permission, RolePermission)
            .outerjoin(RolePermission, (RolePermission.permission_id == Permission.id) & (RolePermission.role_id == role.id))
        ).all()
        
        # Group permissions by category
        categories_dict: dict[str, list[PermissionPublic]] = {}
        for perm, role_perm in results:
            allowed = role_perm.allowed if role_perm else False
            
            category = get_permission_category(perm.name)
            if category not in categories_dict:
                categories_dict[category] = []
            
            categories_dict[category].append(
                PermissionPublic(
                    id=perm.id,
                    name=perm.name.split(":")[-1].replace("_", " ").title() if ":" in perm.name else perm.name,
                    description=perm.description or "",
                    enabled=allowed
                )
            )
        
        # Convert to PermissionGroupPublic list
        permission_groups = [
            PermissionGroupPublic(
                id=f"pg-{idx}",
                category=category,
                permissions=perms
            )
            for idx, (category, perms) in enumerate(categories_dict.items())
        ]
        
        result.append(
            RolePublic(
                id=role.id,
                name=role.name.replace("_", " ").title() if "_" in role.name else role.name,
                description=role.description or "",
                icon=getattr(role, "icon", None) or "shield",
                userCount=user_count,
                permissions=permission_groups,
                isSystem=role.name in SYSTEM_ROLES
            )
        )
    
    return result


def get_role_by_id(session: Session, role_id: UUID) -> RolePublic:
    """Get a single role by ID with permissions"""
    role = session.get(Role, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Get user count
    user_count = session.exec(
        select(func.count(UserRole.id)).where(UserRole.role_id == role.id)
    ).one()
    
    # Get all permissions and check if enabled for this role
    results = session.exec(
        select(Permission, RolePermission)
        .outerjoin(RolePermission, (RolePermission.permission_id == Permission.id) & (RolePermission.role_id == role.id))
    ).all()
    
    # Group by category
    categories_dict: dict[str, list[PermissionPublic]] = {}
    for perm, role_perm in results:
        allowed = role_perm.allowed if role_perm else False
        
        category = get_permission_category(perm.name)
        if category not in categories_dict:
            categories_dict[category] = []
        
        categories_dict[category].append(
            PermissionPublic(
                id=perm.id,
                name=(perm.name.split(":")[-1].replace("_", " ").title() if ":" in perm.name else perm.name).replace("Organization", "Workspace"),
                description=perm.description or "",
                enabled=allowed
            )
        )
    
    permission_groups = [
        PermissionGroupPublic(
            id=f"pg-{idx}",
            category=category,
            permissions=perms
        )
        for idx, (category, perms) in enumerate(categories_dict.items())
    ]
    
    return RolePublic(
        id=role.id,
        name=role.name.replace("_", " ").title() if "_" in role.name else role.name,
        description=role.description or "",
        icon=getattr(role, "icon", None) or "shield",
        userCount=user_count,
        permissions=permission_groups,
        isSystem=role.name in SYSTEM_ROLES
    )


def create_role(session: Session, role_data: RoleCreate) -> RolePublic:
    """Create a new custom role"""
    # Check if role name already exists
    existing = session.exec(
        select(Role).where(Role.name == role_data.name.lower().replace(" ", "_"))
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role with this name already exists"
        )
    
    # Create role
    role = Role(
        name=role_data.name.lower().replace(" ", "_"),
        description=role_data.description,
    )
    session.add(role)
    session.commit()
    session.refresh(role)
    
    # Assign permissions
    if role_data.permissions:
        for perm_id in role_data.permissions:
            perm = session.get(Permission, perm_id)
            if perm:
                role_perm = RolePermission(
                    role_id=role.id,
                    permission_id=perm_id,
                    allowed=True
                )
                session.add(role_perm)
        session.commit()
    
    return get_role_by_id(session, role.id)


def update_role(session: Session, role_id: UUID, role_data: RoleUpdate) -> RolePublic:
    """Update an existing role"""
    role = session.get(Role, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Update basic fields
    if role_data.name:
        new_name = role_data.name.lower().replace(" ", "_")
        if role.name in SYSTEM_ROLES and new_name != role.name:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot rename system roles"
            )
        role.name = new_name

    if role_data.description is not None:
        role.description = role_data.description
    
    if role_data.icon is not None:
        # role.icon = role_data.icon  # Requires database migration to add 'icon' column
        pass
    
    session.add(role)
    session.commit()
    
    # Update permissions if provided
    if role_data.permissions is not None:
        # Remove existing permissions
        existing_perms = session.exec(
            select(RolePermission).where(RolePermission.role_id == role.id)
        ).all()
        for rp in existing_perms:
            session.delete(rp)
        
        # Add new permissions
        for perm_id in role_data.permissions:
            perm = session.get(Permission, perm_id)
            if perm:
                role_perm = RolePermission(
                    role_id=role.id,
                    permission_id=perm_id,
                    allowed=True
                )
                session.add(role_perm)
        
        session.commit()
    
    return get_role_by_id(session, role.id)


def delete_role(session: Session, role_id: UUID) -> dict:
    """Delete a custom role (system roles cannot be deleted)"""
    role = session.get(Role, role_id)
    if not role:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not found"
        )
    
    # Prevent deletion of system roles
    if role.name in SYSTEM_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete system roles"
        )
    
    # Check if role is assigned to any users
    user_count = session.exec(
        select(func.count(UserRole.id)).where(UserRole.role_id == role.id)
    ).one()
    
    if user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete role. It is currently assigned to {user_count} user(s)"
        )
    
    session.delete(role)
    session.commit()
    
    return {"success": True, "message": "Role deleted successfully"}


def create_permission(session: Session, permission_data: PermissionCreate) -> PermissionPublic:
    """Create a new permission"""
    # Check if permission already exists
    existing = session.exec(
        select(Permission).where(Permission.name == permission_data.name.lower())
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Permission already exists"
        )
    
    # Create permission
    permission = Permission(
        name=permission_data.name.lower(),
        description=permission_data.description
    )
    session.add(permission)
    session.commit()
    session.refresh(permission)
    
    is_sensitive = any(keyword in permission.name.lower() for keyword in ["manage", "delete", "suspend", "impersonate", "audit", "settings", "gateway"])
    
    return PermissionPublic(
        id=permission.id,
        name=(permission.name.split(":")[-1].replace("_", " ").title() if ":" in permission.name else permission.name).replace("Organization", "Workspace"),
        description=permission.description or "",
        enabled=False,
        isSensitive=is_sensitive
    )


def get_all_permissions(session: Session) -> list[PermissionGroupPublic]:
    """Get all available permissions grouped by category"""
    permissions = session.exec(select(Permission)).all()
    
    categories_dict: dict[str, list[PermissionPublic]] = {}
    
    for perm in permissions:
        category = get_permission_category(perm.name)
        if category not in categories_dict:
            categories_dict[category] = []
        
        is_sensitive = any(keyword in perm.name.lower() for keyword in ["manage", "delete", "suspend", "impersonate", "audit", "treasury", "settings", "gateway"])
        
        categories_dict[category].append(
            PermissionPublic(
                id=perm.id,
                name=(perm.name.split(":")[-1].replace("_", " ").title() if ":" in perm.name else perm.name).replace("Organization", "Workspace"),
                description=perm.description or "",
                enabled=False,
                isSensitive=is_sensitive
            )
        )
    
    # Sort categories alphabetically
    sorted_categories = sorted(categories_dict.items())
    
    return [
        PermissionGroupPublic(
            id=f"pg-{idx}",
            category=category,
            permissions=perms
        )
        for idx, (category, perms) in enumerate(sorted_categories)
    ]


def check_user_permission(session: Session, user_id: UUID, permission_name: str) -> bool:
    """
    Check if a user has a specific permission through any of their assigned roles.
    Super admins always return True.
    """
    # Quick check for super admin
    user_roles_query = select(UserRole).where(UserRole.user_id == user_id)
    user_roles = session.exec(user_roles_query).all()
    
    for ur in user_roles:
        # Check if user has platform_super_admin role
        role = session.get(Role, ur.role_id)
        if role and role.name == "platform_super_admin":
            return True
            
    # Regular permission check
    statement = (
        select(RolePermission)
        .join(UserRole, UserRole.role_id == RolePermission.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(UserRole.user_id == user_id)
        .where(Permission.name == permission_name)
        .where(RolePermission.allowed == True)
    )
    result = session.exec(statement).first()
    if result:
        return True
        
    # Check for organization super admin via UserRole
    # (Assuming org_super_admin should have all org-related permissions)
    # This is a fallback to avoid rigid permission management for super admins
    for ur in user_roles:
        role = session.get(Role, ur.role_id)
        if role and role.name == "org_super_admin":
            # If it's an org permission, grant it
            if permission_name.startswith("organization:") or permission_name.startswith("credit:"):
                return True
                
    return False


def require_permission(session: Session, user_id: UUID, permission_name: str):
    """
    Raise 403 Forbidden if user lacks the required permission.
    """
    if not check_user_permission(session, user_id, permission_name):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing required permission: {permission_name}"
        )
