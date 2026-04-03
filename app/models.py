import uuid
from typing import Optional
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from pydantic import EmailStr, ConfigDict, model_validator
from sqlmodel import Field, Relationship, SQLModel, Column
from sqlalchemy import JSON
import sqlalchemy as sa


# Shared properties
class UserBase(SQLModel):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    is_active: bool = True
    is_superuser: bool = False
    full_name: str | None = Field(default=None, max_length=255)
    tag_number: str | None = Field(default=None, max_length=50, unique=True, index=True, description="Unique user tag for identification (e.g., @qor123456)")
    # profile fields for user settings
    first_name: str | None = Field(default=None, max_length=150, alias="firstName")
    last_name: str | None = Field(default=None, max_length=150, alias="lastName")
    phone: str | None = Field(default=None, max_length=50)
    state: str | None = Field(default=None, max_length=255)
    avatar: str | None = Field(default=None, max_length=500)
    # additional profile fields
    username: str | None = Field(default=None, max_length=150, index=True)
    phone_number: str | None = Field(default=None, max_length=50)
    dial_code: str | None = Field(default=None, max_length=10)
    auth_provider: str = Field(default="password", max_length=20, description="Auth provider: password, google, sso")
    address: str | None = Field(default=None, max_length=500)
    postcode: str | None = Field(default=None, max_length=50)
    city: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=255)
    timezone: str | None = Field(default=None, max_length=100)

    model_config = ConfigDict(populate_by_name=True)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: str | None = None
    roles: list[str] | None = None


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=150)
    account_type: str = Field(default="individual", description="Account type: individual or organization")
    organization_name: str | None = Field(default=None, max_length=255, description="Organization name (required for organization account type)")
    accept_terms: bool = Field(description="User must accept terms and conditions")
    invitation_token: str | None = Field(default=None, description="Optional invitation token to auto-verify and join workspace")


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None
    status: str | None = None
    role: str | None = None
    roles: list[str] | None = None


class UserIdentityRoleUpdate(SQLModel):
    identityRole: str = Field(..., description="The new identity role name (e.g. platform_super_admin)")

    model_config = ConfigDict(populate_by_name=True)


class UserUpdateMe(SQLModel):
    # Accept camelCase from frontend
    firstName: str | None = Field(default=None, max_length=150)
    lastName: str | None = Field(default=None, max_length=150)
    phone: str | None = Field(default=None, max_length=50)
    address: str | None = Field(default=None, max_length=500)
    state: str | None = Field(default=None, max_length=255)
    email: EmailStr | None = Field(default=None, max_length=255)
    username: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=255)
    postcode: str | None = Field(default=None, max_length=50)

    def to_db_dict(self) -> dict:
        """Convert camelCase fields to snake_case for database"""
        data = {}
        if self.firstName is not None:
            data['first_name'] = self.firstName
        if self.lastName is not None:
            data['last_name'] = self.lastName
        if self.phone is not None:
            data['phone'] = self.phone
        if self.address is not None:
            data['address'] = self.address
        if self.state is not None:
            data['state'] = self.state
        if self.email is not None:
            data['email'] = self.email
        if self.username is not None:
            data['username'] = self.username
        if self.city is not None:
            data['city'] = self.city
        if self.country is not None:
            data['country'] = self.country
        if self.postcode is not None:
            data['postcode'] = self.postcode
        return data


class UserSocialLogin(SQLModel):
    email: EmailStr
    full_name: str | None = Field(default=None, max_length=255)
    avatar: str | None = Field(default=None, max_length=500)
    provider: str = Field(..., max_length=20)


