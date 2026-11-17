from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.projects.models import Project, Task
from app.modules.projects.schemas import (
    ProjectCreate,
    ProjectRead,
    ProjectSummary,
    ProjectUpdate,
    TaskCreate,
    TaskRead,
    TaskUpdate,
)

router = APIRouter(prefix="/projects")


def _include(**kwargs):
    child, _ = build_crud_router(module="projects", **kwargs)
    router.include_router(child)


_include(
    model=Project,
    read_schema=ProjectRead,
    create_schema=ProjectCreate,
    update_schema=ProjectUpdate,
    prefix="/projects",
    tags=["Projects · Projects"],
    permission_prefix="projects.project",
    entity="Project",
    search_fields=("name", "code", "client_name"),
    filter_fields=("status", "client_name"),
    load_options=(selectinload(Project.tasks),),
)

_include(
    model=Task,
    read_schema=TaskRead,
    create_schema=TaskCreate,
    update_schema=TaskUpdate,
    prefix="/tasks",
    tags=["Projects · Tasks"],
    permission_prefix="projects.task",
    entity="Task",
    search_fields=("title", "description"),
    filter_fields=("project_id", "status", "priority", "assignee_id"),
    load_options=(selectinload(Task.project),),
)


@router.get("/projects/{project_id}/summary", response_model=ProjectSummary, tags=["Projects · Reports"])
async def project_summary(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.project.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Project).options(selectinload(Project.tasks)).where(Project.id == project_id)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Project.tenant_id == user.tenant_id)
    project = await db.scalar(stmt)
    if project is None:
        raise NotFoundError("Project not found")
    done = [task for task in project.tasks if task.status == "done"]
    estimated = sum((Decimal(task.estimated_hours or 0) for task in project.tasks), Decimal("0"))
    actual = sum((Decimal(task.actual_hours or 0) for task in project.tasks), Decimal("0"))
    billable = sum((Decimal(task.actual_hours or 0) * Decimal(task.billable_rate or 0) for task in project.tasks), Decimal("0"))
    return ProjectSummary(
        project_id=project.id,
        total_tasks=len(project.tasks),
        done_tasks=len(done),
        open_tasks=len(project.tasks) - len(done),
        total_budget=project.budget,
        estimated_hours=estimated,
        actual_hours=actual,
        billable_value=billable,
    )
