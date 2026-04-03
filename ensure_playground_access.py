from sqlmodel import Session, select
from app.core.db import engine
from app.models import Role, Permission, RolePermission
import uuid

def ensure_playground_access():
    print("Starting playground access fix...")
    with Session(engine) as session:
        # 1. Ensure playground:access permission exists
        perm_name = "playground:access"
        playground_perm = session.exec(select(Permission).where(Permission.name == perm_name)).first()
        
        if not playground_perm:
            print(f"Permission {perm_name} not found! Creating it...")
            playground_perm = Permission(
                id=uuid.uuid4(),
                name=perm_name, 
                description="Access AI Playground environment"
            )
            session.add(playground_perm)
            session.commit()
            session.refresh(playground_perm)
        else:
            print(f"Permission {perm_name} already exists.")

        # 2. Assign to relevant roles
        roles_to_grant = [
            "org_super_admin",
            "org_admin",
            "platform_super_admin",
            "platform_admin"
        ]
        
        for role_name in roles_to_grant:
            # Note: System roles have organization_id = None
            role = session.exec(select(Role).where(Role.name == role_name, Role.organization_id == None)).first()
            
            if not role:
                # If not found as system role, check if there are any organization-specific ones (though these names are usually system roles)
                role = session.exec(select(Role).where(Role.name == role_name)).first()
            
            if not role:
                print(f"Role {role_name} not found in database.")
                continue

            # Check if association already exists
            exists = session.exec(
                select(RolePermission).where(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == playground_perm.id
                )
            ).first()
            
            if not exists:
                print(f"Granting {perm_name} to {role_name}...")
                rp = RolePermission(
                    role_id=role.id,
                    permission_id=playground_perm.id,
                    allowed=True
                )
                session.add(rp)
            else:
                if not exists.allowed:
                    print(f"Enabling {perm_name} for {role_name}...")
                    exists.allowed = True
                    session.add(exists)
                else:
                    print(f"Role {role_name} already has {perm_name} enabled.")
        
        session.commit()
        print("Successfully updated permissions.")

if __name__ == "__main__":
    ensure_playground_access()