class UpdatePassword(SQLModel):
    current_password: str = Field(min_length=8, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


# Database model, database table inferred from class name
class User(UserBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    hashed_password: str
    credits: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4, description="Cached credits for the user. Source of truth is the wallet ledger.")
    status: str = Field(default="active", max_length=20, description="User status: active, pending, disabled")
    last_login: datetime | None = Field(default=None, description="Timestamp of the last login")
    account_type: str = Field(default="individual", max_length=50, description="Account type: individual or organization")
    organization_name: str | None = Field(default=None, max_length=255, description="Organization name for company accounts")
    accepted_terms_at: datetime | None = Field(default=None, description="Timestamp when user accepted terms and conditions")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_verified: bool = Field(default=False, description="Whether the user email has been verified")
    user_roles: list["UserRole"] = Relationship(back_populates="user", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(SQLModel):
    id: uuid.UUID
    email: EmailStr
    tagNumber: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    name: str | None = None
    phone: str | None = None
    address: str | None = None
    state: str | None = None
    avatar: str | None = None
    accountType: str | None = None
    organizationName: str | None = None
    organization: dict | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    role: str | None = None
    status: str | None = None
    timezone: str | None = None
    isVerified: bool = Field(default=False, alias="is_verified")
    authProvider: str | None = "password"
    lastOnline: datetime | None = None
    username: str | None = None
    city: str | None = None
    country: str | None = None
    postcode: str | None = None
    credits: float | None = 0.0
    orgCredits: float | None = 0.0
    totalSpending: float | None = 0
    roles: list[str] = []
    permissions: list[str] = []
    botsCount: int | None = 0
    projectsCount: int | None = 0

    @classmethod
    def from_user(cls, user: "User") -> "UserPublic":
        """Convert User model to UserPublic with camelCase fields"""
        # Determine status
        status = getattr(user, "status", None)
        if not status:
            status = "active" if user.is_active else "pending"
        
        # Get all role names and permissions
        user_role_names = []
        user_permissions = []
        if hasattr(user, "user_roles") and user.user_roles:
            for ur in user.user_roles:
                if hasattr(ur, "role") and ur.role:
                    user_role_names.append(ur.role.name)
                    if hasattr(ur.role, "role_permissions") and ur.role.role_permissions:
                        for rp in ur.role.role_permissions:
                            if rp.allowed and hasattr(rp, "permission") and rp.permission:
                                user_permissions.append(rp.permission.name)

        user_permissions = list(set(user_permissions))

        # Determine "Primary" role from RBAC system for single-role compatibility
        role = "Member"
        if user_role_names:
            # Prioritize super admin
            if "platform_super_admin" in user_role_names:
                role = "platform_super_admin"
            elif "platform_admin" in user_role_names:
                role = "platform_admin"
            else:
                role = user_role_names[0]
        elif getattr(user, "is_superuser", False):
            role = "Admin"
        
        # Use last_login if available, fallback to updated_at
        last_online = getattr(user, "last_login", None) or user.updated_at
        
        return cls(
            id=user.id,
            email=user.email,
            tagNumber=user.tag_number,
            firstName=user.first_name,
            lastName=user.last_name,
            name=user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip() or "User",
            phone=user.phone,
            address=user.address,
            state=user.state,
            avatar=user.avatar,
            accountType=user.account_type,
            organizationName=user.organization_name,
            createdAt=user.created_at,
            updatedAt=user.updated_at,
            role=role,
            status=status,
            timezone=user.timezone,
            authProvider=getattr(user, "auth_provider", "password"),
            lastOnline=last_online,
            credits=float(user.credits) if hasattr(user, "credits") else 0.0,
            orgCredits=0, # Calculated in the route
            username=getattr(user, "username", None),
            city=getattr(user, "city", None),
            country=getattr(user, "country", None),
            postcode=getattr(user, "postcode", None),
            totalSpending=0, # Calculated in the route
            botsCount=0, # Calculated in the route
            projectsCount=0, # Calculated in the route
            roles=user_role_names,
            permissions=user_permissions,
            isVerified=user.is_verified
        )


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# RBAC Models
class Role(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=50, index=True)
    description: str | None = Field(default=None, max_length=255)
    organization_id: uuid.UUID | None = Field(default=None, foreign_key="organization.id", nullable=True, ondelete="CASCADE", index=True)
    
    user_roles: list["UserRole"] = Relationship(back_populates="role", cascade_delete=True)
    role_permissions: list["RolePermission"] = Relationship(back_populates="role", cascade_delete=True)
    organization: Optional["Organization"] = Relationship(back_populates="roles")


class Permission(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=100, unique=True, index=True)
    description: str | None = Field(default=None, max_length=255)
    role_permissions: list["RolePermission"] = Relationship(back_populates="permission", cascade_delete=True)


class UserRole(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    role_id: uuid.UUID = Field(foreign_key="role.id", nullable=False, ondelete="CASCADE")
    user: User | None = Relationship(back_populates="user_roles")
    role: Role | None = Relationship(back_populates="user_roles")


class RolePermission(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    role_id: uuid.UUID = Field(foreign_key="role.id", nullable=False, ondelete="CASCADE")
    permission_id: uuid.UUID = Field(foreign_key="permission.id", nullable=False, ondelete="CASCADE")
    allowed: bool = Field(default=True)
    role: Role | None = Relationship(back_populates="role_permissions")
    permission: Permission | None = Relationship(back_populates="role_permissions")




# Generic message
class Message(SQLModel):
    message: str


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    token_type: str = "bearer"
    user: dict | None = None


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None
    authority: list[str] | None = None
    iat: float | None = None


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=128)


# Transaction Status Enum
class TransactionStatus(str, Enum):
    """Transaction status enum"""
    COMPLETED = "completed"
    PENDING = "pending"
    FAILED = "failed"
    EXPIRED = "expired"


# Wallet Owner Type Enum
class WalletOwnerType(str, Enum):
    """Wallet owner type enum"""
    ORGANIZATION = "organization"
    USER = "user"


# Wallet Transaction Type Enum
class WalletTransactionType(str, Enum):
    """Wallet transaction type enum"""
    TOP_UP = "top_up"
    CREDIT_SHARE = "credit_share"
    USAGE = "usage"
    REFUND = "refund"
    ADJUSTMENT = "adjustment"


# Project Status Enum
class ProjectStatus(str, Enum):
    """Project status enum"""
    ACTIVE = "active"
    IN_DEVELOPMENT = "in_development"
    ARCHIVED = "archived"


# Project Type Enum
class ProjectType(str, Enum):
    """Project type enum"""
    WEB = "web"
    MOBILE = "mobile"
    BACKEND = "backend"
    DESKTOP = "desktop"
    IOT = "iot"
    OTHER = "other"


# Organization Model
class Organization(SQLModel, table=True):
    """Database model for organizations/teams"""
    __tablename__ = "organization"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, index=True)
    description: str | None = Field(default=None, max_length=500)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    is_active: bool = Field(default=True)
    credits_balance: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4, description="Cached credits for the organization. Source of truth is the wallet ledger.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    projects: list["Project"] = Relationship(back_populates="organization")
    members: list["OrganizationMember"] = Relationship(back_populates="organization", cascade_delete=True)
    workspaces: list["Workspace"] = Relationship(back_populates="organization", cascade_delete=True)
    roles: list["Role"] = Relationship(back_populates="organization", cascade_delete=True)


# Organization Member Model
class OrganizationMember(SQLModel, table=True):
    """Database model for organization members"""
    __tablename__ = "organization_member"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE")
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    role: str = Field(max_length=50, default="member")  # member, org_super_admin
    joined_at: datetime | None = Field(default=None)
    status: str = Field(default="pending", max_length=20)  # pending, invited, active, suspended

    # Relationships
    organization: Organization | None = Relationship(back_populates="members")


# Organization Pydantic Schemas
class OrganizationCreate(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)

class OrganizationCreateWithAdmin(SQLModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    admin_email: EmailStr = Field(max_length=255)
    admin_name: str = Field(min_length=1, max_length=255)

class OrganizationUpdate(SQLModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    is_active: bool | None = None

class OrganizationPublic(SQLModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    owner_id: uuid.UUID
    is_active: bool
    created_at: datetime
    updated_at: datetime

class OrganizationMemberPublic(SQLModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    joined_at: datetime | None = None
    name: str | None = None
    email: str | None = None
    avatar: str | None = None
    workspaces_count: int = 0
    status: str = "pending"

class OrganizationTeamListResponse(SQLModel):
    list: list[OrganizationMemberPublic]
    total: int

# Organization Model Settings
class OrganizationModel(SQLModel, table=True):
    """Database model for organization-specific model settings"""
    __tablename__ = "organization_model"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE", index=True)
    model_id: uuid.UUID = Field(foreign_key="aimodel.id", nullable=False, ondelete="CASCADE", index=True)
    is_enabled: bool = Field(default=False, description="Whether this model is enabled for the organization")
    is_default: bool = Field(default=False, description="Whether this is the default model for the organization")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    model: Optional["AIModel"] = Relationship()


# Enhanced Project Model
class Project(SQLModel, table=True):
    """Database model for projects"""
    __tablename__ = "project"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, index=True)
    description: str | None = Field(default=None, max_length=500)
    # Store as strings to avoid enum validation issues
    type: str = Field(default="other", max_length=50, index=True)
    status: str = Field(default="in_development", max_length=50, index=True)
    project_url: str | None = Field(default=None, max_length=500)

    # Ownership
    owner_user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    org_id: uuid.UUID | None = Field(default=None, foreign_key="organization.id", nullable=True, ondelete="CASCADE")

    # API Key linkage (one-to-one)
    api_key_id: uuid.UUID | None = Field(default=None, foreign_key="apikey.id", nullable=True, unique=True)

    # Metadata
    is_active: bool = Field(default=True)
    is_deleted: bool = Field(default=False, index=True)  # Soft delete
    deleted_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    api_requests: list["APIRequest"] = Relationship(back_populates="project", cascade_delete=True)
    api_key: Optional["APIKey"] = Relationship(back_populates="project")
    organization: Organization | None = Relationship(back_populates="projects")


# Project Pydantic Schemas
class ProjectCreate(SQLModel):
    """Schema for creating a project"""
    name: str = Field(min_length=1, max_length=255, description="Project name")
    description: str | None = Field(default=None, max_length=500)
    type: ProjectType = Field(default=ProjectType.OTHER)
    status: ProjectStatus = Field(default=ProjectStatus.IN_DEVELOPMENT)
    project_url: str | None = Field(default=None, max_length=500)
    org_id: uuid.UUID | None = Field(default=None, description="Optional organization ID")
    api_key_id: uuid.UUID | None = Field(default=None, description="API key to link (optional, generates new if null)")


class ProjectUpdate(SQLModel):
    """Schema for updating a project"""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    type: ProjectType | None = None
    status: ProjectStatus | None = None
    project_url: str | None = Field(default=None, max_length=500)
    api_key_id: uuid.UUID | None = Field(default=None, description="Change API key linkage")


class ProjectPublic(SQLModel):
    """Public project schema"""
    id: uuid.UUID
    name: str
    description: str | None
    type: ProjectType
    status: ProjectStatus
    project_url: str | None
    owner_user_id: uuid.UUID
    org_id: uuid.UUID | None
    api_key_id: uuid.UUID | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    total_requests: int | None = None
    total_tokens: int | None = None
    total_cost: Decimal | None = None

    @model_validator(mode="after")
    def rename_default_project(self) -> "ProjectPublic":
        if self.name == "AI Engine (Direct API)":
            self.name = "AI Direct Access"
            if self.description == "Automatically created for direct AI API usage":
                self.description = "Direct API usage"
        return self


class ProjectCreated(ProjectPublic):
    """Project created successfully return schema"""
    plain_api_key: str | None = Field(default=None, description="The actual API key (if newly generated)")


class ProjectsPublic(SQLModel):
    """Schema for paginated projects"""
    data: list[ProjectPublic]
    count: int


class ProjectWithUsage(ProjectPublic):
    """Project schema with usage summary"""
    total_requests: int = 0
    total_cost: Decimal = Decimal("0.00")
    last_request_at: datetime | None = None


# Usage Analytics Schemas
class UsageMetricsSummary(SQLModel):
    """Summary metrics for project usage"""
    total_calls: int = 0
    total_tokens: int = 0
    total_cost: Decimal = Decimal("0.00")
    avg_response_time_ms: float = 0.0
    success_rate: float = 0.0


class UsageTrendData(SQLModel):
    """Daily usage trend data point"""
    date: str  # ISO format date string (YYYY-MM-DD)
    api_calls: int = 0
    tokens_consumed: int = 0
    cost: Decimal = Decimal("0.00")


class RecentAPICall(SQLModel):
    """Recent API call log"""
    id: uuid.UUID
    timestamp: datetime
    model: str
    endpoint: str
    total_tokens: int
    cost: Decimal
    status: str
    response_time_ms: int | None


class ProjectUsageResponse(SQLModel):
    """Complete project usage analytics response"""
    project: ProjectPublic
    date_range: dict[str, str]  # {"start": "2024-01-01", "end": "2024-01-31"}
    metrics_summary: UsageMetricsSummary
    usage_trends: list[UsageTrendData]
    recent_calls: list[RecentAPICall]
    total_recent_calls: int
    page: int = 1
    page_size: int = 50


# API Request Model
class APIRequest(SQLModel, table=True):
    __tablename__ = "apirequest"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(foreign_key="project.id", nullable=False, ondelete="CASCADE")
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    model: str = Field(max_length=100, index=True)  # e.g., "gpt-4", "claude-sonnet", "llama-3"
    endpoint: str = Field(max_length=255)  # API endpoint called
    request_tokens: int = Field(default=0)
    response_tokens: int = Field(default=0)
    total_tokens: int = Field(default=0)
    cost: Decimal = Field(default=Decimal("0.00"), max_digits=10, decimal_places=4)  # Cost in USD
    status: str = Field(max_length=50, default="success")  # success, error, timeout
    response_time_ms: int | None = Field(default=None)  # Response time in milliseconds
    organization_id: uuid.UUID | None = Field(default=None, foreign_key="organization.id", nullable=True, ondelete="SET NULL", index=True)
    ip_address: str | None = Field(default=None, max_length=50)
    origin: str | None = Field(default=None, max_length=255)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    project: Project | None = Relationship(back_populates="api_requests")


class APIRequestPublic(SQLModel):
    """Public API request schema"""
    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    model: str
    endpoint: str
    request_tokens: int
    response_tokens: int
    total_tokens: int
    cost: Decimal
    status: str
    response_time_ms: int | None
    organization_id: uuid.UUID | None = None
    ip_address: str | None = None
    origin: str | None = None
    created_at: datetime


class APIRequestsPublic(SQLModel):
    """Schema for paginated API requests"""
    data: list[APIRequestPublic]
    count: int


# Credit Transaction Model (for general credit tracking)
class CreditTransaction(SQLModel, table=True):
    __tablename__ = "credit_transaction"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    amount: Decimal = Field(max_digits=10, decimal_places=2)  # Positive for credit, negative for debit
    balance_after: Decimal = Field(max_digits=10, decimal_places=2)  # Balance after transaction
    transaction_type: str = Field(max_length=50, index=True)  # purchase, usage, refund, bonus
    description: str | None = Field(default=None, max_length=500)
    reference_id: str | None = Field(default=None, max_length=255)  # Payment or API request reference
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


# Credit Transfer Model (for user-to-user credit transfers)
class CreditTransferBase(SQLModel):
    """Base model for credit transfers between users"""
    sender_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    recipient_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    amount: int = Field(gt=0, description="Amount of credits transferred")
    message: str | None = Field(default=None, max_length=500)
    status: str = Field(default="pending")


class CreditTransfer(CreditTransferBase, table=True):
    """Database model for credit transfers between users"""
    __tablename__ = "credit_transfer"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    sender: User | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[CreditTransfer.sender_id]"}
    )
    recipient: User | None = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[CreditTransfer.recipient_id]"}
    )


class CreditTransferCreate(SQLModel):
    """Schema for creating a credit transfer"""
    recipientIds: list[uuid.UUID] | None = Field(default=None, description="List of recipient user IDs")
    recipientTags: list[str] | None = Field(default=None, description="List of recipient user tags (e.g., @qor123456)")
    amount: int = Field(gt=0, description="Amount of credits to transfer per recipient")
    message: str | None = Field(default=None, max_length=500)


class CreditTransferPublic(SQLModel):
    """Public schema for credit transfer"""
    id: uuid.UUID
    senderId: uuid.UUID
    recipientId: uuid.UUID
    amount: int
    message: str | None
    status: str
    createdAt: datetime
    updatedAt: datetime
    recipientName: str | None = None
    recipientEmail: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class CreditTransferList(SQLModel):
    """Schema for paginated credit transfers"""
    transactions: list[CreditTransferPublic]
    total: int


class SharedCreditsStats(SQLModel):
    """Schema for shared credits statistics"""
    available_credits: int = Field(alias="availableCredits")
    total_recipients: int = Field(alias="totalRecipients")
    credits_shared: int = Field(alias="creditsShared")
    total_transfers: int = Field(alias="totalTransfers")
    cost_naira: Decimal = Field(default=Decimal("0.00"), alias="costNaira")


# AI Chat Models
class AIChat(SQLModel, table=True):
    """AI Chat conversation model"""
    __tablename__ = "ai_chats"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    title: str = Field(default="New Chat", max_length=500)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Relationships
    messages: list["AIChatMessage"] = Relationship(back_populates="chat", cascade_delete=True)


class AIChatMessage(SQLModel, table=True):
    """AI Chat message model"""
    __tablename__ = "ai_chat_messages"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    chat_id: uuid.UUID = Field(foreign_key="ai_chats.id", nullable=False, ondelete="CASCADE", index=True)
    role: str = Field(max_length=20, index=True)  # 'user' or 'assistant'
    content: str  # The message content
    tokens_used: int | None = Field(default=None)  # Tokens used for this message
    model: str | None = Field(default=None, max_length=100)  # AI model used
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationships
    chat: AIChat | None = Relationship(back_populates="messages")


# AI Chat Pydantic Schemas
class AIChatCreate(SQLModel):
    """Schema for creating a new chat"""
    title: str | None = Field(default="New Chat", max_length=500)


class AIChatUpdate(SQLModel):
    """Schema for updating a chat"""
    title: str = Field(min_length=1, max_length=500)


class AIChatMessagePublic(SQLModel):
    """Public schema for chat messages"""
    id: uuid.UUID
    chat_id: uuid.UUID
    role: str
    content: str
    tokens_used: int | None
    model: str | None
    created_at: datetime


class AIChatPublic(SQLModel):
    """Public schema for chats"""
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    messages: list[AIChatMessagePublic] = []


class AIChatListPublic(SQLModel):
    """Public schema for chat list (without messages)"""
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    created_at: datetime
    updated_at: datetime
    last_message_preview: str | None = None


class AIChatsPublic(SQLModel):
    """Public schema for list of chats"""
    data: list[AIChatListPublic]
    count: int


# Team models / schemas (lightweight views for API responses)
class TeamMemberPublic(SQLModel):
    id: uuid.UUID
    name: str | None = None
    firstName: str | None = None
    lastName: str | None = None
    email: EmailStr
    username: str | None = None
    phoneNumber: str | None = None
    address: str | None = None
    postcode: str | None = None
    city: str | None = None
    country: str | None = None
    img: str | None = None
    role: str | None = None
    lastOnline: datetime | None = None
    status: str | None = None
    totalSpending: Decimal | None = None


class TeamListResponse(SQLModel):
    list: list[TeamMemberPublic]
    total: int


class TeamAnalytics(SQLModel):
    totalMembers: int
    activeMembers: int
    teamUsage: Decimal
    teamUsagePeriod: str | None = None
    sharedCredits: Decimal
    sharedCreditsChange: Decimal | None = None
    sharedCreditsChangePeriod: str | None = None
    pendingInvites: int
    pendingInvitesStatus: str | None = None


class AIChatSendMessage(SQLModel):
    """Schema for sending a message"""
    message: str = Field(min_length=1, max_length=10000)
    model: str | None = Field(default="gpt-3.5-turbo", description="AI model to use for the response")


class AIChatMessageResponse(SQLModel):
    """Response after sending a message"""
    user_message: AIChatMessagePublic
    assistant_message: AIChatMessagePublic


# Top-Up / Payment Models
class TopUpStatus(str, Enum):
    """Top-up status enum"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


class TopUp(SQLModel, table=True):
    """Database model for credit top-ups via bank transfer"""
    __tablename__ = "topup"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    workspace_id: uuid.UUID | None = Field(default=None, foreign_key="workspace.id", nullable=True, index=True)
    organization_id: uuid.UUID | None = Field(default=None, foreign_key="organization.id", nullable=True, index=True)
    amount_naira: Decimal = Field(max_digits=10, decimal_places=2, description="Amount in Naira")
    ai_credits: Decimal = Field(max_digits=10, decimal_places=4, description="Equivalent AI credits")
    status: TopUpStatus = Field(default=TopUpStatus.PENDING)
    payment_reference: str = Field(max_length=255, unique=True, index=True)
    monnify_reference: str | None = Field(default=None, max_length=255)
    account_number: str | None = Field(default=None, max_length=50)
    bank_name: str | None = Field(default=None, max_length=100)
    payment_method: str = Field(default="bank_transfer", max_length=50)
    paid_at: datetime | None = Field(default=None)
    expires_at: datetime = Field(description="Payment reference expires after 24 hours")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TopUpPublic(SQLModel):
    """Public schema for top-up"""
    id: uuid.UUID
    user_id: uuid.UUID
    workspace_id: uuid.UUID | None = Field(default=None, alias="workspaceId")
    amount_naira: Decimal
    ai_credits: Decimal
    status: TopUpStatus
    payment_reference: str
    account_number: str | None
    bank_name: str | None
    payment_method: str
    paid_at: datetime | None
    expires_at: datetime
    created_at: datetime
    updated_at: datetime


class TopUpCreate(SQLModel):
    """Schema for creating a top-up"""
    amount: Decimal = Field(gt=0, description="Amount in Naira (minimum ₦100)")
    payment_method: str = Field(default="bank_transfer")
    workspace_id: uuid.UUID | None = Field(default=None, alias="workspaceId")
    organization_id: uuid.UUID | None = Field(default=None, alias="organizationId")

    model_config = ConfigDict(populate_by_name=True)


class TopUpStatusResponse(SQLModel):
    """Response for top-up status check"""
    status: TopUpStatus
    updated_at: datetime
    paid_at: datetime | None = None


# API Key Models
class APIKey(SQLModel, table=True):
    """Database model for user API keys"""
    __tablename__ = "apikey"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    name: str = Field(max_length=255, description="User-friendly name for the API key")
    key_prefix: str = Field(max_length=20, description="First few characters of the key for display")
    key_hash: str = Field(max_length=255, description="Hashed API key")
    is_active: bool = Field(default=True)
    last_used_at: datetime | None = Field(default=None)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    expires_at: datetime | None = Field(default=None, description="Optional expiration date")

    # Usage tracking
    total_requests: int = Field(default=0)
    total_cost: Decimal = Field(default=Decimal("0.00"), max_digits=10, decimal_places=4)
    abuse_score: int = Field(default=0)
    allowed_ips: str | None = Field(default=None, description="Comma-separated list of allowed IP addresses/CIDR")
    allowed_domains: str | None = Field(default=None, description="Comma-separated list of allowed domains (CORS)")

    # Relationships
    project: Optional["Project"] = Relationship(back_populates="api_key")


class APIKeyPublic(SQLModel):
    """Public schema for API key (without the actual key)"""
    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    key_prefix: str
    is_active: bool
    last_used_at: datetime | None
    created_at: datetime
    expires_at: datetime | None
    total_requests: int
    total_cost: Decimal
    abuseScore: int = Field(default=0, alias="abuse_score")
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    allowed_ips: str | None = None
    allowed_domains: str | None = None

    model_config = ConfigDict(populate_by_name=True)


class APIKeyCreate(SQLModel):
    """Schema for creating an API key"""
    name: str = Field(min_length=1, max_length=255, description="Name for the API key")
    expires_in_days: int | None = Field(default=None, ge=1, le=365, description="Optional expiration in days")
    allowed_ips: str | None = Field(default=None, description="Optional IP whitelisting")
    allowed_domains: str | None = Field(default=None, description="Optional domain whitelisting")


class APIKeyCreated(SQLModel):
    """Response when creating an API key (includes the actual key once)"""
    id: uuid.UUID
    name: str
    key: str  # The actual API key - only shown once!
    key_prefix: str
    created_at: datetime
    expires_at: datetime | None


class APIKeysResponse(SQLModel):
    """Response for listing API keys"""
    keys: list[APIKeyPublic]
    total: int


# ==================== Workspace Models ====================

class WorkspaceStatus(str, Enum):
    """Workspace status enum"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    INACTIVE = "inactive"


class MemberStatus(str, Enum):
    """Member status enum"""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"


class WorkspaceProjectStatus(str, Enum):
    """Workspace project status enum"""
    ACTIVE = "active"
    ARCHIVED = "archived"


class TransactionType(str, Enum):
    """Transaction type enum"""
    PURCHASE = "purchase"
    ALLOCATION = "allocation"
    USAGE = "usage"
    REFUND = "refund"





# Workspace Model
class Workspace(SQLModel, table=True):
    """Database model for workspaces"""
    __tablename__ = "workspace"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=255, index=True)
    description: str = Field(default="")
    avatar: str | None = Field(default=None, max_length=500)
    owner_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    organization_id: uuid.UUID | None = Field(default=None, foreign_key="organization.id", nullable=True, ondelete="CASCADE", index=True)
    credits_balance: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    monthly_credit_limit: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    status: str = Field(default="active", max_length=20)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    organization: Optional["Organization"] = Relationship(back_populates="workspaces")
    members: list["WorkspaceMember"] = Relationship(back_populates="workspace", cascade_delete=True)
    roles: list["WorkspaceRole"] = Relationship(back_populates="workspace", cascade_delete=True)
    projects: list["WorkspaceProject"] = Relationship(back_populates="workspace", cascade_delete=True)
    transactions: list["WorkspaceCreditTransaction"] = Relationship(back_populates="workspace", cascade_delete=True)


# Workspace Member Model
class WorkspaceMember(SQLModel, table=True):
    """Database model for workspace members"""
    __tablename__ = "workspace_member"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True)
    user_id: uuid.UUID | None = Field(foreign_key="user.id", nullable=True, ondelete="CASCADE", index=True)
    invited_email: str | None = Field(default=None, max_length=255, index=True)  # Email for users who haven't registered yet
    credits_allocated: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    status: str = Field(default="active", max_length=20)
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_active: datetime | None = None

    # Relationships
    workspace: Workspace = Relationship(back_populates="members")
    member_roles: list["WorkspaceMemberRole"] = Relationship(back_populates="member", cascade_delete=True)


# Workspace Role Model
class WorkspaceRole(SQLModel, table=True):
    """Database model for workspace roles"""
    __tablename__ = "workspace_role"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True)
    name: str = Field(max_length=100, index=True)
    description: str = Field(default="")
    is_custom: bool = Field(default=True)
    permissions: dict = Field(default_factory=dict, sa_type=JSON)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    workspace: Workspace = Relationship(back_populates="roles")
    member_roles: list["WorkspaceMemberRole"] = Relationship(back_populates="role", cascade_delete=True)


