import asyncio
from collections.abc import Generator
import uuid
from decimal import Decimal
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from sqlmodel import Session, SQLModel, create_engine, select
from sqlalchemy.pool import StaticPool
from testcontainers.postgres import PostgresContainer
from typing import AsyncGenerator, Dict, Any

from app.main import app as fastapi_app
from unittest.mock import MagicMock
import app.email_utils
from app.api.deps import get_db
from app.core.config import settings
from app.core.rbac_seed import seed_rbac
from app import user_repository
from app.models import User, UserCreate, Role, Organization, OrganizationMember
from app.core.security import create_access_token

# ==================== Database Setup ====================

@pytest.fixture(scope="session")
def postgres_container():
    """Starts a PostgreSQL container for the entire test session."""
    with PostgresContainer("pgvector/pgvector:pg15") as postgres:
        yield postgres

@pytest.fixture(scope="session")
def db_engine(postgres_container):
    """Creates a database engine connected to the test container."""
    database_url = postgres_container.get_connection_url()
    # Using StaticPool to ensure the connection stays alive during tests if needed
    # but since we use Testcontainers, the DB is persistent for the session.
    engine = create_engine(
        database_url,
        poolclass=StaticPool,
    )
    
    # Enable extensions and create required schemas
    from sqlalchemy import text
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS copilot;"))
        conn.commit()
        
    SQLModel.metadata.create_all(engine)
    
    # Seed RBAC data
    with Session(engine) as session:
        seed_rbac(session)
        
    return engine

