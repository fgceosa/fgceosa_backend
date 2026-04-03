import pytest
from httpx import AsyncClient
from app.core.config import settings
from app.models import User
from sqlmodel import Session, select
from app.utils import verify_email_verification_token, verify_password_reset_token

@pytest.mark.asyncio
async def test_user_registration_success(client: AsyncClient, db_session: Session):
    """Test successful user registration."""
    user_data = {
        "email": "newuser@example.com",
        "password": "strongpassword123",
        "full_name": "New User",
        "account_type": "individual",
        "accept_terms": True
    }
    response = await client.post(f"{settings.API_V1_STR}/users/signup", json=user_data)
    assert response.status_code == 200
    data = response.json()
    print(f"\nDEBUG SIGNUP RESPONSE: {data}")
    assert data["email"] == user_data["email"]
    # UserPublic has 'name' field mapped from full_name
    assert data["name"] == user_data["full_name"]
    assert "id" in data
    
    # Verify user exists in DB and is NOT verified yet
    user = db_session.exec(select(User).where(User.email == user_data["email"])).first()
    assert user is not None
    assert user.is_verified is False
    assert user.status == "active"

@pytest.mark.asyncio
async def test_user_registration_duplicate_email(client: AsyncClient, db_session: Session):
    """Test registration with an already existing email."""
    user_data = {
        "email": "duplicate@example.com",
        "password": "password123",
        "full_name": "Duplicate User",
        "account_type": "individual",
        "accept_terms": True
    }
    # First registration
    await client.post(f"{settings.API_V1_STR}/users/signup", json=user_data)
    
    # Second registration with same email
    response = await client.post(f"{settings.API_V1_STR}/users/signup", json=user_data)
    assert response.status_code == 400
    assert "already exists" in response.json()["detail"]

@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, db_session: Session, platform_super_admin: User):
    """Test successful login with platform_super_admin."""
    # platform_super_admin uses "testpassword123" in conftest.py
    login_data = {
        "username": platform_super_admin.email,
        "password": "testpassword123"
    }
    response = await client.post(
        f"{settings.API_V1_STR}/login/access-token", 
        data=login_data
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["user"]["email"] == platform_super_admin.email

@pytest.mark.asyncio
async def test_login_invalid_credentials(client: AsyncClient):
    """Test login with wrong password."""
    login_data = {
        "username": "admin@qorebit.com",
        "password": "wrongpassword"
    }
    response = await client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    assert response.status_code == 401
    assert "incorrect" in response.json()["detail"]

@pytest.mark.asyncio
async def test_email_verification_flow(client: AsyncClient, db_session: Session):
    """Test the full email verification flow."""
    email = "verify@example.com"
    user_data = {
        "email": email,
        "password": "password123",
        "full_name": "Verify Me",
        "account_type": "individual",
        "accept_terms": True
    }
    await client.post(f"{settings.API_V1_STR}/users/signup", json=user_data)
    
    # Manually generate token as if it were emailed
    from app.email_utils import generate_email_verification_token
    token = generate_email_verification_token(email)
    
    response = await client.post(f"{settings.API_V1_STR}/login/verify-email?token={token}")
    assert response.status_code == 200
    assert "verified successfully" in response.json()["message"]
    
    # Check DB
    db_session.expire_all()
    user = db_session.exec(select(User).where(User.email == email)).first()
    assert user.is_verified is True

@pytest.mark.asyncio
async def test_password_recovery_and_reset(client: AsyncClient, db_session: Session, platform_super_admin: User):
    """Test password recovery request and reset."""
    email = platform_super_admin.email
    response = await client.post(f"{settings.API_V1_STR}/password-recovery/{email}")
    assert response.status_code == 200
    
    from app.email_utils import generate_password_reset_token
    token = generate_password_reset_token(email)
    
    reset_data = {
        "token": token,
        "new_password": "newsecurepassword123"
    }
    response = await client.post(f"{settings.API_V1_STR}/reset-password", json=reset_data)
    assert response.status_code == 200
    
    # Verify login with new password
    login_data = {
        "username": email,
        "password": reset_data["new_password"]
    }
    response = await client.post(f"{settings.API_V1_STR}/login/access-token", data=login_data)
    assert response.status_code == 200
