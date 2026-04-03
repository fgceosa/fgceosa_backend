"""
Pydantic schemas for Roles and Permissions API
"""
from uuid import UUID
from pydantic import BaseModel, Field
from typing import Optional


class PermissionBase(BaseModel):
    """Base permission schema"""
    name: str = Field(..., max_length=100)
    description: Optional[str] = Field(None, max_length=255)


class PermissionCreate(PermissionBase):
    """Schema for creating a permission"""
    pass


class PermissionPublic(PermissionBase):
    """Public permission schema"""
    id: UUID
    enabled: bool = False  # Will be set based on role context
    isSensitive: bool = False

    class Config:
        from_attributes = True


class PermissionGroupPublic(BaseModel):
    """Permission group for frontend"""
    id: str
    category: str
    permissions: list[PermissionPublic]


class RoleBase(BaseModel):
    """Base role schema"""
    name: str = Field(..., max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field(None, max_length=50)


class RoleCreate(RoleBase):
    """Schema for creating a role"""
    permissions: list[UUID] = Field(default_factory=list, description="List of permission IDs to assign")


class RoleUpdate(BaseModel):
    """Schema for updating a role"""
    name: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    icon: Optional[str] = Field(None, max_length=50)
    permissions: Optional[list[UUID]] = Field(None, description="List of permission IDs to assign")


class RolePublic(RoleBase):
    """Public role schema"""
    id: UUID
    userCount: int = 0
    permissions: list[PermissionGroupPublic]
    isSystem: bool = False

    class Config:
        from_attributes = True


class RolesListPublic(BaseModel):
    """List of roles response"""
    data: list[RolePublic]
    total: int


class RolePermissionUpdate(BaseModel):
    """Schema for updating role permissions"""
    permission_ids: list[UUID] = Field(..., description="List of permission IDs to assign to role")


class OrganizationRoleCreate(RoleBase):
    """Schema for creating an organization role (permissions by name)"""
    permissions: list[str] = Field(default_factory=list, description="List of permission names to assign")


class OrganizationRoleUpdate(BaseModel):
    """Schema for updating an organization role"""
    name: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = Field(None, max_length=255)
    permissions: Optional[list[str]] = Field(None, description="List of permission names to assign")


class OrganizationRolePublic(RoleBase):
    """Public organization role schema with flattened permissions"""
    id: UUID
    userCount: int = 0
    permissions: list[str] = Field(default_factory=list)
    isSystem: bool = False
