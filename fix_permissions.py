from sqlmodel import Session, select
from app.core.db import engine
from app.models import Role, Permission, RolePermission

def fix_permissions():
    print("Starting permission fix...")
    with Session(engine) as session:
        # Get Permissions
        api_perm = session.exec(select(Permission).where(Permission.name == "api:access")).first()
        playground_perm = session.exec(select(Permission).where(Permission.name == "playground:access")).first()

        if not api_perm:
            print("Permission api:access not found! Creating it...")
            api_perm = Permission(name="api:access", description="Access API endpoints")
            session.add(api_perm)
            session.commit()
            session.refresh(api_perm)

        if not playground_perm:
             print("Permission playground:access not found! Creating it...")
             playground_perm = Permission(name="playground:access", description="Access AI playground")
             session.add(playground_perm)
             session.commit()
             session.refresh(playground_perm)

        perms_to_add = [api_perm, playground_perm]

        # Get Roles
        roles_to_fix = ["org_admin", "org_super_admin"]
        
        for role_name in roles_to_fix:
            role = session.exec(select(Role).where(Role.name == role_name)).first()
            if not role:
                print(f"Role {role_name} not found")
                continue

            for perm in perms_to_add:
                # Check if exists
                exists = session.exec(
                    select(RolePermission).where(
                        RolePermission.role_id == role.id,
                        RolePermission.permission_id == perm.id
                    )
                ).first()
                
                if not exists:
                    print(f"Adding {perm.name} to {role_name}...")
                    rp = RolePermission(role_id=role.id, permission_id=perm.id, allowed=True)
                    session.add(rp)
                else:
                    print(f"{role_name} already has {perm.name}")
        
        session.commit()
        print("Done!")

if __name__ == "__main__":
    fix_permissions()