# Workspace Member-Role Link Table
class WorkspaceMemberRole(SQLModel, table=True):
    """Database model for workspace member-role assignments"""
    __tablename__ = "workspace_member_role"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    member_id: uuid.UUID = Field(foreign_key="workspace_member.id", nullable=False, ondelete="CASCADE", index=True)
    role_id: uuid.UUID = Field(foreign_key="workspace_role.id", nullable=False, ondelete="CASCADE", index=True)
    assigned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    member: WorkspaceMember = Relationship(back_populates="member_roles")
    role: WorkspaceRole = Relationship(back_populates="member_roles")


# Workspace Project Model
class WorkspaceProject(SQLModel, table=True):
    """Database model for workspace projects"""
    __tablename__ = "workspace_project"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True)
    name: str = Field(max_length=255, index=True)
    description: str = Field(default="")
    created_by: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    status: str = Field(default="active", max_length=20)
    credits_used: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    api_calls_count: int = Field(default=0)
    last_activity: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    workspace: Workspace = Relationship(back_populates="projects")
    project_members: list["WorkspaceProjectMember"] = Relationship(back_populates="project", cascade_delete=True)


# Workspace Project-Member Link Table
class WorkspaceProjectMember(SQLModel, table=True):
    """Database model for workspace project-member assignments"""
    __tablename__ = "workspace_project_member"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    project_id: uuid.UUID = Field(foreign_key="workspace_project.id", nullable=False, ondelete="CASCADE", index=True)
    member_id: uuid.UUID = Field(foreign_key="workspace_member.id", nullable=False, ondelete="CASCADE", index=True)
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    project: WorkspaceProject = Relationship(back_populates="project_members")


