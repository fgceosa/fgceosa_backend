"""
Script to add platform:view_audit_logs permission to platform_admin role
"""
import sys
import os

# Add the parent directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from app.core.db import engine
from app.models import Role, Permission, RolePermission

def add_permission_to_platform_admin():
    with Session(engine) as session:
        # Get platform_admin role
        platform_admin = session.exec(
            select(Role).where(Role.name == "platform_admin")
        ).first()
        
        if not platform_admin:
            print("platform_admin role not found!")
            return
        
        # Get platform:view_audit_logs permission
        permission = session.exec(
            select(Permission).where(Permission.name == "platform:view_audit_logs")
        ).first()
        
        if not permission:
            print("platform:view_audit_logs permission not found!")
            return
        
        # Check if mapping already exists
        existing = session.exec(
            select(RolePermission).where(
                RolePermission.role_id == platform_admin.id,
                RolePermission.permission_id == permission.id
            )
        ).first()
        
        if existing:
            print("Permission already assigned to platform_admin")
            return
        
        # Create the mapping
        role_permission = RolePermission(
            role_id=platform_admin.id,
            permission_id=permission.id,
            allowed=True
        )
        session.add(role_permission)
        session.commit()
        
        print(f"✅ Successfully added 'platform:view_audit_logs' permission to 'platform_admin' role")

if __name__ == "__main__":
    add_permission_to_platform_admin()
