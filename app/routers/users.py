"""
Users router — current-user info.

  GET /users/me → the authenticated user's profile (UserOut)
"""

from fastapi import APIRouter, Depends

from app.dependencies import get_current_user
from app.models.orm import User
from app.schemas.auth import UserOut

router = APIRouter()


@router.get("/me", response_model=UserOut)
async def read_current_user(
    current_user: User = Depends(get_current_user),
) -> UserOut:
    return UserOut.model_validate(current_user)
