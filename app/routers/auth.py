"""
Auth router — registration and login.

  POST /auth/register → create a user, return UserOut
  POST /auth/login    → verify credentials, return a JWT (Token)

/login uses the OAuth2 password form (username + password fields) so it
works with Swagger's built-in "Authorize" button. The `username` field
carries the email.
"""

from fastapi import APIRouter, Depends
from fastapi import status as http_status
from fastapi.security import OAuth2PasswordRequestForm

from app.dependencies import get_auth_service
from app.schemas.auth import Token, UserCreate, UserOut
from app.services.auth_service import AuthService

router = APIRouter()


@router.post(
    "/register",
    status_code=http_status.HTTP_201_CREATED,
    response_model=UserOut,
)
async def register(
    payload: UserCreate,
    auth_svc: AuthService = Depends(get_auth_service),
) -> UserOut:
    user = await auth_svc.register(payload.email, payload.password)
    return UserOut.model_validate(user)


@router.post("/login", response_model=Token)
async def login(
    form: OAuth2PasswordRequestForm = Depends(),
    auth_svc: AuthService = Depends(get_auth_service),
) -> Token:
    # OAuth2 form uses `username`; we treat it as the email
    access_token = await auth_svc.login(form.username, form.password)
    return Token(access_token=access_token)
