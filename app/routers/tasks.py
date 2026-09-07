"""
Task router — HTTP concerns only.

Each handler:
  1. Receives validated input from FastAPI (Pydantic schemas, query params).
  2. Calls the TaskService method.
  3. Returns the response model.

No SQL, no sentinel inspection, no business logic lives here.
"""

from datetime import date

from fastapi import APIRouter, Depends, Query, Response
from fastapi import status as http_status

from app.dependencies import get_task_service
from app.schemas.task import (
    PaginatedResponse,
    SortBy,
    SortOrder,
    TaskCreate,
    TaskOut,
    TaskStatus,
    TaskUpdate,
)
from app.services.task_service import TaskService

router = APIRouter()


@router.post("", status_code=http_status.HTTP_201_CREATED, response_model=TaskOut)
async def create_task(
    payload: TaskCreate,
    svc: TaskService = Depends(get_task_service),
) -> TaskOut:
    row = await svc.create_task(payload.model_dump())
    return TaskOut.model_validate(row)


@router.get("", response_model=PaginatedResponse[TaskOut])
async def list_tasks(
    status: TaskStatus | None = Query(default=None),
    due_before: date | None = Query(default=None),
    due_after: date | None = Query(default=None),
    sort_by: SortBy = Query(default="created_at"),
    sort_order: SortOrder = Query(default="desc"),
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(
        default=20, ge=1, le=100, description="Items per page (max 100)"
    ),
    svc: TaskService = Depends(get_task_service),
) -> PaginatedResponse[TaskOut]:
    return await svc.list_tasks_paginated(
        status=status,
        due_before=due_before,
        due_after=due_after,
        sort_by=sort_by,
        sort_order=sort_order,
        page=page,
        page_size=page_size,
    )


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: int,
    svc: TaskService = Depends(get_task_service),
) -> TaskOut:
    row = await svc.get_task(task_id)
    return TaskOut.model_validate(row)


@router.put("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: int,
    payload: TaskUpdate,
    svc: TaskService = Depends(get_task_service),
) -> TaskOut:
    row = await svc.update_task(
        task_id,
        payload.model_dump(exclude_unset=True),
        payload.version,
    )
    return TaskOut.model_validate(row)


@router.delete("/{task_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    svc: TaskService = Depends(get_task_service),
) -> Response:
    await svc.delete_task(task_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
