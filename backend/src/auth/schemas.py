"""Pydantic schemas for authentication."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr


class UserBase(BaseModel):
    email: EmailStr
    full_name: str
    phone: str | None = None
    job_title: str | None = None


class UserCreate(UserBase):
    password: str


class UserUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    job_title: str | None = None
    avatar_url: str | None = None


class UserResponse(UserBase):
    id: int
    is_active: bool
    is_superuser: bool
    avatar_url: str | None = None
    role: str = "sales_rep"
    created_at: datetime
    last_login: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class TenantInfo(BaseModel):
    """Tenant information included in login response."""
    tenant_id: int
    tenant_slug: str
    company_name: str | None = None
    role: str
    is_primary: bool = False
    primary_color: str | None = None
    secondary_color: str | None = None
    accent_color: str | None = None
    logo_url: str | None = None


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    tenants: list | None = None


class TokenData(BaseModel):
    user_id: int | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleAuthorizeRequest(BaseModel):
    """Client sends the redirect_uri it will be returning to."""
    redirect_uri: str


class GoogleAuthorizeResponse(BaseModel):
    auth_url: str
    state: str


class GoogleCallbackRequest(BaseModel):
    code: str
    redirect_uri: str
    state: str | None = None
