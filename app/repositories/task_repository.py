"""
TaskRepository — thin async wrappers around SQLAlchemy queries.

Rules for this layer:
  - No business logic, no HTTP concerns, no FastAPI imports.
  - Every method accepts an AsyncSession injected by the caller.
  - Sentinel values NOT_FOUND / VERSION_CONFLICT signal DB-level outcomes
    (row missing vs version mismatch) back to the service layer.
  - Filter / sort params are validated against whitelists before touching SQL
    so injection is impossible even if callers pass user-supplied strings.
"""

from datetime import date, datetime, timezone

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.orm import Task

# ---------------------------------------------------------------------------
# Sentinel return values
# ---------------------------------------------------------------------------
NOT_FOUND = "NOT_FOUND"
VERSION_CONFLICT = "VERSION_CONFLICT"

# ---------------------------------------------------------------------------
# Safe allowlists for dynamic ORDER BY (SQL injection guard)
# ---------------------------------------------------------------------------
SORT_COLUMNS: dict[str, str] = {
    "created_at": "created_at",
    "due_date": "due_date",
    "title": "title",
}
SORT_ORDERS: dict[str, str] = {
    "asc": "asc",
    "desc": "desc",
}

# Columns that may appear in an UPDATE payload
_UPDATABLE_COLUMNS = frozenset({"title", "description", "status", "due_date"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _to_str(value) -> str | None:
    """Coerce date / Enum values to their plain string form for storage."""
    if value is None:
        return None
    if hasattr(value, "value"):               # str-Enum (.value is already str)
        return value.value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


# ---------------------------------------------------------------------------
# TaskRepository
# ---------------------------------------------------------------------------

class TaskRepository:
    """
    All database interactions for the tasks table.

    Instantiate with an AsyncSession; the session lifecycle (commit / rollback)
    is managed by the ``get_db`` dependency in database.py — the repository
    never commits or rolls back directly.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, task_id: int) -> dict | None:
        """Return the task as a dict, or None if it doesn't exist."""
        result = await self._db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        return task.to_dict() if task is not None else None

    async def get_all(
        self,
        *,
        status: str | None = None,
        due_before: date | None = None,
        due_after: date | None = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> list[dict]:
        """
        Return all tasks matching the given filters, in the requested order.

        sort_by and sort_order are validated against whitelists — unknown
        values raise ValueError before any SQL is constructed.
        """
        column_name = SORT_COLUMNS.get(sort_by)
        if column_name is None:
            raise ValueError(f"invalid sort_by: {sort_by!r}")
        if sort_order not in SORT_ORDERS:
            raise ValueError(f"invalid sort_order: {sort_order!r}")

        stmt = select(Task)

        if status is not None:
            stmt = stmt.where(Task.status == _to_str(status))
        if due_before is not None:
            # due_date stored as TEXT "YYYY-MM-DD"; lexicographic ≤ works correctly
            stmt = stmt.where(Task.due_date <= due_before.isoformat())
        if due_after is not None:
            stmt = stmt.where(Task.due_date >= due_after.isoformat())

        col = getattr(Task, column_name)
        stmt = stmt.order_by(col.asc() if sort_order == "asc" else col.desc())

        result = await self._db.execute(stmt)
        return [row.to_dict() for row in result.scalars().all()]

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(self, data: dict) -> dict:
        """Insert a new task and return the persisted row as a dict."""
        now = _utcnow()
        task = Task(
            title=data["title"],
            description=data.get("description"),
            status="pending",
            due_date=_to_str(data.get("due_date")),
            created_at=now,
            updated_at=now,
            version=1,
        )
        self._db.add(task)
        await self._db.flush()       # materialise the auto-generated id
        await self._db.refresh(task) # reload all server-generated columns
        return task.to_dict()

    async def update_raw(
        self,
        task_id: int,
        data: dict,
        version: int,
    ) -> dict | str:
        """
        Optimistic-locking UPDATE.

        Only columns in _UPDATABLE_COLUMNS that are present in *data* are
        changed.  version is always incremented; updated_at is always set.

        Returns:
          - updated task dict on success
          - NOT_FOUND  if no row with task_id exists
          - VERSION_CONFLICT if the row exists but its version != *version*
        """
        now = _utcnow()

        values: dict = {
            "updated_at": now,
            "version": Task.version + 1,
        }
        for col in _UPDATABLE_COLUMNS:
            if col in data:
                values[col] = _to_str(data[col])

        stmt = (
            update(Task)
            .where(Task.id == task_id, Task.version == version)
            .values(**values)
            .returning(Task)
        )
        result = await self._db.execute(stmt)
        updated = result.scalar_one_or_none()

        if updated is not None:
            return updated.to_dict()

        # rowcount == 0: need to distinguish 404 from 409
        exists_result = await self._db.execute(
            select(func.count()).where(Task.id == task_id)
        )
        exists = exists_result.scalar_one() > 0
        return VERSION_CONFLICT if exists else NOT_FOUND

    async def delete(self, task_id: int) -> bool:
        """
        Delete the task with *task_id*.

        Returns True if a row was deleted, False if it didn't exist.
        """
        result = await self._db.execute(
            select(Task).where(Task.id == task_id)
        )
        task = result.scalar_one_or_none()
        if task is None:
            return False
        await self._db.delete(task)
        return True