# Workspace Credit Transaction Model
class WorkspaceCreditTransaction(SQLModel, table=True):
    """Database model for workspace credit transactions"""
    __tablename__ = "workspace_credit_transaction"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True)
    type: str = Field(max_length=20)
    amount: Decimal = Field(max_digits=12, decimal_places=4)
    tokens: int = Field(default=0)
    balance: Decimal = Field(max_digits=12, decimal_places=4)

    description: str
    recipient_id: uuid.UUID | None = Field(default=None, foreign_key="workspace_member.id", nullable=True, ondelete="SET NULL")
    status: str = Field(default="completed", max_length=20)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    workspace: Workspace = Relationship(back_populates="transactions")


class OrganizationCreditTransaction(SQLModel, table=True):
    """Database model for organization-level credit transactions"""
    __tablename__ = "organization_credit_transaction"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    organization_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE", index=True)
    amount: Decimal = Field(max_digits=12, decimal_places=4)
    balance_after: Decimal = Field(max_digits=12, decimal_places=4)
    transaction_type: str = Field(max_length=50, index=True)  # topup, allocation, usage, refund
    description: str = Field(max_length=500)
    workspace_id: uuid.UUID | None = Field(default=None, foreign_key="workspace.id", nullable=True, ondelete="SET NULL")
    performed_by: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True, ondelete="SET NULL")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


