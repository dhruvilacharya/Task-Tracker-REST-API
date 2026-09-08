"""
Security primitives — password hashing and JWT encode/decode.

Stateless helpers with no DB or HTTP dependencies. Kept separate from
AuthService so they can be reused (e.g. in tests) and unit-tested easily.
"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt

from app.config import settings

# bcrypt operates on the first 72 bytes of the input. We pre-hash longer
# passwords with SHA-256 is overkill here; instead we simply cap the byte
# length, which is the documented bcrypt behavior.
_BCRYPT_MAX_BYTES = 72


# ---------------------------------------------------------------------------
# Password hashing (bcrypt directly — no passlib)
# ---------------------------------------------------------------------------

def _to_bcrypt_bytes(plain: str) -> bytes:
    """Encode to UTF-8 and truncate to bcrypt's 72-byte limit."""
    return plain.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(plain: str) -> str:
    hashed = bcrypt.hashpw(_to_bcrypt_bytes(plain), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(_to_bcrypt_bytes(plain), hashed.encode("utf-8"))
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# JWT
# ---------------------------------------------------------------------------

def create_access_token(
    *,
    subject: int,
    expires_minutes: int | None = None,
) -> str:
    """
    Create a signed JWT whose `sub` claim is the user id.

    `exp` defaults to settings.ACCESS_TOKEN_EXPIRE_MINUTES from now.
    """
    minutes = (
        expires_minutes
        if expires_minutes is not None
        else settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    expire = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> int | None:
    """
    Decode and validate a JWT.

    Returns the user id (from `sub`) on success, or None if the token is
    invalid, expired, or malformed.
    """
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
        )
    except JWTError:
        return None

    sub = payload.get("sub")
    if sub is None:
        return None
    try:
        return int(sub)
    except (TypeError, ValueError):
        return None
