from sqlmodel import Session, create_engine, select

from app import user_repository
from app.core.config import settings
from app.models import User, UserCreate

# Main database engine (existing PostgreSQL on port 5432)
# Optimized for high-concurrency production environments (Render)
engine = create_engine(
    str(settings.SQLALCHEMY_DATABASE_URI), 
    pool_pre_ping=True,
    pool_recycle=120,
    pool_timeout=60,         # Wait up to 60s for a slot
    pool_size=20,            # Increased for concurrent request handling
    max_overflow=10,         # Allow temporary spikes up to 30 connections
    pool_use_lifo=True,
)

# Copilot Hub database engine (pgvector PostgreSQL)
copilot_engine = create_engine(
    str(settings.COPILOT_DATABASE_URI), 
    pool_pre_ping=True,
    pool_recycle=120,
    pool_timeout=60,
    pool_size=10,            # Separate pool for vector operations
    max_overflow=5,          # Total connections: Main (30) + Copilot (15) = 45/97 limit
    pool_use_lifo=True,
)


def init_copilot_db() -> None:
    """Initialize copilot database: create schema and enable vector extension"""
    from sqlalchemy import text
    from sqlmodel import SQLModel
    # Import all copilot models to register them with SQLModel metadata
    import app.copilot.models 
    
    with copilot_engine.connect() as conn:
        # Create schema if it doesn't exist
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS copilot;"))
        # Enable vector extension
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.commit()
    
    # Create all tables registered in metadata (which will include the copilot schema ones)
    # This won't affect the main database because we are using copilot_engine
    SQLModel.metadata.create_all(copilot_engine)



# make sure all SQLModel models are imported (app.models) before initializing DB
# otherwise, SQLModel might fail to initialize relationships properly
# for more details: https://github.com/fastapi/full-stack-fastapi-template/issues/28


def init_db(session: Session) -> None:
    # Tables should be created with Alembic migrations
    # But if you don't want to use migrations, create
    # the tables un-commenting the next lines
    # from sqlmodel import SQLModel

    # This works because the models are already imported and registered from app.models
    # SQLModel.metadata.create_all(engine)

    from app.core.rbac_seed import seed_rbac
    
    # Initialize roles, permissions and their relationships
    seed_rbac(session)

    user = session.exec(
        select(User).where(User.email == settings.FIRST_SUPERUSER)
    ).first()
    if not user:
        user_in = UserCreate(
            email=settings.FIRST_SUPERUSER,
            password=settings.FIRST_SUPERUSER_PASSWORD,
            is_superuser=True,
            role="platform_super_admin"  # Explicitly assign platform_super_admin role
        )
        user = user_repository.create_user(session=session, user_create=user_in)
    else:
        # Maintenance: Ensure existing superuser has the platform_super_admin role
        from app.models import UserRole, Role
        psa_role = session.exec(select(Role).where(Role.name == "platform_super_admin")).first()
        if psa_role:
            existing_ur = session.exec(
                select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == psa_role.id)
            ).first()
            if not existing_ur:
                user_role = UserRole(user_id=user.id, role_id=psa_role.id)
                session.add(user_role)
                user.is_superuser = True
                session.add(user)
                session.commit()
