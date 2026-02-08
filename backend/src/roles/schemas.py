"""Pydantic schemas for RBAC."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict


class RoleBase(BaseModel):
    name: str
    description: Optional[str] = None
    permissions: Optional[dict] = None


class RoleCreate(RoleBase):
    pass


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[dict] = None


class RoleResponse(RoleBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserRoleAssign(BaseModel):
    user_id: int
    role_id: int


class UserRoleResponse(BaseModel):
    id: int
    user_id: int
    role_id: int
    role: RoleResponse
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
