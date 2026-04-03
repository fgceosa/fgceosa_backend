#!/usr/bin/env python3
"""
Test script for RBAC functionality
"""
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlmodel import Session, select
from app.core.db import engine
from app.models import User, Role, UserRole
from app.utils.permissions import (
    get_user_roles, 
    get_user_permissions, 
    user_has_permission,
    assign_role_to_user,
    user_has_role
)
from app.seed_rbac_data import seed_rbac_data
import app.crud as crud


def test_rbac_system():
    """Test the RBAC system functionality"""
    
    print("🔧 Setting up test environment...")
    
    # First, seed the RBAC data
    try:
        seed_rbac_data()
        print("✅ RBAC data seeded successfully")
    except Exception as e:
        print(f"⚠️  RBAC seeding error (might already exist): {e}")
    
    with Session(engine) as session:
        # Test 1: Create a test user and assign role
        print("\n📝 Test 1: Creating test user...")
        
        # Check if test user exists
        test_email = "testuser@example.com"
        existing_user = user_repository.get_user_by_email(session=session, email=test_email)
        
        if existing_user:
            test_user = existing_user
            print(f"✅ Using existing test user: {test_user.email}")
        else:
            # Create test user
            from app.models import UserCreate
            user_data = UserCreate(
                email=test_email,
                password="testpassword123",
                full_name="Test User"
            )
            test_user = user_repository.create_user(session=session, user_create=user_data)
            print(f"✅ Created test user: {test_user.email}")
        
        # Test 2: Check default role assignment
        print("\n🔍 Test 2: Checking default role assignment...")
        user_roles = get_user_roles(session, test_user)
        print(f"User roles: {user_roles}")
        assert 'user' in user_roles, "Default user role not assigned"
        print("✅ Default role assignment working")
        
        # Test 3: Test role-based permissions
        print("\n🔒 Test 3: Testing role-based permissions...")
        user_permissions = get_user_permissions(session, test_user)
        print(f"User permissions: {user_permissions}")
        
        # Regular user should have api:access permission
        has_api_access = user_has_permission(session, test_user, "api:access")
        print(f"Has api:access permission: {has_api_access}")
        assert has_api_access, "User should have api:access permission"
        
        # Regular user should NOT have user:manage permission
        has_user_manage = user_has_permission(session, test_user, "user:manage")
        print(f"Has user:manage permission: {has_user_manage}")
        assert not has_user_manage, "User should NOT have user:manage permission"
        
        print("✅ Permission checking working correctly")
        
        # Test 4: Test role upgrade
        print("\n⬆️  Test 4: Testing role upgrade...")
        
        # Assign platform_admin role
        success = assign_role_to_user(session, test_user, "platform_admin")
        assert success, "Failed to assign platform_admin role"
        
        # Check new roles
        updated_roles = get_user_roles(session, test_user)
        print(f"Updated user roles: {updated_roles}")
        assert 'platform_admin' in updated_roles, "Platform admin role not assigned"
        
        # Check new permissions
        updated_permissions = get_user_permissions(session, test_user)
        print(f"Updated permissions: {updated_permissions}")
        
        # Platform admin should now have dashboard:admin permission
        has_dashboard_admin = user_has_permission(session, test_user, "dashboard:admin")
        print(f"Has dashboard:admin permission: {has_dashboard_admin}")
        assert has_dashboard_admin, "Platform admin should have dashboard:admin permission"
        
        print("✅ Role upgrade working correctly")
        
        # Test 5: Test authority array for login response
        print("\n🔐 Test 5: Testing authority array for login response...")
        authority_array = get_user_roles(session, test_user)
        print(f"Authority array for login: {authority_array}")
        
        expected_roles = ['user', 'platform_admin']
        for role in expected_roles:
            assert role in authority_array, f"Role {role} missing from authority array"
        
        print("✅ Authority array working correctly")
        
        print("\n🎉 All RBAC tests passed!")
        print("\n📋 Test Summary:")
        print(f"   - User: {test_user.email}")
        print(f"   - Roles: {authority_array}")
        print(f"   - Permissions: {updated_permissions}")
        
        return True


def demonstrate_frontend_integration():
    """Demonstrate how the frontend will receive the authority array"""
    
    print("\n🌐 Frontend Integration Demo:")
    print("When a user logs in, they will receive:")
    print("""
    {
        "access_token": "jwt_token_here",
        "token_type": "bearer",
        "user": {
            "userId": "user_uuid_here",
            "userName": "Test User",
            "authority": ["user", "platform_admin"],
            "avatar": "",
            "email": "testuser@example.com"
        }
    }
    """)
    
    print("The frontend will then use the 'authority' array to:")
    print("1. Show/hide routes based on user roles")
    print("2. Control access to components")
    print("3. Redirect users to appropriate dashboards")
    
    print("\n🛡️ Route Access Matrix:")
    routes = {
        "/user": ["user", "staff", "org_admin", "org_super_admin", "platform_admin", "platform_super_admin"],
        "/api-keys": ["user", "staff", "org_admin", "org_super_admin", "platform_admin", "platform_super_admin"],
        "/ai-playground": ["user", "staff", "org_admin", "org_super_admin", "platform_admin", "platform_super_admin"],
        "/api-providers": ["user", "staff", "org_admin", "org_super_admin", "platform_admin", "platform_super_admin"],
        "/team": ["org_admin", "org_super_admin", "platform_super_admin"],
        "/admin-dashboard": ["platform_admin", "platform_super_admin"],
        "/revenue": ["platform_admin", "platform_super_admin"],
        "/enterprise": ["platform_admin", "platform_super_admin"]
    }
    
    for route, allowed_roles in routes.items():
        print(f"   {route}: {allowed_roles}")


if __name__ == "__main__":
    try:
        success = test_rbac_system()
        if success:
            demonstrate_frontend_integration()
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)