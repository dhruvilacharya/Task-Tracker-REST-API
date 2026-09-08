"""
UserRepository — thin async wrappers around SQLAlchemy queries for users.

Rules for this layer:
  - No business logic, no HTTP concerns, no FastAPI imports.
  - No password hashing here — the service layer hashes before calling create.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import User


class UserRepository:
    """All database interactions for the users table."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_email(self, email: str) -> User | None:
        """Return the User ORM object for the given email, or None."""
        result = await self._db.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        """Return the User ORM object for the given id, or None."""
        result = await self._db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def create(self, *, email: str, hashed_password: str) -> User:
        """
        Insert a new user with an already-hashed password.

        Returns the persisted User (with id populated).
        """
        user = User(email=email, hashed_password=hashed_password, is_active=True)
        self._db.add(user)
        await self._db.flush()
        await self._db.refresh(user)
        return user
