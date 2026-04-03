import sys
from sqlmodel import Session, select
from fastapi.testclient import TestClient
from app.main import app
from app.core.db import engine
from app.core import security
from app.models import User, Role, UserRole, TokenPayload
from app.core.config import settings
import jwt
from datetime import datetime, timedelta, timezone

def test_api():
    print("Starting API Test...")
    with Session(engine) as session:
        # 1. Find a user with org_admin role
        statement = (
            select(User)
            .join(UserRole, User.id == UserRole.user_id)
            .join(Role, UserRole.role_id == Role.id)
            .where(Role.name == "org_admin")
        )
        user = session.exec(statement).first()
        
        if not user:
            print("No user with org_admin role found. Trying to find any user and assign role...")
            user = session.exec(select(User).limit(1)).first()
            if not user:
                print("No users found in DB!")
                return
            
            # Find role
            role = session.exec(select(Role).where(Role.name == "org_admin")).first()
            if role:
                 user_role = UserRole(user_id=user.id, role_id=role.id)
                 session.add(user_role)
                 session.commit()
                 print(f"Assigned org_admin to user {user.email}")
            else:
                 print("Role org_admin not found!")
                 return

        print(f"Using user: {user.email} ({user.id})")

        # 2. Generate Token
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        expire = datetime.now(timezone.utc) + access_token_expires
        to_encode = {"exp": expire, "sub": str(user.id)}
        encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=security.ALGORITHM)
        
        headers = {"Authorization": f"Bearer {encoded_jwt}"}
        
        # 3. Request
        client = TestClient(app)
        url = f"{settings.API_V1_STR}/audit-logs/"
        print(f"Requesting {url}")
        
        response = client.get(url, headers=headers)
        
        print(f"Status Code: {response.status_code}")
        if response.status_code != 200:
             print("Error Response:")
             print(response.json())
        else:
             data = response.json()
             print(f"Total Logs: {data.get('total')}")
             logs = data.get('logs', [])
             print(f"Returned {len(logs)} logs")
             if len(logs) > 0:
                 print("Sample Log:")
                 print(logs[0])

if __name__ == "__main__":
    test_api()