# ==================== Wallet & Ledger Models (Production Grade) ====================

class Wallet(SQLModel, table=True):
    """
    Wallet entity representing ownership of credits.
    Wallets are owned by Organizations or Users.
    """
    __tablename__ = "wallet"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    owner_type: WalletOwnerType = Field(
        sa_column=sa.Column(
            sa.Enum(WalletOwnerType, name="walletownertype", values_callable=lambda x: [e.value for e in x]),
            nullable=False,
            index=True
        )
    )
    owner_id: uuid.UUID = Field(index=True)
    currency: str = Field(default="CREDITS", max_length=10)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationship to transactions
    wallet_transactions: list["WalletTransaction"] = Relationship(back_populates="wallet", cascade_delete=True)


class WalletTransaction(SQLModel, table=True):
    """
    Immutable ledger of all wallet activities.
    Balance is derived as: SUM(credit) - SUM(debit)
    """
    __tablename__ = "wallet_transaction"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    wallet_id: uuid.UUID = Field(foreign_key="wallet.id", index=True, nullable=False, ondelete="CASCADE")
    transaction_type: WalletTransactionType = Field(
        sa_column=sa.Column(
            sa.Enum(WalletTransactionType, name="wallettransactiontype", values_callable=lambda x: [e.value for e in x]),
            nullable=False,
            index=True
        )
    )
    
    # Financial indicators
    credit: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    debit: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    transfer_in: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    transfer_out: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    amount: Decimal = Field(max_digits=12, decimal_places=4, description="Net movement amount")
    
    # Context
    description: str | None = Field(default=None, max_length=500)
    source: str | None = Field(default=None, max_length=100) # e.g., 'flutterwave', 'p2p_transfer', 'ai_usage'
    reference_id: str | None = Field(default=None, max_length=255, description="External reference (Payment Ref, API Request ID, etc.)")
    idempotency_key: str | None = Field(default=None, max_length=255, unique=True, index=True)
    
    # Audit
    created_by: uuid.UUID | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

    # Relationships
    wallet: Wallet = Relationship(back_populates="wallet_transactions")


class WorkspaceUsageTracking(SQLModel, table=True):
    """Database model for tracking workspace AI credit usage per period"""
    __tablename__ = "workspace_usage_tracking"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    workspace_id: uuid.UUID = Field(foreign_key="workspace.id", nullable=False, ondelete="CASCADE", index=True)
    organization_id: uuid.UUID = Field(foreign_key="organization.id", nullable=False, ondelete="CASCADE", index=True)
    billing_period_start: datetime = Field(index=True)
    billing_period_end: datetime = Field(index=True)
    total_usage: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    usage_breakdown: dict = Field(default_factory=dict, sa_column=Column(JSON))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Workspace Pydantic Schemas
class WorkspaceCreate(SQLModel):
    """Schema for creating a workspace"""
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")


class WorkspaceUpdate(SQLModel):
    """Schema for updating a workspace"""
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    avatar: str | None = None
    status: str | None = None


class WorkspacePublic(SQLModel):
    """Public workspace response schema"""
    id: uuid.UUID
    name: str
    description: str
    avatar: str | None
    owner_id: uuid.UUID = Field(alias="ownerId")
    organization_id: uuid.UUID | None = Field(default=None, alias="organizationId")
    credits_balance: Decimal = Field(alias="creditsBalance")
    status: str
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    total_members: int = Field(default=0, alias="totalMembers")
    total_projects: int = Field(default=0, alias="totalProjects")
    organization_name: str | None = Field(default=None, alias="organizationName")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkspacesPublic(SQLModel):
    """Response for listing workspaces"""
    workspaces: list[WorkspacePublic]
    total: int


# Workspace Member Schemas
class WorkspaceMemberPublic(SQLModel):
    """Public workspace member response schema"""
    id: uuid.UUID
    workspace_id: uuid.UUID = Field(alias="workspaceId")
    user_id: uuid.UUID | None = Field(alias="userId")
    name: str
    email: str
    avatar: str | None
    roles: list[str]
    credits_allocated: Decimal = Field(alias="creditsAllocated")
    status: str
    joined_at: datetime = Field(alias="joinedAt")
    last_active: datetime | None = Field(alias="lastActive")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkspaceMembersPublic(SQLModel):
    """Response for listing workspace members"""
    members: list[WorkspaceMemberPublic]
    total: int



class AddMemberRequest(SQLModel):
    """Schema for adding an existing organization member to a workspace"""
    user_id: uuid.UUID = Field(alias="userId")
    roles: list[str]
    credits_to_allocate: Decimal | None = None

    model_config = ConfigDict(populate_by_name=True)


# Workspace Role Schemas
class RolePermissions(SQLModel):
    """Role permissions schema"""
    access_ai_credits: bool = False
    manage_workspaces: bool = False
    create_projects: bool = False
    manage_billing: bool = False
    manage_integrations: bool = False
    invite_members: bool = False
    manage_roles: bool = False
    view_reports: bool = False
    manage_members: bool = False
    delete_workspace: bool = False


class WorkspaceRoleCreate(SQLModel):
    """Schema for creating a workspace role"""
    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="")
    permissions: RolePermissions


class WorkspaceRoleUpdate(SQLModel):
    """Schema for updating a workspace role"""
    name: str | None = None
    description: str | None = None
    permissions: RolePermissions | None = None


