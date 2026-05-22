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
    # Profile fields for user settings
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
    graduation_year: str | None = Field(default=None, max_length=4)
    profession: str | None = Field(default=None, max_length=255)
    membership_id: str | None = Field(default=None, max_length=50, unique=True, index=True)
    nickname: str | None = Field(default=None, max_length=150)
    alternative_email: str | None = Field(default=None, max_length=255)
    gender: str | None = Field(default=None, max_length=50)
    fgce_set: str | None = Field(default=None, max_length=50)
    fgce_house: str | None = Field(default=None, max_length=150)


    model_config = ConfigDict(populate_by_name=True)


# Properties to receive via API on creation
class UserCreate(UserBase):
    password: str | None = Field(default=None, min_length=8, max_length=128)
    role: str | None = None
    roles: list[str] | None = None


class UserRegister(SQLModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(min_length=8, max_length=128)
    first_name: str = Field(max_length=150)
    last_name: str = Field(max_length=150)
    nickname: str | None = Field(default=None, max_length=150)
    alternative_email: str | None = Field(default=None, max_length=255)
    phone_number: str | None = Field(default=None, max_length=50)
    gender: str = Field(max_length=50)
    fgce_set: str = Field(max_length=50)
    fgce_house: str = Field(max_length=150)
    city: str = Field(max_length=255)
    country: str = Field(max_length=255)
    username: str | None = Field(default=None, max_length=150)
    accept_terms: bool = Field(description="User must accept terms and conditions")
    graduation_year: str | None = Field(default=None, max_length=4)
    profession: str | None = Field(default=None, max_length=255)
    account_type: str | None = Field(default="individual", max_length=50)
    organization_name: str | None = Field(default=None, max_length=255)
    invitation_token: str | None = Field(default=None, max_length=300)


# Properties to receive via API on update, all are optional
class UserUpdate(UserBase):
    email: EmailStr | None = Field(default=None, max_length=255)  # type: ignore
    password: str | None = Field(default=None, min_length=8, max_length=128)
    is_active: bool | None = None
    status: str | None = None
    role: str | None = None
    roles: list[str] | None = None
    graduation_year: str | None = Field(default=None, max_length=4)
    profession: str | None = Field(default=None, max_length=255)
    membership_id: str | None = Field(default=None, max_length=50)


class UserIdentityRoleUpdate(SQLModel):
    identityRole: str = Field(..., description="The new identity role name (e.g. super_admin)")

    model_config = ConfigDict(populate_by_name=True)


class UserUpdateMe(SQLModel):
    # Accept camelCase from frontend
    firstName: str | None = Field(default=None, max_length=150)
    lastName: str | None = Field(default=None, max_length=150)
    email: EmailStr | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    nickname: str | None = Field(default=None, max_length=150)
    alternativeEmail: str | None = Field(default=None, max_length=255)
    gender: str | None = Field(default=None, max_length=50)
    fgceSet: str | None = Field(default=None, max_length=50)
    fgceHouse: str | None = Field(default=None, max_length=150)
    city: str | None = Field(default=None, max_length=255)
    country: str | None = Field(default=None, max_length=255)
    password: str | None = Field(default=None, min_length=8, max_length=128)

    def to_db_dict(self) -> dict:
        """Convert camelCase fields to snake_case for database"""
        data = {}
        if self.firstName is not None:
            data['first_name'] = self.firstName
        if self.lastName is not None:
            data['last_name'] = self.lastName
        if self.email is not None:
            data['email'] = self.email
        if self.phone is not None:
            data['phone'] = self.phone or self.phone # Handle both phone/phone_number aliases if needed
            data['phone_number'] = self.phone
        if self.nickname is not None:
            data['nickname'] = self.nickname
        if self.alternativeEmail is not None:
            data['alternative_email'] = self.alternativeEmail
        if self.gender is not None:
            data['gender'] = self.gender
        if self.fgceSet is not None:
            data['fgce_set'] = self.fgceSet
        if self.fgceHouse is not None:
            data['fgce_house'] = self.fgceHouse
        if self.city is not None:
            data['city'] = self.city
        if self.country is not None:
            data['country'] = self.country
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
    # Credits removed from public view for now if not used, but keeping in DB for potential future dues balance
    credits: Decimal = Field(default=Decimal("0.0000"), max_digits=12, decimal_places=4)
    status: str = Field(default="active", max_length=20, description="User status: active, pending, disabled")
    last_login: datetime | None = Field(default=None, description="Timestamp of the last login")
    accepted_terms_at: datetime | None = Field(default=None, description="Timestamp when user accepted terms and conditions")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_verified: bool = Field(default=False, description="Whether the user email has been verified")
    user_roles: list["UserRole"] = Relationship(back_populates="user", cascade_delete=True)
    payments: list["Payment"] = Relationship(back_populates="user", cascade_delete=True)


# Properties to return via API, id is always required
class UserPublic(SQLModel):
    id: uuid.UUID
    email: EmailStr
    firstName: str | None = None
    lastName: str | None = None
    name: str | None = None
    nickname: str | None = None
    gender: str | None = None
    alternativeEmail: str | None = None
    fgceSet: str | None = None
    fgceHouse: str | None = None
    phone: str | None = None
    city: str | None = None
    country: str | None = None
    avatar: str | None = None
    createdAt: datetime | None = None
    updatedAt: datetime | None = None
    role: str | None = None
    status: str | None = None
    timezone: str | None = None
    isVerified: bool = Field(default=False, alias="is_verified")
    authProvider: str | None = "password"
    lastOnline: datetime | None = None
    accountType: str | None = "individual"
    roles: list[str] = []
    permissions: list[str] = []
    dues: str | None = None

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
        role = "member"
        if user_role_names:
            if "super_admin" in user_role_names:
                role = "super_admin"
            elif "admin" in user_role_names:
                role = "admin"
            else:
                role = user_role_names[0]
        elif getattr(user, "is_superuser", False):
            role = "admin"
        
        # Use last_login if available, fallback to updated_at
        last_online = getattr(user, "last_login", None)
        if not last_online:
            last_online = user.updated_at
        
        return cls(
            id=user.id,
            email=user.email,
            firstName=user.first_name,
            lastName=user.last_name,
            name=user.full_name or f"{user.first_name or ''} {user.last_name or ''}".strip() or "User",
            nickname=getattr(user, "nickname", None),
            gender=getattr(user, "gender", None),
            alternativeEmail=getattr(user, "alternative_email", None),
            fgceSet=getattr(user, "fgce_set", None),
            fgceHouse=getattr(user, "fgce_house", None),
            phone=user.phone,
            city=getattr(user, "city", None),
            country=getattr(user, "country", None),
            avatar=user.avatar,
            createdAt=user.created_at,
            updatedAt=user.updated_at,
            role=role,
            status=status,
            timezone=user.timezone,
            isVerified=user.is_verified,
            authProvider=getattr(user, "auth_provider", "password"),
            lastOnline=last_online,
            accountType=getattr(user, "account_type", "individual"),
            roles=user_role_names,
            permissions=user_permissions,
            dues=None # Calculated later in endpoints
        )


class UsersPublic(SQLModel):
    data: list[UserPublic]
    count: int


# RBAC Models
class Role(SQLModel, table=True):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    name: str = Field(max_length=50, index=True)
    description: str | None = Field(default=None, max_length=255)
    user_roles: list["UserRole"] = Relationship(back_populates="role", cascade_delete=True)
    role_permissions: list["RolePermission"] = Relationship(back_populates="role", cascade_delete=True)


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



# FGCEOSA MODELS

class Payment(SQLModel, table=True):
    __tablename__ = "payment"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    status: str = Field(default="pending", max_length=30) # completed, pending, pending_verification, rejected, failed
    transaction_reference: str = Field(max_length=255, unique=True, index=True)
    amount: Decimal = Field(default=Decimal("0.00"), max_digits=10, decimal_places=2)
    currency: str = Field(default="NGN", max_length=10)
    payment_method: str | None = Field(default=None, max_length=50)
    paystack_id: str | None = Field(default=None, max_length=255, index=True)
    description: str | None = Field(default=None, max_length=500)
    receipt_url: str | None = Field(default=None, max_length=1000)
    rejection_reason: str | None = Field(default=None, sa_column=sa.Column(sa.TEXT))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    user: "User" = Relationship(back_populates="payments")

class PaymentBase(SQLModel):
    amount: Decimal
    currency: str = "NGN"
    description: str | None = None

class PaymentCreate(PaymentBase):
    pass

class PaymentPublic(PaymentBase):
    id: uuid.UUID
    user_id: uuid.UUID
    status: str
    transaction_reference: str
    payment_method: str | None
    receipt_url: str | None = None
    rejection_reason: str | None = None
    created_at: datetime
    updated_at: datetime
    user: UserPublic | None = None

class PaymentsPublic(SQLModel):
    data: list[PaymentPublic]
    count: int

class Announcement(SQLModel, table=True):
    __tablename__ = "announcement"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    content: str
    category: str = Field(default="General", max_length=100)
    status: str = Field(default="Sent", max_length=50) # Sent, Draft, Scheduled
    priority: str = Field(default="Normal", max_length=50) # Normal, High, Urgent
    views: int = Field(default=0)
    engagement: int = Field(default=0)
    image: str | None = Field(default=None, sa_column=sa.Column(sa.TEXT))
    is_important: bool = Field(default=False)
    is_pinned: bool = Field(default=False)
    scheduled_at: datetime | None = Field(default=None)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)
    created_by_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")

