"""
Pydantic schemas for authentication and user management.
"""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class UserCreate(BaseModel):
    """Request body for POST /auth/register."""

    email: EmailStr
    password: str = Field(min_length=8, description="Minimum 8 characters")


class UserOut(BaseModel):
    """Public user representation — never exposes hashed_password."""

    id: int
    email: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class Token(BaseModel):
    """Response body for POST /auth/login."""

    access_token: str
    token_type: str = "bearer"


class TokenData(BaseModel):
    """Decoded payload extracted from a validated JWT."""

    user_id: int