class WorkspaceRolePublic(SQLModel):
    """Public workspace role response schema"""
    id: uuid.UUID
    workspace_id: uuid.UUID = Field(alias="workspaceId")
    name: str
    description: str
    is_custom: bool = Field(alias="isCustom")
    permissions: dict
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkspaceRolesPublic(SQLModel):
    """Response for listing workspace roles"""
    roles: list[WorkspaceRolePublic]
    total: int


# Workspace Project Schemas
class WorkspaceProjectCreate(SQLModel):
    """Schema for creating a workspace project"""
    name: str = Field(min_length=1, max_length=255)
    description: str = Field(default="")
    members: list[uuid.UUID] = []


class WorkspaceProjectUpdate(SQLModel):
    """Schema for updating a workspace project"""
    name: str | None = None
    description: str | None = None
    status: str | None = None


class WorkspaceProjectPublic(SQLModel):
    """Public workspace project response schema"""
    id: uuid.UUID
    workspace_id: uuid.UUID = Field(alias="workspaceId")
    name: str
    description: str
    created_by: uuid.UUID = Field(alias="createdBy")
    status: str
    credits_used: Decimal = Field(alias="creditsUsed")
    api_calls_count: int = Field(alias="apiCallsCount")
    last_activity: datetime | None = Field(alias="lastActivity")
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")
    members: list[str] = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class WorkspaceProjectsPublic(SQLModel):
    """Response for listing workspace projects"""
    projects: list[WorkspaceProjectPublic]
    total: int


# Credit Transaction Schemas
class AllocateCreditsRequest(SQLModel):
    """Schema for allocating credits to a member"""
    member_id: uuid.UUID | None = None
    amount: Decimal
    message: str | None = None


class TopUpCreditsRequest(SQLModel):
    """Schema for topping up workspace credits"""
    amount: Decimal


class CreditTransactionPublic(SQLModel):
    """Public credit transaction response schema"""
    id: uuid.UUID
    workspace_id: uuid.UUID = Field(alias="workspaceId")
    type: str
    amount: Decimal
    balance: Decimal
    description: str
    recipient_id: uuid.UUID | None = Field(default=None, alias="recipientId")
    recipient_name: str | None = Field(default=None, alias="recipientName")
    status: str
    created_at: datetime = Field(alias="createdAt")

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class CreditTransactionsPublic(SQLModel):
    """Response for listing credit transactions"""
    transactions: list[CreditTransactionPublic]
    total: int


# Dashboard Stats Schema
class WorkspaceDashboardStats(SQLModel):
    """Workspace dashboard statistics schema"""
    credits_balance: Decimal
    total_members: int
    total_projects: int
    total_api_calls: int
    credits_used_today: Decimal
    credits_used_this_month: Decimal
    tokens_used_today: int = 0
    tokens_used_this_month: int = 0
    credit_burn_rate: Decimal
    active_integrations: int
    success_rate: Decimal
    daily_usage: list[dict] | None = None
    recent_requests: list[dict] | None = None


# Usage Report Schemas
class MemberUsage(SQLModel):
    """Member usage statistics schema"""
    member_id: uuid.UUID = Field(alias="memberId")
    member_name: str = Field(alias="memberName")
    member_email: str = Field(alias="memberEmail")
    credits_used: Decimal = Field(alias="creditsUsed")
    api_calls: int = Field(alias="apiCalls")
    tokens: int

    model_config = ConfigDict(populate_by_name=True)


class ProjectUsage(SQLModel):
    """Project usage statistics schema"""
    project_id: uuid.UUID = Field(alias="projectId")
    project_name: str = Field(alias="projectName")
    credits_used: Decimal = Field(alias="creditsUsed")
    api_calls: int = Field(alias="apiCalls")
    tokens: int

    model_config = ConfigDict(populate_by_name=True)


class UsageTrend(SQLModel):
    """Usage trend data schema"""
    date: str
    credits_consumed: Decimal = Field(alias="creditsConsumed")
    api_calls: int = Field(alias="apiCalls")
    tokens: int

    model_config = ConfigDict(populate_by_name=True)


class WorkspaceUsageReport(SQLModel):
    """Workspace usage report schema"""
    workspace_id: uuid.UUID = Field(alias="workspaceId")
    period: str
    total_credits_consumed: Decimal = Field(alias="totalCreditsConsumed")
    total_api_calls: int = Field(alias="totalApiCalls")
    total_tokens: int = Field(alias="totalTokens")
    per_member_usage: list[MemberUsage] = Field(alias="perMemberUsage")
    per_project_usage: list[ProjectUsage] = Field(alias="perProjectUsage")
    trends: list[UsageTrend]

    model_config = ConfigDict(populate_by_name=True)


# ==================== OAuth Connection ====================

class OAuthConnection(SQLModel, table=True):
    """
    Model for storing OAuth connections to external services (Google Drive, Dropbox, etc.)
    """
    __tablename__ = "oauth_connection"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(index=True, nullable=False)  # Owner of the connection
    workspace_id: uuid.UUID | None = Field(default=None, index=True)  # Optional workspace association

    # Connection metadata
    provider: str = Field(max_length=50, index=True)  # 'google-drive', 'dropbox', etc.
    provider_user_id: str | None = Field(default=None)  # User ID from the provider
    provider_email: str | None = Field(default=None)  # Email from the provider

    # OAuth tokens (should be encrypted in production)
    access_token: str = Field(max_length=1000)
    refresh_token: str | None = Field(default=None, max_length=1000)
    token_type: str = Field(default="Bearer", max_length=50)
    expires_at: datetime | None = None  # When the access token expires

    # Scopes granted
    scopes: str | None = None  # JSON array of scopes

    # Connection status
    is_active: bool = Field(default=True)
    last_synced_at: datetime | None = None

    # Connection metadata (renamed to avoid SQLAlchemy reserved word)
    connection_metadata: dict = Field(default_factory=dict, sa_column=Column(JSON))

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))# --- Notification Models ---

class Notification(SQLModel, table=True):
    """Database model for user notifications"""
    __tablename__ = "notification"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    title: str = Field(max_length=255)
    description: str = Field(max_length=1000)
    type: str = Field(max_length=50, default="general")  # credit_received, low_balance, workspace_invite, system
    is_read: bool = Field(default=False, index=True)
    metadata_json: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)


class NotificationPublic(SQLModel):
    """Public schema for notification"""
    id: uuid.UUID
    userId: uuid.UUID = Field(alias="userId")
    title: str
    description: str
    type: str
    isRead: bool = Field(alias="isRead")
    createdAt: datetime = Field(alias="createdAt")
    metadata: dict | None = None

    model_config = ConfigDict(populate_by_name=True)


class NotificationsPublic(SQLModel):
    """Schema for paginated notifications"""
    data: list[NotificationPublic]
    count: int
    unreadCount: int = Field(alias="unreadCount")

    model_config = ConfigDict(populate_by_name=True)
# ==================== AI Provider & Model Registry ====================

class AIProvider(SQLModel, table=True):
    """Database model for AI providers (e.g., OpenAI, Anthropic)"""
    __tablename__ = "aiprovider"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(unique=True, index=True, max_length=255)
    slug: str = Field(unique=True, index=True, max_length=100)
    description: str | None = Field(default=None, max_length=500)
    website: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    models: list["AIModel"] = Relationship(back_populates="provider", cascade_delete=True)


class AIModel(SQLModel, table=True):
    """Database model for AI models registered in the global registry"""
    __tablename__ = "aimodel"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(index=True, max_length=255)
    slug: str = Field(unique=True, index=True, max_length=100)
    provider_id: uuid.UUID = Field(foreign_key="aiprovider.id", nullable=False, ondelete="CASCADE")
    
    description: str | None = Field(default=None, max_length=1000)
    context_size: str | None = Field(default=None, max_length=50)
    input_price: Decimal = Field(default=Decimal("0.0000"), max_digits=10, decimal_places=6)
    output_price: Decimal = Field(default=Decimal("0.0000"), max_digits=10, decimal_places=6)
    
    capabilities: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    status: str = Field(default="Approved", max_length=50) # Approved, Experimental, Deprecated
    availability: str = Field(default="Global", max_length=50) # Global, Enterprise-only, Internal
    
    category: str = Field(default="Text", max_length=50) # Text, Embedding, Vision, Audio
    
    # Extra data (matching frontend RegistryModel)
    best_use_cases: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    token_limits: dict = Field(default_factory=dict, sa_column=Column(JSON)) # {rpm: 1000, tpm: 10000}
    compliance: dict = Field(default_factory=dict, sa_column=Column(JSON)) # {piiHandling: bool, safetyTags: list[str], internalNotes: str}
    lifecycle: dict = Field(default_factory=dict, sa_column=Column(JSON)) # {deprecationDate: str, statusHistory: list[dict]}
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    provider: AIProvider | None = Relationship(back_populates="models")