@pytest_asyncio.fixture
async def db_session(db_engine) -> AsyncGenerator[Session, None]:
    """
    Creates a new database session for each test.
    Starts a transaction and rolls it back after the test completes.
    This ensures test isolation.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()

# ==================== Client & Dependency Overrides ====================

@pytest_asyncio.fixture
async def client(db_session: Session) -> AsyncGenerator[AsyncClient, None]:
    """
    Async client for API testing with database session override.
    """
    def override_get_db():
        try:
            yield db_session
        finally:
            pass # Session is closed by the fixture

    from app.api.deps import get_db, get_copilot_db
    fastapi_app.dependency_overrides[get_db] = override_get_db
    fastapi_app.dependency_overrides[get_copilot_db] = override_get_db
    
    # Using ASGITransport for internal FastAPI testing without a real server
    async with AsyncClient(
        transport=ASGITransport(app=fastapi_app), 
        base_url="http://test"
    ) as ac:
        yield ac
    
    fastapi_app.dependency_overrides.clear()


# ==================== Authentication Fixtures ====================

async def create_test_user_with_role(session: Session, email: str, role_name: str) -> User:
    """Helper to create a user with a specific role."""
    user_in = UserCreate(
        email=email,
        password="testpassword123",
        role=role_name,
        is_active=True,
    )
    user = user_repository.create_user(session=session, user_create=user_in)
    # Ensure user is verified for testing
    user.is_verified = True
    user.status = "active"
    session.add(user)
    session.commit()
    session.refresh(user)
    return user

@pytest.fixture(autouse=True)
def mock_emails(monkeypatch):
    """Robustly mock email functionality to prevent external calls."""
    from unittest.mock import MagicMock
    from app.services.email_service import EmailService
    
    # Mock the send_email method on the class to cover all instances
    monkeypatch.setattr(EmailService, "send_email", MagicMock(return_value={"status": "mocked"}))
    monkeypatch.setattr(EmailService, "send_welcome_email", MagicMock(return_value={"status": "mocked"}))
    monkeypatch.setattr(EmailService, "send_password_reset_email", MagicMock(return_value={"status": "mocked"}))
    monkeypatch.setattr(EmailService, "send_email_verification", MagicMock(return_value={"status": "mocked"}))
    monkeypatch.setattr(EmailService, "send_team_invitation", MagicMock(return_value={"status": "mocked"}))
    
    # Also mock higher level utils just in case they were imported before patching
    import app.email_utils
    monkeypatch.setattr(app.email_utils, "send_email_verification", MagicMock(return_value={"status": "mocked"}))
    monkeypatch.setattr(app.email_utils, "send_new_account_email", MagicMock(return_value={"status": "mocked"}))
    monkeypatch.setattr(app.email_utils, "send_reset_password_email", MagicMock(return_value={"status": "mocked"}))
    monkeypatch.setattr(app.email_utils, "send_team_invitation_email", MagicMock(return_value={"status": "mocked"}))

@pytest_asyncio.fixture
async def platform_super_admin(db_session: Session) -> User:
    user = await create_test_user_with_role(db_session, "psa@example.com", "platform_super_admin")
    # Mint a bunch of credits so we can test transfers etc.
    from app.credit_repository import add_credits
    add_credits(
        session=db_session,
        user_id=user.id,
        amount=Decimal("100000.0"),
        transaction_type="purchase", # Use purchase so it's simple
        description="Seeding test credits",
    )
    db_session.commit()
    db_session.refresh(user)
    return user

@pytest_asyncio.fixture
async def org_super_admin(db_session: Session) -> User:
    user = await create_test_user_with_role(db_session, "osa@example.com", "org_super_admin")
    # Also create an organization they own
    org = Organization(name="Test Org", owner_id=user.id)
    db_session.add(org)
    db_session.flush()
    member = OrganizationMember(organization_id=org.id, user_id=user.id, role="org_super_admin", status="active")
    db_session.add(member)
    db_session.commit()
    return user

@pytest_asyncio.fixture
async def org_admin(db_session: Session) -> User:
    return await create_test_user_with_role(db_session, "admin@example.com", "org_admin")

@pytest_asyncio.fixture
async def org_member(db_session: Session) -> User:
    return await create_test_user_with_role(db_session, "member@example.com", "org_member")

@pytest_asyncio.fixture
async def normal_user(db_session: Session) -> User:
    return await create_test_user_with_role(db_session, "user@example.com", "user")

# ==================== Authenticated Clients ====================

def get_auth_headers(user: User) -> Dict[str, str]:
    from datetime import timedelta
    # Token valid for 1 hour for tests
    token = create_access_token(user.id, expires_delta=timedelta(hours=1))
    return {"Authorization": f"Bearer {token}"}

@pytest_asyncio.fixture
async def psa_client(client: AsyncClient, platform_super_admin: User) -> AsyncClient:
    client.headers.update(get_auth_headers(platform_super_admin))
    return client


@pytest_asyncio.fixture
async def osa_client(client: AsyncClient, org_super_admin: User) -> AsyncClient:
    client.headers.update(get_auth_headers(org_super_admin))
    return client

@pytest_asyncio.fixture
async def admin_client(client: AsyncClient, org_admin: User) -> AsyncClient:
    client.headers.update(get_auth_headers(org_admin))
    return client

@pytest_asyncio.fixture
async def member_client(client: AsyncClient, org_member: User) -> AsyncClient:
    client.headers.update(get_auth_headers(org_member))
    return client

# ==================== Wallet & Flow Simulation Helpers ====================

@pytest.fixture
def wallet_simulator(db_session: Session):
    """Fixture to simulate wallet credit flows."""
    
    class WalletSim:
        @staticmethod
        def add_credits(user: User, amount: float):
            # Use WalletService to add credits correctly via the ledger
            from app.services.wallet_service import WalletService
            from app.models import WalletOwnerType, WalletTransactionType
            
            wallet = WalletService.get_or_create_wallet(db_session, user.id, WalletOwnerType.USER)
            WalletService.add_transaction(
                session=db_session,
                wallet_id=wallet.id,
                transaction_type=WalletTransactionType.TOP_UP,
                amount=Decimal(str(amount)),
                credit=Decimal(str(amount)),
                description="Test credit allocation",
                commit=True
            )
            return user
            
        @staticmethod
        def add_org_credits(org: Organization, amount: float):
            from app.services.wallet_service import WalletService
            from app.models import WalletOwnerType, WalletTransactionType
            
            wallet = WalletService.get_or_create_wallet(db_session, org.id, WalletOwnerType.ORGANIZATION)
            WalletService.add_transaction(
                session=db_session,
                wallet_id=wallet.id,
                transaction_type=WalletTransactionType.TOP_UP,
                amount=Decimal(str(amount)),
                credit=Decimal(str(amount)),
                description="Test org credit allocation",
                commit=True
            )
            return org
            
    return WalletSim()

@pytest.fixture
def webhook_simulator(client: AsyncClient):
    """Fixture to simulate webhook callbacks."""
    class WebhookSim:
        async def send_payment_callback(self, reference: str, status: str = "success"):
            return await client.post(
                f"{settings.API_V1_STR}/payments/webhook/monnify",
                json={
                    "event_type": "SUCCESSFUL_TRANSACTION",
                    "event_data": {
                        "payment_reference": reference,
                        "status": status
                    }
                }
            )
    return WebhookSim()

# Ensures that we don't accidentally run tests against production
def pytest_configure(config):
    import os
    os.environ["ENVIRONMENT"] = "test"
    os.environ["TESTING"] = "true"
