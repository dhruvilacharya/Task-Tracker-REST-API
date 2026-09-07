"""
TaskService — business logic layer for tasks.

Rules for this layer:
  - No SQL / SQLAlchemy imports — all DB work goes through TaskRepository.
  - Translates repository sentinels into HTTPExceptions so the router stays
    thin (HTTP status codes only, zero business logic).
  - Accepts a TaskRepository instance (constructor injection) so unit tests
    can swap in a mock without touching the DB.
  - Future home for: status-transition state machine (Phase 5), audit
    dispatch (Phase 6), and any other cross-cutting task logic.
"""

from datetime import date

from fastapi import HTTPException
from fastapi import status as http_status

from app.repositories.task_repository import (
    NOT_FOUND,
    VERSION_CONFLICT,
    TaskRepository,
)


class TaskService:
    """
    Orchestrates task operations.

    Instantiate with a TaskRepository; call methods to perform operations.
    All methods raise HTTPException on error so the router never needs to
    inspect return values for sentinel strings.
    """

    def __init__(self, repo: TaskRepository) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_task(self, task_id: int) -> dict:
        """
        Return a task by id.

        Raises 404 if not found.
        """
        row = await self._repo.get_by_id(task_id)
        if row is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found",
            )
        return row

    async def list_tasks(
        self,
        *,
        status: str | None = None,
        due_before: date | None = None,
        due_after: date | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[dict]:
        """
        Return all tasks matching the given filters in the requested order.

        The repository handles whitelist validation for sort params; any
        ValueError it raises becomes a 422 here (FastAPI will not reach
        this path for invalid Literal values — it 422s before the handler
        runs — so this is a defensive belt-and-suspenders guard).
        """
        try:
            return await self._repo.get_all(
                status=status,
                due_before=due_before,
                due_after=due_after,
                sort_by=sort_by,
                sort_order=sort_order,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(exc),
            ) from exc

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_task(self, data: dict) -> dict:
        """Create and return a new task."""
        return await self._repo.create(data)

    async def update_task(
        self,
        task_id: int,
        data: dict,
        version: int,
    ) -> dict:
        """
        Apply an optimistic-locking update.

        Raises 404 if the task doesn't exist, 409 on a version conflict.
        """
        result = await self._repo.update_raw(task_id, data, version)

        if result == NOT_FOUND:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found",
            )
        if result == VERSION_CONFLICT:
            raise HTTPException(
                status_code=http_status.HTTP_409_CONFLICT,
                detail="version mismatch, re-fetch and retry",
            )
        return result  # type: ignore[return-value]  # dict at this point

    async def delete_task(self, task_id: int) -> None:
        """
        Delete a task by id.

        Raises 404 if the task doesn't exist.
        """
        row = await self._repo.get_by_id(task_id)
        if row is None:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=f"Task with id {task_id} not found",
            )
        await self._repo.delete(task_id)