class AIProviderPublic(SQLModel):
    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    website: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AIModelPublic(SQLModel):
    id: uuid.UUID
    name: str
    slug: str
    providerId: uuid.UUID
    provider: str | None = None
    providerSlug: str | None = None
    description: str | None = None
    contextSize: str | None = None
    inputPrice: float = 0.0
    outputPrice: float = 0.0
    capabilities: list[str] = []
    status: str
    availability: str
    category: str
    bestUseCases: list[str] = []
    tokenLimits: dict = {}
    compliance: dict = {}
    lifecycle: dict = {}
    lastUpdated: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class AIModelsPublic(SQLModel):
    models: list[AIModelPublic]
    total: int


class AIProvidersPublic(SQLModel):
    providers: list[AIProviderPublic]
    total: int


class AIModelCreate(SQLModel):
    name: str
    slug: str
    provider_id: uuid.UUID = Field(alias="providerId")
    description: str | None = None
    context_size: str | None = Field(default=None, alias="contextSize")
    input_price: Decimal = Field(default=Decimal("0.0000"), alias="inputPrice")
    output_price: Decimal = Field(default=Decimal("0.0000"), alias="outputPrice")
    capabilities: list[str] = []
    status: str = "Approved"
    availability: str = "Global"
    category: str = "Text"
    best_use_cases: list[str] = Field(default_factory=list, alias="bestUseCases")
    token_limits: dict = Field(default_factory=dict, alias="tokenLimits")
    compliance: dict = Field(default_factory=dict, alias="compliance")
    lifecycle: dict = Field(default_factory=dict, alias="lifecycle")

    model_config = ConfigDict(populate_by_name=True)


class AIModelUpdate(SQLModel):
    name: str | None = None
    description: str | None = None
    context_size: str | None = Field(default=None, alias="contextSize")
    input_price: Decimal | None = Field(default=None, alias="inputPrice")
    output_price: Decimal | None = Field(default=None, alias="outputPrice")
    capabilities: list[str] | None = None
    status: str | None = None
    availability: str | None = None
    category: str | None = None
    best_use_cases: list[str] | None = Field(default=None, alias="bestUseCases")
    token_limits: dict | None = Field(default=None, alias="tokenLimits")
    compliance: dict | None = Field(default=None, alias="compliance")
    lifecycle: dict | None = Field(default=None, alias="lifecycle")

    model_config = ConfigDict(populate_by_name=True)


# ==================== Campaign / Program Models ====================
class CampaignStatus(str, Enum):
    """Campaign status enum"""
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    DRAFT = "draft"


class Campaign(SQLModel, table=True):
    """Database model for bulk credit campaigns/programs"""
    __tablename__ = "campaign"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    organization_id: uuid.UUID | None = Field(default=None, foreign_key="organization.id", nullable=True, index=True, description="The organization that owns this campaign, if any.")
    name: str = Field(max_length=255, index=True)
    description: str | None = Field(default=None, max_length=500)
    type: str = Field(max_length=50, default="general")  # bootcamp, corporate, rewards, general
    status: str = Field(max_length=50, default="draft", index=True)  # active, paused, completed, draft
    amount: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2, description="Total amount allocated")
    recipients: int = Field(default=0, description="Number of recipients")
    progress: int = Field(default=0, description="Program progress percentage (0-100)")
    total_distributed: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2, description="Total credits distributed")
    spent_naira: Decimal = Field(default=Decimal("0.00"), max_digits=12, decimal_places=2, description="Total Naira equivalent spent")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    starts_at: datetime | None = Field(default=None)
    ends_at: datetime | None = Field(default=None)


class CampaignCreate(SQLModel):
    """Schema for creating a campaign"""
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    type: str = Field(default="general", max_length=50)
    organization_id: uuid.UUID | None = None
    amount: Decimal = Field(default=Decimal("0.00"))
    recipients: int = Field(default=0)
    status: str | None = Field(default="active", max_length=50)
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CampaignUpdate(SQLModel):
    """Schema for updating a campaign"""
    name: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=500)
    type: str | None = Field(default=None, max_length=50)
    organization_id: uuid.UUID | None = None
    status: str | None = Field(default=None, max_length=50)
    amount: Decimal | None = None
    recipients: int | None = None
    progress: int | None = None
    total_distributed: Decimal | None = None
    spent_naira: Decimal | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class CampaignPublic(SQLModel):
    """Public schema for campaign"""
    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID | None
    name: str
    description: str | None
    type: str
    status: str
    amount: Decimal
    recipients: int
    progress: int
    total_distributed: Decimal
    spent_naira: Decimal
    created_at: datetime
    updated_at: datetime
    starts_at: datetime | None
    ends_at: datetime | None

# ==================== Security Models ====================

class SecurityEvent(SQLModel, table=True):
    """Database model for security events"""
    __tablename__ = "security_event"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    type: str = Field(max_length=50, index=True)  # token_spike, api_abuse, fraud, policy_violation
    severity: str = Field(max_length=20, index=True)  # low, medium, high, critical
    description: str = Field(max_length=500)
    source_ip: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=100)
    status: str = Field(default="open", max_length=20, index=True)  # open, investigating, resolved, dismissed
    
    user_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    assigned_to_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL")
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Relationships
    user: User | None = Relationship(sa_relationship_kwargs={"foreign_keys": "[SecurityEvent.user_id]"})
    assigned_to: User | None = Relationship(sa_relationship_kwargs={"foreign_keys": "[SecurityEvent.assigned_to_id]"})


class SecurityEventPublic(SQLModel):
    """Public schema for security event"""
    id: uuid.UUID
    type: str
    severity: str
    description: str
    sourceIp: str | None
    location: str | None
    status: str
    timestamp: str | None = None 
    user: UserPublic | None = None
    assignedTo: UserPublic | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(populate_by_name=True)


class SecurityEventListResponse(SQLModel):
    """Response for listing security events"""
    events: list[SecurityEventPublic]
    total: int



class SecurityEventAction(SQLModel):
    action: str 
    reason: str | None = None


class ApiKeyAction(SQLModel):
    action: str
    reason: str | None = None


class SecurityActionResponse(SQLModel):
    success: bool
    message: str


class AdminActionRequest(SQLModel):
    userId: uuid.UUID
    action: str
    reason: str


class SecurityApiKeyPublic(SQLModel):
    id: uuid.UUID
    keyName: str
    keyPrefix: str
    owner: str 
    ownerId: uuid.UUID
    lastUsed: str | None = None
    requestCount: int
    status: str 
    abuseScore: int
    dailyLimit: int = 1000 

    model_config = ConfigDict(populate_by_name=True)


class SecurityEventListResponse(SQLModel):
    """Response for listing security events"""
    events: list[SecurityEventPublic]
    total: int


class SecurityStats(SQLModel):
    """Schema for security statistics"""
    securityScore: int
    activeThreats: int
    blockedAttacks: int
    activeMonitoring: int
    scoreTrend: str # 'up' | 'down' | 'stable'
    threatsTrend: str
    blockedTrend: str
    monitoringTrend: str
    # Session monitoring metrics
    activeSessions: int
    failedLogins24h: int
    suspiciousPatterns: int
    # Analytics card metrics
    highPriority: int
    apiAbuseAttempts: int
    fraudIncidents: int
    # Security control configuration
    securityConfig: dict  # Contains mfaEnforced, sessionTimeoutMins, passwordStrength, ipAllowlistEnabled
    policySnapshot: dict  # Contains mfaStatus, apiAbuseProtection, geoRestrictions, rateLimitPolicy



