"""
FastAPI dependency factories.

Centralises dependency wiring so routers stay free of construction logic.
Each factory is a single function that FastAPI resolves via Depends().
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.repositories.task_repository import TaskRepository
from app.services.task_service import TaskService


def get_task_service(db: AsyncSession = Depends(get_db)) -> TaskService:  # noqa: B008
    """Wire db → TaskRepository → TaskService for injection into routers."""
    return TaskService(TaskRepository(db))