class AnnouncementView(SQLModel, table=True):
    __tablename__ = "announcement_view"
    announcement_id: uuid.UUID = Field(foreign_key="announcement.id", primary_key=True, ondelete="CASCADE")
    user_id: uuid.UUID = Field(foreign_key="user.id", primary_key=True, ondelete="CASCADE")
    viewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Event(SQLModel, table=True):
    __tablename__ = "event"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    description: str
    date: datetime
    time: str = Field(default="12:00 PM", max_length=50)
    location: str | None = Field(default=None, max_length=500)
    status: str = Field(default="Upcoming", max_length=50) # Upcoming, Active, Past
    image: str | None = Field(default=None, sa_column=sa.Column(sa.TEXT))
    total_registered: int = Field(default=0)
    capacity: int = Field(default=100)
    category: str = Field(default="General", max_length=100)
    is_online: bool = Field(default=False)
    meeting_link: str | None = Field(default=None, max_length=1000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE")
    
    registrations: list["EventRegistration"] = Relationship(back_populates="event", cascade_delete=True)


class EventRegistration(SQLModel, table=True):
    __tablename__ = "event_registration"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    event_id: uuid.UUID = Field(foreign_key="event.id", nullable=False, ondelete="CASCADE", index=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    registration_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str | None = Field(default=None, max_length=500)
    attendees_count: int = Field(default=1)
    status: str = Field(default="confirmed", max_length=50) # confirmed, cancelled
    
    event: "Event" = Relationship(back_populates="registrations")
    user: "User" = Relationship()

class EventRegistrationCreate(SQLModel):
    event_id: uuid.UUID | None = None
    notes: str | None = None
    attendees_count: int = 1

class EventRegistrationPublic(SQLModel):
    id: uuid.UUID
    event_id: uuid.UUID
    user_id: uuid.UUID
    registration_date: datetime
    notes: str | None
    attendees_count: int = 1
    status: str
    user: Optional[UserPublic] = None


class SystemSettings(SQLModel, table=True):
    __tablename__ = "system_settings"
    id: int = Field(default=1, primary_key=True)
    association_name: str = Field(default="FGCEOSA", max_length=255)
    association_logo: str | None = Field(default=None, sa_column=sa.Column(sa.TEXT))
    contact_email: str = Field(default="admin@fgceosa.org", max_length=255)
    contact_phone: str = Field(default="+234 800 000 0000", max_length=50)
    address: str | None = Field(default="Federal Government College, Independence Layout, Enugu, Nigeria.", max_length=500)
    
    # Billing & Identity
    currency: str = Field(default="NGN", max_length=10)
    payment_enabled: bool = Field(default=True)
    paystack_public_key: str | None = Field(default=None, max_length=255)
    paystack_secret_key: str | None = Field(default=None, max_length=255)
    
    # Invoice Config
    tax_percentage: Decimal = Field(default=Decimal("0.00"), max_digits=5, decimal_places=2)
    invoice_footer_note: str | None = Field(default="Thank you for your tireless support of the FGCEOSA community.", max_length=500)
    
    # Preferences
    default_member_status: str = Field(default="active", max_length=20)
    allow_self_registration: bool = Field(default=True)
    enable_email_notifications: bool = Field(default=True)
    timezone: str = Field(default="WAT", max_length=100)
    date_format: str = Field(default="DD/MM/YYYY", max_length=50)
    
    # Bank Details
    bank_name: str | None = Field(default=None, max_length=255)
    account_number: str | None = Field(default=None, max_length=50)
    account_name: str | None = Field(default=None, max_length=255)
    
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SystemSettingsUpdate(SQLModel):
    association_name: str | None = None
    association_logo: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    currency: str | None = None
    payment_enabled: bool | None = None
    paystack_public_key: str | None = None
    paystack_secret_key: str | None = None
    tax_percentage: Decimal | None = None
    invoice_footer_note: str | None = None
    default_member_status: str | None = None
    allow_self_registration: bool | None = None
    enable_email_notifications: bool | None = None
    timezone: str | None = None
    date_format: str | None = None
    bank_name: str | None = None
    account_number: str | None = None
    account_name: str | None = None

class SystemSettingsPublic(SQLModel):
    association_name: str
    association_logo: str | None
    contact_email: str
    contact_phone: str
    address: str | None
    currency: str
    payment_enabled: bool
    paystack_public_key: str | None = None
    paystack_secret_key: str | None = None
    tax_percentage: Decimal
    invoice_footer_note: str | None
    default_member_status: str
    allow_self_registration: bool
    enable_email_notifications: bool
    timezone: str
    date_format: str
    bank_name: str | None
    account_number: str | None
    account_name: str | None


class Due(SQLModel, table=True):
    __tablename__ = "due"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    title: str = Field(max_length=255)
    amount: Decimal = Field(max_digits=12, decimal_places=2)
    due_date: datetime
    description: str | None = Field(default=None, max_length=1000)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DueCreate(SQLModel):
    title: str = Field(max_length=255)
    amount: Decimal
    due_date: datetime
    description: str | None = None
    is_active: bool = True

class DueUpdate(SQLModel):
    title: str | None = None
    amount: Decimal | None = None
    due_date: datetime | None = None
    description: str | None = None
    is_active: bool | None = None

class DuePublic(SQLModel):
    id: uuid.UUID
    title: str
    amount: Decimal
    due_date: datetime
    description: str | None
    is_active: bool
    created_at: datetime


class Notification(SQLModel, table=True):
    __tablename__ = "notification"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    user_id: uuid.UUID = Field(foreign_key="user.id", nullable=False, ondelete="CASCADE", index=True)
    title: str = Field(max_length=255)
    description: str = Field(max_length=1000)
    type: str = Field(default="info", max_length=50) # info, success, warning, danger
    is_read: bool = Field(default=False, index=True)
    metadata_json: dict | None = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), index=True)

class NotificationPublic(SQLModel):
    id: uuid.UUID
    user_id: uuid.UUID
    title: str
    description: str
    type: str
    is_read: bool
    metadata_json: dict | None
    created_at: datetime

class NotificationsPublic(SQLModel):
    data: list[NotificationPublic]
    count: int
    unreadCount: int