class SecurityEventAction(SQLModel):
    action: str 
    reason: str | None = None


class ApiKeyAction(SQLModel):
    action: str
    reason: str | None = None


class SecurityActionResponse(SQLModel):
    success: bool
    message: str


class AdminActionRequest(SQLModel):
    userId: uuid.UUID
    action: str
    reason: str


class SecurityApiKeyPublic(SQLModel):
    id: uuid.UUID
    keyName: str = Field(alias="name")
    keyPrefix: str = Field(alias="key_prefix")
    owner: str 
    ownerId: uuid.UUID = Field(alias="user_id")
    lastUsed: str | None = None
    requestCount: int = Field(alias="total_requests")
    status: str 
    abuseScore: int = Field(alias="abuse_score")
    dailyLimit: int = 1000 

    model_config = ConfigDict(populate_by_name=True)


class SecurityApiKeyListResponse(SQLModel):
    keys: list[SecurityApiKeyPublic]
    total: int


# --- Audit Log Models ---

class AuditLog(SQLModel, table=True):
    """Immutable record of all critical actions across the platform."""
    __tablename__ = "audit_log"
    
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    
    # Actor details
    actor_id: uuid.UUID | None = Field(default=None, foreign_key="user.id", ondelete="SET NULL", index=True)
    actor_name: str | None = Field(default=None, max_length=255)
    actor_role: str | None = Field(default=None, max_length=100)
    actor_type: str = Field(default="human", max_length=50) # human, system, automation
    
    # Action details
    action: str = Field(index=True, max_length=100) # e.g. ROLE_UPDATED, CREDITS_ALLOCATED
    action_category: str | None = Field(default=None, max_length=100) # e.g. access_control, financial, system
    
    # Target details
    target_id: str | None = Field(default=None, max_length=255, index=True)
    target_type: str | None = Field(default=None, max_length=100) # User, Org, API Key, Treasury, Role
    
    # Context
    organization_id: uuid.UUID | None = Field(default=None, index=True)
    workspace_id: uuid.UUID | None = Field(default=None, index=True)
    
    # Network details
    ip_address: str | None = Field(default=None, max_length=50)
    location: str | None = Field(default=None, max_length=255)
    user_agent: str | None = Field(default=None, max_length=500)
    
    # Result
    severity: str = Field(default="low", max_length=20) # low, medium, high, critical
    status: str = Field(default="success", max_length=20) # success, failed, partially_completed
    
    # Metadata (Extended details)
    meta_data: dict = Field(default_factory=dict, sa_column=Column(JSON)) # full metadata, before/after, etc.
    correlation_id: str | None = Field(default=None, max_length=100, index=True)
    request_source: str = Field(default="ui", max_length=50) # ui, api, job
    auth_method: str | None = Field(default=None, max_length=50) # password, sso, token

from pydantic import Field as PydanticField

class AuditLogPublic(SQLModel):
    id: uuid.UUID
    timestamp: datetime
    actorName: str | None = PydanticField(default=None, validation_alias="actor_name")
    actorRole: str | None = PydanticField(default=None, validation_alias="actor_role")
    actorType: str = PydanticField(default="human", validation_alias="actor_type")
    action: str
    targetType: str | None = PydanticField(default=None, validation_alias="target_type")
    targetId: str | None = PydanticField(default=None, validation_alias="target_id")
    ipAddress: str | None = PydanticField(default=None, validation_alias="ip_address")
    location: str | None = PydanticField(default=None, validation_alias="location")
    severity: str = "low"
    status: str = "success"
    organizationId: uuid.UUID | None = PydanticField(default=None, validation_alias="organization_id")
    metaData: dict | None = PydanticField(default=None, validation_alias="meta_data")
    authMethod: str | None = PydanticField(default=None, validation_alias="auth_method")
    requestSource: str = PydanticField(default="ui", validation_alias="request_source")
    correlationId: str | None = PydanticField(default=None, validation_alias="correlation_id")
    
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

class AuditLogListResponse(SQLModel):
    logs: list[AuditLogPublic]
    total: int

class AuditLogStats(SQLModel):
    totalEvents: int
    criticalActions: int
    adminActions: int
    securitySensitive: int
    failedActions: int


# ==================== Platform Settings Model ====================

class PlatformSettings(SQLModel, table=True):
    """
    Singleton table for global platform configuration.
    Uses JSON columns for flexible storage of section-specific settings.
    """
    __tablename__ = "platform_settings"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    
    # Sections as JSON columns
    general: dict = Field(default_factory=dict, sa_column=Column(JSON))
    notifications: dict = Field(default_factory=dict, sa_column=Column(JSON))
    payments: dict = Field(default_factory=dict, sa_column=Column(JSON))
    gateways: dict = Field(default_factory=dict, sa_column=Column(JSON))
    email: dict = Field(default_factory=dict, sa_column=Column(JSON))
    security: dict = Field(default_factory=dict, sa_column=Column(JSON))
    rate_limiting: dict = Field(default_factory=dict, sa_column=Column(JSON))
    integrations: dict = Field(default_factory=dict, sa_column=Column(JSON))
    compliance: dict = Field(default_factory=dict, sa_column=Column(JSON))
    
    # Metadata
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_by: uuid.UUID | None = Field(default=None, foreign_key="user.id", nullable=True, ondelete="SET NULL")

class PlatformSettingsPublic(SQLModel):
    """Public schema for platform settings"""
    general: dict
    notifications: dict
    payments: dict
    gateways: dict
    email: dict
    security: dict
    rateLimiting: dict = Field(alias="rate_limiting")
    integrations: dict
    compliance: dict
    updatedAt: datetime = Field(alias="updated_at")

    model_config = ConfigDict(populate_by_name=True)

class PlatformSettingsUpdate(SQLModel):
    """Schema for updating platform settings"""
    general: dict | None = None
    notifications: dict | None = None
    payments: dict | None = None
    gateways: dict | None = None
    email: dict | None = None
    security: dict | None = None
    rateLimiting: dict | None = Field(default=None, alias="rate_limiting")
    integrations: dict | None = None
    compliance: dict | None = None

    model_config = ConfigDict(populate_by_name=True)

# ==================== Help Center Models ====================

class HelpCategoryBase(SQLModel):
    title: str = Field(max_length=100)
    description: str = Field(max_length=500)
    icon: str = Field(max_length=50) # Lucide icon name
    color: str = Field(max_length=50) # Tailwind text color class
    bg_color: str = Field(max_length=50, alias="bgColor") # Tailwind bg color class
    order: int = Field(default=0)

    model_config = ConfigDict(populate_by_name=True)

class HelpCategory(HelpCategoryBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    articles: list["HelpArticle"] = Relationship(back_populates="category", cascade_delete=True)

class HelpArticleBase(SQLModel):
    title: str = Field(max_length=255)
    content: str | None = Field(default=None)
    order: int = Field(default=0)
    category_id: uuid.UUID = Field(foreign_key="helpcategory.id")

class HelpArticle(HelpArticleBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    category: HelpCategory = Relationship(back_populates="articles")

class HelpFAQBase(SQLModel):
    question: str = Field(max_length=255)
    answer: str = Field(max_length=500)
    order: int = Field(default=0)

class HelpFAQ(HelpFAQBase, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)

class HelpCategoryPublic(HelpCategoryBase):
    id: uuid.UUID
    articles: list["HelpArticlePublic"] = []

    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

class HelpArticlePublic(HelpArticleBase):
    id: uuid.UUID
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

class HelpFAQPublic(HelpFAQBase):
    id: uuid.UUID
    model_config = ConfigDict(populate_by_name=True, from_attributes=True)

class HelpCenterResponse(SQLModel):
    categories: list[HelpCategoryPublic]
    faqs: list[HelpFAQPublic]
