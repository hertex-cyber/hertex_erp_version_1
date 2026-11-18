import json
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import create_model
from sqlalchemy import Integer, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.crud import CRUDService, build_crud_router
from app.core.deps import get_current_user, require_permissions
from app.core.exceptions import ConflictError, ForbiddenError, ValidationError
from app.core.schemas import Page
from app.db.session import AsyncSessionLocal, get_db
from app.modules.identity.models import User
from app.modules.projects import models as m
from app.modules.projects import workflows as wf
from app.modules.projects.filters import apply_filter
from app.modules.projects.schemas import (
    AiActionDecision,
    AiSignalRequest,
    AutomationRunRequest,
    BacklogUpdate,
    BaselineCreate,
    BillingPostRequest,
    BillingPreview,
    BillingReviewRequest,
    BillingRunCreate,
    CapacityQuery,
    CapacityRow,
    CommentCreate,
    CommentUpdate,
    CostRow,
    CriticalPathResponse,
    GovernanceSummary,
    ImportMappingDecision,
    ImportSubmit,
    IntakeDecision,
    IntakeSubmit,
    NotificationRequest,
    ProfitabilitySummary,
    ProjectCompletionRequest,
    ProjectSummary,
    RateChangeRequest,
    ReportResponse,
    ScheduleVarianceRow,
    SprintCompleteRequest,
    SprintMetrics,
    TimeEntryDecision,
    TransitionRequest,
    UnbilledReport,
    WorkItemLinkCreate,
    WorkloadRow,
    schema_for,
)
from app.modules.projects.services import (
    IMMUTABLE_MODELS,
    as_decimal,
    assert_no_dependency_cycle,
    assert_no_parent_cycle,
    billing_preview,
    change_resource_rate,
    critical_path,
    dispatch_outbox,
    enqueue_event,
    get_or_404,
    guard_ai_prohibited_action,
    guard_baseline_immutable,
    guard_capacity_override,
    guard_immutable,
    guard_no_double_billing,
    guard_project_completion,
    guard_resource_scope,
    guard_reviewer_not_assignee,
    guard_self_approval,
    guard_subtask_completion,
    guard_update_fields,
    guard_wip_limit,
    idempotency_lookup,
    idempotency_store,
    mask_sensitive,
    post_billing_run,
    recompute_task_actual_hours,
    record_activity,
    refresh_ai_signals,
    refresh_capacity,
    resolve_employee_id,
    run_automation_rules,
    sequence_number,
    utcnow,
    workload_rows,
)
from app.modules.projects.state_machines import next_status


class IdempotentRoute(APIRoute):
    def get_route_handler(self):
        original_handler = super().get_route_handler()

        async def route_handler(request: Request):
            key = request.headers.get("idempotency-key")
            if request.method not in ("POST", "PATCH") or not key:
                return await original_handler(request)
            scope = f"{request.method}:{request.url.path}"
            user = None
            auth = request.headers.get("authorization", "")
            scheme, _, token = auth.partition(" ")
            if scheme.lower() == "bearer" and token:
                async with AsyncSessionLocal() as lookup_db:
                    try:
                        user = await get_current_user(
                            HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
                            lookup_db,
                        )
                        cached = await idempotency_lookup(lookup_db, user, scope, key)
                    except Exception:
                        cached = None
                    if cached is not None:
                        return JSONResponse(
                            status_code=cached.get("status_code", 200),
                            content=cached.get("response"),
                        )
            response = await original_handler(request)
            if user is not None and response.status_code < 400 and hasattr(response, "body"):
                try:
                    body = json.loads(response.body)
                    async with AsyncSessionLocal() as store_db:
                        await idempotency_store(
                            store_db, user, scope, key, body, response.status_code
                        )
                        await store_db.commit()
                except Exception:
                    pass
            return response

        return route_handler


router = APIRouter(
    prefix="/projects", tags=["Project Management"], route_class=IdempotentRoute
)

ProjectCreateSchema = schema_for(m.Project, "create")
ProjectBaseReadSchema = schema_for(m.Project, "read")
TaskCreateSchema = schema_for(m.Task, "create")
TaskReadSchema = schema_for(m.Task, "read")
ProjectReadSchema = create_model(
    "ProjectReadSchema",
    __base__=ProjectBaseReadSchema,
    tasks=(list[TaskReadSchema], []),
)
SprintCreateSchema = schema_for(m.ProjectSprint, "create")
SprintReadSchema = schema_for(m.ProjectSprint, "read")
DependencyCreateSchema = schema_for(m.ProjectDependency, "create")
DependencyReadSchema = schema_for(m.ProjectDependency, "read")
TimeEntryCreateSchema = schema_for(m.ProjectTimeEntry, "create")
TimeEntryReadSchema = schema_for(m.ProjectTimeEntry, "read")
TimesheetReadSchema = schema_for(m.ProjectTimesheet, "read")
MilestoneReadSchema = schema_for(m.ProjectMilestone, "read")
RiskReadSchema = schema_for(m.ProjectRisk, "read")
IssueReadSchema = schema_for(m.ProjectIssue, "read")
ChangeRequestReadSchema = schema_for(m.ProjectChangeRequest, "read")
BookingReadSchema = schema_for(m.ProjectResourceBooking, "read")
BillingRunReadSchema = schema_for(m.ProjectBillingRun, "read")
AiSignalReadSchema = schema_for(m.ProjectAiSignal, "read")
AiActionCreateSchema = schema_for(m.ProjectAiAction, "create")
AiActionReadSchema = schema_for(m.ProjectAiAction, "read")
AutomationRunReadSchema = schema_for(m.ProjectAutomationRun, "read")
StatusUpdateReadSchema = schema_for(m.ProjectStatusUpdate, "read")

ProjectCRUD = CRUDService(
    m.Project,
    search_fields=("name", "code", "number"),
    filter_fields=("status", "health", "priority", "portfolio_id", "program_id"),
)

DONE_STATUSES = {"done", "accepted", "closed", "cancelled", "paid", "invoiced"}
ALLOWED_AI_ACTIONS = {
    "draft_status_update",
    "draft_risk",
    "draft_issue",
    "draft_work_item",
}
BOARD_COLUMNS = (
    ("To Do", "todo"),
    ("In Progress", "in_progress"),
    ("Blocked", "blocked"),
    ("In Review", "review"),
    ("Done", "done"),
)
STATUS_COLUMN = {
    "backlog": "To Do",
    "todo": "To Do",
    "in_progress": "In Progress",
    "blocked": "Blocked",
    "in_review": "In Review",
    "done": "Done",
    "accepted": "Done",
    "closed": "Done",
    "cancelled": "To Do",
}


def _serialize(model: Any, obj: Any, user: User) -> dict[str, Any]:
    from app.modules.projects.services import mask_sensitive

    data = schema_for(model, "read").model_validate(obj).model_dump(mode="json")
    if model is m.Project:
        data["tasks"] = [
            schema_for(m.Task, "read").model_validate(task).model_dump(mode="json")
            for task in obj.tasks
        ]
    return mask_sensitive(model.__name__, data, user)


async def _write_audit(
    db: AsyncSession,
    user: User,
    request: Request,
    entity: str,
    entity_id: UUID,
    action: str,
    changes: dict[str, Any],
    on_behalf_of: UUID | None = None,
) -> None:
    correlation_id = request.headers.get("x-correlation-id")
    await record_audit(
        db,
        user=user,
        action=action,
        module="projects",
        entity=entity,
        entity_id=entity_id,
        changes=changes,
        request=request,
        on_behalf_of=on_behalf_of,
        correlation_id=correlation_id,
    )
    await record_activity(
        db, user, entity, entity_id, action, changes, correlation_id=correlation_id
    )


async def _ensure_default_board(db: AsyncSession, user: User, project_id: UUID) -> m.ProjectBoard:
    stmt = select(m.ProjectBoard).where(
        m.ProjectBoard.project_id == project_id,
        m.ProjectBoard.name == "Default",
    )
    if user.tenant_id:
        stmt = stmt.where(m.ProjectBoard.tenant_id == user.tenant_id)
    board = await db.scalar(stmt)
    if board is not None:
        return board
    board = m.ProjectBoard(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        project_id=project_id,
        name="Default",
        type="kanban",
    )
    db.add(board)
    await db.flush()
    for sequence, (name, category) in enumerate(BOARD_COLUMNS, start=1):
        db.add(
            m.ProjectBoardColumn(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                board_id=board.id,
                name=name,
                sequence=sequence,
                status_category=category,
                wip_limit=3 if category == "in_progress" else None,
            )
        )
    await db.flush()
    return board


async def _default_column_id(db: AsyncSession, board: m.ProjectBoard, status: str) -> Optional[UUID]:
    name = STATUS_COLUMN.get(status, "To Do")
    stmt = select(m.ProjectBoardColumn.id).where(
        m.ProjectBoardColumn.board_id == board.id,
        m.ProjectBoardColumn.name == name,
    )
    return await db.scalar(stmt)


def _project_id(obj: Any) -> Optional[UUID]:
    value = getattr(obj, "project_id", None)
    if value is not None:
        return value
    if isinstance(obj, m.Project):
        return obj.id
    return None


def _owner_employee_id(obj: Any) -> Optional[UUID]:
    for field in ("employee_id", "manager_employee_id", "assignee_id", "owner_employee_id"):
        value = getattr(obj, field, None)
        if value is not None:
            return value
    return None


async def _transition(
    db: AsyncSession,
    user: User,
    request: Request,
    model: Any,
    item_id: UUID,
    kind: str,
    payload: TransitionRequest,
    entity: str,
) -> Any:
    item = await get_or_404(db, user, model, item_id)
    target = next_status(kind, item.status, payload.event)
    changes: dict[str, Any] = {
        "from_status": item.status,
        "to_status": target,
        "event": payload.event,
    }
    if payload.comment:
        changes["comment"] = payload.comment
    waiver_code = getattr(payload, "waiver_code", None)
    waiver_approval_id = getattr(payload, "waiver_approval_id", None)
    if waiver_code is not None:
        changes["waiver_code"] = waiver_code
    if waiver_approval_id is not None:
        changes["waiver_approval_id"] = str(waiver_approval_id)

    if kind == "project" and target == "completed":
        await guard_project_completion(
            db,
            item,
            user=user,
            waiver_code=waiver_code,
            waiver_approval_id=waiver_approval_id,
        )

    if target in ("approved", "accepted", "confirmed", "closed", "completed"):
        await guard_self_approval(
            db,
            user,
            entity_type=entity,
            entity_id=item.id,
            owner_employee_id=_owner_employee_id(item),
        )

    if kind == "work_item" and target in DONE_STATUSES:
        await guard_reviewer_not_assignee(db, user, item)
        await guard_subtask_completion(db, item)
        if item.board_id is not None:
            board = await get_or_404(db, user, m.ProjectBoard, item.board_id)
            target_column_id = await _default_column_id(db, board, target)
            if target_column_id is not None:
                occupant_stmt = select(func.count()).select_from(m.Task).where(
                    m.Task.board_column_id == target_column_id,
                    m.Task.is_active.is_(True),
                    m.Task.id != item.id,
                )
                await guard_wip_limit(
                    db,
                    await get_or_404(db, user, m.ProjectBoardColumn, target_column_id),
                    int(await db.scalar(occupant_stmt) or 0),
                    user=user,
                    entity_id=item.id,
                )
                item.board_column_id = target_column_id

    if model in (m.ProjectBaseline, m.ProjectBaselineSnapshot):
        guard_baseline_immutable(item)

    if kind == "billing_run" and target in ("approved", "invoiced"):
        line_stmt = select(m.ProjectBillingLine).where(
            m.ProjectBillingLine.billing_run_id == item.id,
            m.ProjectBillingLine.is_active.is_(True),
        )
        for line in (await db.scalars(line_stmt)).all():
            if line.source_id is not None and line.source_type:
                await guard_no_double_billing(
                    db,
                    source_type=line.source_type,
                    source_id=line.source_id,
                    exclude_line_id=line.id,
                )

    if kind == "time_entry" and target == "approved":
        item.approved_by_id = user.id
        item.approved_at = utcnow()
    if kind == "timesheet" and target == "approved":
        item.approved_by_id = user.id
        item.approved_at = utcnow()
        entry_stmt = select(m.ProjectTimesheetEntry).where(
            m.ProjectTimesheetEntry.timesheet_id == item.id
        )
        for link in (await db.scalars(entry_stmt)).all():
            entry = await db.scalar(
                select(m.ProjectTimeEntry).where(m.ProjectTimeEntry.id == link.time_entry_id)
            )
            if entry and entry.status in ("submitted", "rejected"):
                entry.status = "approved"
                entry.approved_by_id = user.id
                entry.approved_at = utcnow()
                await recompute_task_actual_hours(db, entry.work_item_id)
    if kind == "change_request" and target == "approved":
        item.approved_by_id = user.id
    if kind == "booking" and target == "confirmed":
        await guard_capacity_override(db, user, item)
        item.approved_by_id = user.id
    if kind == "risk" and target == "escalated" and item.project_id:
        board = await _ensure_default_board(db, user, item.project_id)
        task = m.Task(
            tenant_id=user.tenant_id,
            created_by_id=user.id,
            project_id=item.project_id,
            title=f"Mitigate risk: {item.title}",
            number=await sequence_number(db, user, "work_item", "PRJ-T"),
            description=item.mitigation_plan,
            status="todo",
            priority="high",
            board_id=board.id,
            board_column_id=await _default_column_id(db, board, "todo"),
        )
        db.add(task)
        await db.flush()
        changes["mitigation_work_item_id"] = str(task.id)

    item.status = target
    if hasattr(item, "state_changed_at"):
        item.state_changed_at = utcnow()
    if hasattr(item, "version"):
        item.version = int(item.version or 1) + 1
    if hasattr(item, "completed_at") and target in DONE_STATUSES:
        item.completed_at = utcnow()
    if hasattr(item, "published_at") and target == "published":
        item.published_at = utcnow()
    await db.flush()

    await _write_audit(db, user, request, entity, item.id, f"{kind}.{payload.event}", changes)
    event_name = "project.started" if kind == "project" and target == "active" else f"{kind}.{target}"
    await enqueue_event(
        db,
        user,
        event_name,
        {
            "entity_type": entity,
            "entity_id": str(item.id),
            "project_id": str(_project_id(item)) if _project_id(item) else None,
        },
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await run_automation_rules(
        db,
        user,
        event_name,
        item.id,
        _project_id(item),
    )
    return item


async def _project_id_for_entity(
    db: AsyncSession,
    user: User,
    entity_type: str,
    entity_id: UUID,
) -> UUID:
    if entity_type == "project":
        return entity_id
    if entity_type in ("work_item", "task"):
        return (await get_or_404(db, user, m.Task, entity_id)).project_id
    if entity_type == "time_entry":
        entry = await get_or_404(db, user, m.ProjectTimeEntry, entity_id)
        return (await get_or_404(db, user, m.Task, entry.work_item_id)).project_id
    model_by_type = {
        "milestone": m.ProjectMilestone,
        "dependency": m.ProjectDependency,
        "risk": m.ProjectRisk,
        "issue": m.ProjectIssue,
        "change_request": m.ProjectChangeRequest,
        "sprint": m.ProjectSprint,
        "phase": m.ProjectPhase,
        "release": m.ProjectRelease,
        "booking": m.ProjectResourceBooking,
        "status_update": m.ProjectStatusUpdate,
    }
    model = model_by_type.get(entity_type)
    if model is None:
        raise ValidationError(f"Unsupported AI action entity_type: {entity_type}")
    return (await get_or_404(db, user, model, entity_id)).project_id


@router.get("", response_model=Page[ProjectReadSchema])
async def list_projects(
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    include_inactive: bool = False,
    dsl_filter: Optional[str] = Query(None, alias="filter"),
    user: User = Depends(require_permissions("projects.project.read")),
    db: AsyncSession = Depends(get_db),
):
    if dsl_filter:
        stmt = select(m.Project)
        if not include_inactive:
            stmt = stmt.where(m.Project.is_active.is_(True))
        if user.tenant_id and not user.is_superuser:
            stmt = stmt.where(m.Project.tenant_id == user.tenant_id)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(
                or_(m.Project.name.ilike(pattern), m.Project.code.ilike(pattern), m.Project.number.ilike(pattern))
            )
        stmt = apply_filter(stmt, "Project", dsl_filter, user)
        total = int((await db.scalar(select(func.count()).select_from(stmt.subquery())) ) or 0)
        stmt = stmt.order_by(m.Project.created_at.desc()).offset((page - 1) * size).limit(size)
        items = list((await db.scalars(stmt)).all())
    else:
        filters = {
            field: request.query_params.get(field)
            for field in ProjectCRUD.filter_fields
            if request.query_params.get(field) not in (None, "")
        }
        items, total = await ProjectCRUD.list(
            db,
            user,
            page=page,
            size=size,
            search=q,
            filters=filters,
            include_inactive=include_inactive,
        )
    return {
        "items": [_serialize(m.Project, item, user) for item in items],
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
    }


@router.post("", response_model=ProjectReadSchema, status_code=201)
async def create_project(
    payload: ProjectCreateSchema,
    request: Request,
    user: User = Depends(require_permissions("projects.project.create")),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    data["number"] = await sequence_number(db, user, "project", "PRJ")
    if not data.get("manager_employee_id"):
        data["manager_employee_id"] = await resolve_employee_id(db, user)
    if not data.get("manager_id"):
        data["manager_id"] = user.id
    project = m.Project(tenant_id=user.tenant_id, created_by_id=user.id, **data)
    db.add(project)
    await db.flush()
    await _ensure_default_board(db, user, project.id)
    await _write_audit(db, user, request, "project", project.id, "create", data)
    await enqueue_event(
        db,
        user,
        "project.created",
        {"project_id": str(project.id)},
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await db.commit()
    await db.refresh(project)
    return _serialize(m.Project, project, user)


@router.post("/projects/{project_id}/submit", response_model=ProjectReadSchema)
async def submit_project(
    project_id: UUID,
    request: Request,
    payload: TransitionRequest,
    user: User = Depends(require_permissions("projects.project.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(db, user, request, m.Project, project_id, "project", payload, "project")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Project, item, user)


@router.post("/projects/{project_id}/approve", response_model=ProjectReadSchema)
async def approve_project(
    project_id: UUID,
    request: Request,
    payload: TransitionRequest,
    user: User = Depends(require_permissions("projects.approval.create")),
    db: AsyncSession = Depends(get_db),
):
    event = payload.event or "approve"
    payload.event = event
    item = await _transition(db, user, request, m.Project, project_id, "project", payload, "project")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Project, item, user)


@router.post("/projects/{project_id}/activate", response_model=ProjectReadSchema)
async def activate_project(
    project_id: UUID,
    request: Request,
    payload: TransitionRequest,
    user: User = Depends(require_permissions("projects.project.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(db, user, request, m.Project, project_id, "project", payload, "project")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Project, item, user)


@router.post("/projects/{project_id}/complete", response_model=ProjectReadSchema)
async def complete_project(
    project_id: UUID,
    request: Request,
    payload: ProjectCompletionRequest,
    user: User = Depends(require_permissions("projects.project.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(db, user, request, m.Project, project_id, "project", payload, "project")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Project, item, user)


@router.get("/projects/{project_id}/summary", response_model=ProjectSummary)
async def project_summary(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.report.read")),
    db: AsyncSession = Depends(get_db),
):
    project = await get_or_404(db, user, m.Project, project_id)
    stmt = select(
        func.count(),
        func.sum(func.cast(m.Task.status.in_(DONE_STATUSES), Integer)),
        func.coalesce(func.sum(m.Task.estimated_hours), 0),
        func.coalesce(func.sum(m.Task.actual_hours), 0),
        func.coalesce(func.sum(m.Task.billable_amount), 0),
    ).where(m.Task.project_id == project.id, m.Task.is_active.is_(True))
    row = (await db.execute(stmt)).one()
    total, done, estimated, actual, billable = row
    summary = ProjectSummary(
        project_id=project.id,
        total_tasks=int(total or 0),
        done_tasks=int(done or 0),
        open_tasks=int(total or 0) - int(done or 0),
        total_budget=as_decimal(project.budget),
        estimated_hours=as_decimal(estimated),
        actual_hours=as_decimal(actual),
        billable_value=as_decimal(billable),
    )
    return ProjectSummary.model_validate(
        mask_sensitive("ProjectSummary", summary.model_dump(mode="json"), user)
    )


@router.get("/projects/{project_id}/critical-path", response_model=CriticalPathResponse)
async def project_critical_path(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.schedule.read")),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, user, m.Project, project_id)
    return await critical_path(db, user, project_id)


@router.post("/work-items", response_model=TaskReadSchema, status_code=201)
async def create_work_item(
    payload: TaskCreateSchema,
    request: Request,
    user: User = Depends(require_permissions("projects.workitem.create")),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    project = await get_or_404(db, user, m.Project, data["project_id"])
    data["number"] = await sequence_number(db, user, "work_item", "PRJ-T")
    if not data.get("employee_id"):
        data["employee_id"] = await resolve_employee_id(db, user)
    parent_id = data.get("parent_work_item_id")
    if parent_id:
        await assert_no_parent_cycle(db, uuid4(), parent_id)
    board = await _ensure_default_board(db, user, project.id)
    data.setdefault("board_id", board.id)
    data.setdefault("board_column_id", await _default_column_id(db, board, data.get("status", "backlog")))
    item = m.Task(tenant_id=user.tenant_id, created_by_id=user.id, **data)
    db.add(item)
    await db.flush()
    await _write_audit(db, user, request, "task", item.id, "create", data)
    await enqueue_event(
        db,
        user,
        "work_item.created",
        {"work_item_id": str(item.id), "project_id": str(project.id)},
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await run_automation_rules(db, user, "work_item.created", item.id, project.id)
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Task, item, user)


@router.post("/work-items/{item_id}/transition", response_model=TaskReadSchema)
async def transition_work_item(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.workitem.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(db, user, request, m.Task, item_id, "work_item", payload, "task")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Task, item, user)


@router.patch("/work-items/{item_id}/rank", response_model=TaskReadSchema)
async def rank_work_item(
    item_id: UUID,
    rank: Decimal = Query(..., ge=0),
    user: User = Depends(require_permissions("projects.workitem.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await get_or_404(db, user, m.Task, item_id)
    item.rank = rank
    item.version = int(item.version or 1) + 1
    await db.flush()
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Task, item, user)


@router.post("/sprints", response_model=SprintReadSchema, status_code=201)
async def create_sprint(
    payload: SprintCreateSchema,
    request: Request,
    user: User = Depends(require_permissions("projects.sprint.create")),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    await get_or_404(db, user, m.Project, data["project_id"])
    if data["end_date"] < data["start_date"]:
        raise ValidationError("Sprint end_date must be on or after start_date")
    data["number"] = await sequence_number(db, user, "sprint", "SPR")
    sprint = m.ProjectSprint(tenant_id=user.tenant_id, created_by_id=user.id, **data)
    db.add(sprint)
    await db.flush()
    await _write_audit(db, user, request, "sprint", sprint.id, "create", data)
    await db.commit()
    await db.refresh(sprint)
    return _serialize(m.ProjectSprint, sprint, user)


@router.post("/sprints/{item_id}/transition", response_model=SprintReadSchema)
async def transition_sprint(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.sprint.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(db, user, request, m.ProjectSprint, item_id, "sprint", payload, "sprint")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectSprint, item, user)


@router.post("/milestones/{item_id}/transition", response_model=MilestoneReadSchema)
async def transition_milestone(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.milestone.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(db, user, request, m.ProjectMilestone, item_id, "milestone", payload, "milestone")
    if payload.event == "accept":
        item.accepted_by_id = user.id
        item.accepted_at = utcnow()
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectMilestone, item, user)


@router.post("/dependencies", response_model=DependencyReadSchema, status_code=201)
async def create_dependency(
    payload: DependencyCreateSchema,
    request: Request,
    user: User = Depends(require_permissions("projects.schedule.create")),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    predecessor = await get_or_404(db, user, m.Task, data["predecessor_id"])
    successor = await get_or_404(db, user, m.Task, data["successor_id"])
    await assert_no_dependency_cycle(
        db,
        user.tenant_id,
        data["predecessor_id"],
        data["successor_id"],
    )
    data["status"] = "proposed"
    dependency = m.ProjectDependency(tenant_id=user.tenant_id, created_by_id=user.id, **data)
    db.add(dependency)
    await db.flush()
    await _write_audit(db, user, request, "dependency", dependency.id, "create", data)
    await enqueue_event(
        db,
        user,
        "dependency.proposed",
        {
            "dependency_id": str(dependency.id),
            "project_id": str(predecessor.project_id or successor.project_id),
        },
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await db.commit()
    await db.refresh(dependency)
    return _serialize(m.ProjectDependency, dependency, user)


@router.post("/dependencies/{item_id}/transition", response_model=DependencyReadSchema)
async def transition_dependency(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.schedule.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(
        db, user, request, m.ProjectDependency, item_id, "dependency", payload, "dependency"
    )
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectDependency, item, user)


@router.post("/time-entries", response_model=TimeEntryReadSchema, status_code=201)
async def create_time_entry(
    payload: TimeEntryCreateSchema,
    request: Request,
    user: User = Depends(require_permissions("projects.timeentry.create")),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    if as_decimal(data.get("hours")) <= 0:
        raise ValidationError("hours must be greater than zero")
    work_item = await get_or_404(db, user, m.Task, data["work_item_id"])
    project = await get_or_404(db, user, m.Project, work_item.project_id)
    entry_date = data.get("entry_date")
    if isinstance(entry_date, str):
        entry_date = date.fromisoformat(entry_date)
    if entry_date and (
        (project.start_date and entry_date < project.start_date)
        or (project.end_date and entry_date > project.end_date)
    ):
        raise ValidationError("entry_date must be within the project date window")
    data["status"] = "draft"
    data.setdefault("source", "manual")
    if not data.get("employee_id"):
        data["employee_id"] = await resolve_employee_id(db, user)
    if data.get("external_id"):
        existing = await db.scalar(
            select(m.ProjectTimeEntry).where(
                m.ProjectTimeEntry.tenant_id == user.tenant_id,
                m.ProjectTimeEntry.source == data["source"],
                m.ProjectTimeEntry.external_id == data["external_id"],
            )
        )
        if existing is not None:
            await db.refresh(existing)
            return _serialize(m.ProjectTimeEntry, existing, user)
    data.setdefault("billable", work_item.is_billable)
    data.setdefault("billable_rate", work_item.billable_rate if data["billable"] else Decimal("0"))
    data.setdefault("cost_rate", Decimal("0"))
    entry = m.ProjectTimeEntry(tenant_id=user.tenant_id, created_by_id=user.id, **data)
    db.add(entry)
    await db.flush()
    await _write_audit(db, user, request, "time_entry", entry.id, "create", data)
    await enqueue_event(
        db,
        user,
        "time_entry.created",
        {"time_entry_id": str(entry.id), "project_id": str(project.id)},
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await db.commit()
    await db.refresh(entry)
    return _serialize(m.ProjectTimeEntry, entry, user)


@router.post("/time-entries/{item_id}/submit", response_model=TimeEntryReadSchema)
async def submit_time_entry(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.timeentry.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(
        db, user, request, m.ProjectTimeEntry, item_id, "time_entry", payload, "time_entry"
    )
    if item.employee_id:
        week = week_start_date(item.entry_date)
        stmt = select(m.ProjectTimesheet).where(
            m.ProjectTimesheet.employee_id == item.employee_id,
            m.ProjectTimesheet.week_start == week,
        )
        if user.tenant_id:
            stmt = stmt.where(m.ProjectTimesheet.tenant_id == user.tenant_id)
        timesheet = await db.scalar(stmt)
        if timesheet is None:
            timesheet = m.ProjectTimesheet(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                employee_id=item.employee_id,
                week_start=week,
            )
            db.add(timesheet)
            await db.flush()
        link_stmt = select(m.ProjectTimesheetEntry).where(
            m.ProjectTimesheetEntry.timesheet_id == timesheet.id,
            m.ProjectTimesheetEntry.time_entry_id == item.id,
        )
        if await db.scalar(link_stmt) is None:
            db.add(
                m.ProjectTimesheetEntry(
                    tenant_id=user.tenant_id,
                    created_by_id=user.id,
                    timesheet_id=timesheet.id,
                    time_entry_id=item.id,
                )
            )
            await db.flush()
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectTimeEntry, item, user)


@router.post("/time-entries/{item_id}/approve", response_model=TimeEntryReadSchema)
async def approve_time_entry(
    item_id: UUID,
    payload: TimeEntryDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.timeentry.approve")),
    db: AsyncSession = Depends(get_db),
):
    transition = TransitionRequest(event="approve", comment=payload.comment)
    item = await _transition(
        db, user, request, m.ProjectTimeEntry, item_id, "time_entry", transition, "time_entry"
    )
    await recompute_task_actual_hours(db, item.work_item_id)
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectTimeEntry, item, user)


@router.post("/time-entries/{item_id}/reject", response_model=TimeEntryReadSchema)
async def reject_time_entry(
    item_id: UUID,
    payload: TimeEntryDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.timeentry.approve")),
    db: AsyncSession = Depends(get_db),
):
    transition = TransitionRequest(event="reject", comment=payload.comment)
    item = await _transition(
        db, user, request, m.ProjectTimeEntry, item_id, "time_entry", transition, "time_entry"
    )
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectTimeEntry, item, user)


@router.post("/timesheets/{item_id}/approve", response_model=TimesheetReadSchema)
async def approve_timesheet(
    item_id: UUID,
    payload: TimeEntryDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.timesheet.approve")),
    db: AsyncSession = Depends(get_db),
):
    transition = TransitionRequest(event="approve", comment=payload.comment)
    item = await _transition(
        db, user, request, m.ProjectTimesheet, item_id, "timesheet", transition, "timesheet"
    )
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectTimesheet, item, user)


@router.get("/billing/preview", response_model=BillingPreview)
async def preview_billing(
    project_id: UUID,
    billing_type: Optional[str] = None,
    user: User = Depends(require_permissions("projects.finance.read")),
    db: AsyncSession = Depends(get_db),
):
    project = await get_or_404(db, user, m.Project, project_id)
    return await billing_preview(db, user, project, billing_type)


@router.post("/billing-runs", response_model=BillingRunReadSchema, status_code=201)
async def create_billing_run(
    payload: BillingRunCreate,
    request: Request,
    user: User = Depends(require_permissions("projects.billing.create")),
    db: AsyncSession = Depends(get_db),
):
    project = await get_or_404(db, user, m.Project, payload.project_id)
    preview = await billing_preview(db, user, project, payload.billing_type)
    if not preview.lines:
        raise ConflictError("No billable items are available for this project")
    idempotency_key = payload.idempotency_key or uuid4().hex
    existing_stmt = select(m.ProjectBillingRun).where(
        m.ProjectBillingRun.idempotency_key == idempotency_key
    )
    if user.tenant_id:
        existing_stmt = existing_stmt.where(m.ProjectBillingRun.tenant_id == user.tenant_id)
    existing = await db.scalar(existing_stmt)
    if existing is not None:
        return _serialize(m.ProjectBillingRun, existing, user)
    run = m.ProjectBillingRun(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        project_id=project.id,
        period=payload.period,
        currency=project.currency,
        billing_type=preview.billing_type,
        gross_amount=preview.gross_amount,
        status="draft",
        idempotency_key=idempotency_key,
    )
    db.add(run)
    await db.flush()
    for line in preview.lines:
        db.add(
            m.ProjectBillingLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                billing_run_id=run.id,
                source_type=line.source_type,
                source_id=line.source_id,
                description=line.description,
                quantity=line.quantity,
                rate=line.rate,
                amount=line.amount,
                status="draft",
            )
        )
    await db.flush()
    await _write_audit(db, user, request, "billing_run", run.id, "create", payload.model_dump())
    await enqueue_event(
        db,
        user,
        "billing.draft_created",
        {"billing_run_id": str(run.id), "project_id": str(project.id)},
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await db.commit()
    await db.refresh(run)
    return _serialize(m.ProjectBillingRun, run, user)


@router.post("/billing-runs/{item_id}/transition", response_model=BillingRunReadSchema)
async def transition_billing_run(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.billing.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(
        db, user, request, m.ProjectBillingRun, item_id, "billing_run", payload, "billing_run"
    )
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectBillingRun, item, user)


@router.post("/billing-runs/{item_id}/post", response_model=BillingRunReadSchema)
async def post_billing(
    item_id: UUID,
    payload: BillingPostRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.billing.post")),
    db: AsyncSession = Depends(get_db),
):
    run = await get_or_404(db, user, m.ProjectBillingRun, item_id)
    result = await post_billing_run(db, user, run, payload)
    run.status = "invoiced"
    run.version = int(run.version or 1) + 1
    await db.flush()
    await _write_audit(db, user, request, "billing_run", run.id, "post", result)
    await db.commit()
    await db.refresh(run)
    return _serialize(m.ProjectBillingRun, run, user)


@router.get("/resources/capacity", response_model=list[CapacityRow])
async def get_capacity(
    params: CapacityQuery = Depends(),
    user: User = Depends(require_permissions("projects.resource.read")),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    start_date = params.start_date or (today - timedelta(days=today.weekday()))
    end_date = params.end_date or (start_date + timedelta(days=28))
    return await refresh_capacity(db, user, start_date, end_date, params.employee_id)


@router.post("/resources/capacity/refresh", response_model=list[CapacityRow])
async def refresh_project_capacity(
    request: Request,
    params: CapacityQuery = Depends(),
    user: User = Depends(require_permissions("projects.resource.update")),
    db: AsyncSession = Depends(get_db),
):
    today = date.today()
    start_date = params.start_date or (today - timedelta(days=today.weekday()))
    end_date = params.end_date or (start_date + timedelta(days=28))
    rows = await refresh_capacity(db, user, start_date, end_date, params.employee_id)
    await record_audit(
        db,
        user=user,
        action="refresh",
        module="projects",
        entity="capacity_calendar",
        changes={"start_date": str(start_date), "end_date": str(end_date)},
        request=request,
    )
    await db.commit()
    return rows


@router.get("/resources/workload", response_model=list[WorkloadRow])
async def get_workload(
    user: User = Depends(require_permissions("projects.resource.read")),
    db: AsyncSession = Depends(get_db),
):
    return await workload_rows(db, user)


@router.post("/resource-roles/{item_id}/rate", response_model=dict[str, Any])
async def update_resource_role_rate(
    item_id: UUID,
    payload: RateChangeRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.resourcerole.update")),
    db: AsyncSession = Depends(get_db),
):
    role = await get_or_404(db, user, m.ProjectResourceRole, item_id)
    changes = await change_resource_rate(
        db,
        user,
        role,
        cost_rate=payload.cost_rate,
        billable_rate=payload.billable_rate,
        reason=payload.reason,
    )
    await record_audit(
        db,
        user=user,
        action="rate_change",
        module="projects",
        entity="resource_role",
        entity_id=item_id,
        changes=changes,
        request=request,
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await db.commit()
    await db.refresh(role)
    return _serialize(m.ProjectResourceRole, role, user)


@router.post("/resource-bookings/{item_id}/approve", response_model=BookingReadSchema)
async def approve_booking(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.resource.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(
        db, user, request, m.ProjectResourceBooking, item_id, "booking", payload, "booking"
    )
    await refresh_capacity(db, user, item.start_date, item.end_date, item.employee_id)
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectResourceBooking, item, user)


@router.post("/risks/{item_id}/transition", response_model=RiskReadSchema)
async def transition_risk(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.risk.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(db, user, request, m.ProjectRisk, item_id, "risk", payload, "risk")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectRisk, item, user)


@router.post("/issues/{item_id}/transition", response_model=IssueReadSchema)
async def transition_issue(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.issue.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(db, user, request, m.ProjectIssue, item_id, "issue", payload, "issue")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectIssue, item, user)


@router.post("/change-requests/{item_id}/transition", response_model=ChangeRequestReadSchema)
async def transition_change_request(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.changerequest.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(
        db,
        user,
        request,
        m.ProjectChangeRequest,
        item_id,
        "change_request",
        payload,
        "change_request",
    )
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectChangeRequest, item, user)


@router.post("/status-updates/{item_id}/transition", response_model=StatusUpdateReadSchema)
async def transition_status_update(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.statusupdate.update")),
    db: AsyncSession = Depends(get_db),
):
    item = await _transition(
        db,
        user,
        request,
        m.ProjectStatusUpdate,
        item_id,
        "status_update",
        payload,
        "status_update",
    )
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectStatusUpdate, item, user)


@router.get("/reports/profitability", response_model=list[ProfitabilitySummary])
async def profitability_report(
    project_id: Optional[UUID] = None,
    user: User = Depends(require_permissions("projects.report.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(m.Project).where(m.Project.is_active.is_(True))
    if user.tenant_id:
        stmt = stmt.where(m.Project.tenant_id == user.tenant_id)
    if project_id:
        stmt = stmt.where(m.Project.id == project_id)
    projects = list((await db.scalars(stmt)).all())
    rows: list[ProfitabilitySummary] = []
    for project in projects:
        cost_stmt = select(
            func.coalesce(func.sum(m.ProjectCostEntry.amount), 0),
            func.coalesce(
                func.sum(
                    func.cast(m.ProjectCostEntry.cost_type == "labour", Integer)
                    * m.ProjectCostEntry.amount
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    func.cast(m.ProjectCostEntry.cost_type == "expense", Integer)
                    * m.ProjectCostEntry.amount
                ),
                0,
            ),
        ).where(m.ProjectCostEntry.project_id == project.id)
        total_cost, labour_cost, expense_cost = (await db.execute(cost_stmt)).one()
        other_cost = as_decimal(total_cost) - as_decimal(labour_cost) - as_decimal(expense_cost)
        margin = as_decimal(project.total_billed) - as_decimal(total_cost)
        margin_percent = Decimal("0")
        if as_decimal(project.total_billed) > 0:
            margin_percent = (margin / as_decimal(project.total_billed) * Decimal("100")).quantize(
                Decimal("0.01")
            )
        rows.append(
            ProfitabilitySummary(
                project_id=project.id,
                budget_revenue=as_decimal(project.budget_revenue),
                budget_cost=as_decimal(project.budget_cost),
                billed=as_decimal(project.total_billed),
                labour_cost=as_decimal(labour_cost),
                expense_cost=as_decimal(expense_cost),
                other_cost=other_cost,
                wip=as_decimal(project.wip_amount),
                margin_amount=margin,
                margin_percent=margin_percent,
            )
        )
    return [
        ProfitabilitySummary.model_validate(
            mask_sensitive("ProfitabilitySummary", row.model_dump(mode="json"), user)
        )
        for row in rows
    ]


@router.get("/reports/governance", response_model=GovernanceSummary)
async def governance_report(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.report.read")),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, user, m.Project, project_id)

    async def count(model: Any, *conditions: Any) -> int:
        stmt = select(func.count()).select_from(model).where(model.project_id == project_id)
        for condition in conditions:
            stmt = stmt.where(condition)
        return int(await db.scalar(stmt) or 0)

    approval_stmt = select(func.count()).select_from(m.ProjectApproval).where(
        m.ProjectApproval.entity_id == project_id,
        m.ProjectApproval.status == "pending",
    )
    if user.tenant_id:
        approval_stmt = approval_stmt.where(m.ProjectApproval.tenant_id == user.tenant_id)
    return GovernanceSummary(
        project_id=project_id,
        open_risks=await count(m.ProjectRisk, m.ProjectRisk.status.notin_(("closed", "cancelled"))),
        escalated_risks=await count(m.ProjectRisk, m.ProjectRisk.status == "escalated"),
        open_issues=await count(m.ProjectIssue, m.ProjectIssue.status.notin_(("closed", "cancelled"))),
        pending_approvals=int(await db.scalar(approval_stmt) or 0),
        status_updates=await count(m.ProjectStatusUpdate),
        goals=await count(m.ProjectGoal),
    )


@router.post("/ai/signals/refresh", response_model=list[AiSignalReadSchema])
async def refresh_signals(
    project_id: Optional[UUID] = None,
    request: Request = None,
    user: User = Depends(require_permissions("projects.ai.update")),
    db: AsyncSession = Depends(get_db),
):
    signals = await refresh_ai_signals(db, user, project_id)
    if request is not None:
        await record_audit(
            db,
            user=user,
            action="refresh",
            module="projects",
            entity="ai_signal",
            changes={"project_id": str(project_id) if project_id else None},
            request=request,
        )
    await db.commit()
    return [_serialize(m.ProjectAiSignal, signal, user) for signal in signals]


@router.post("/ai/signals", response_model=AiSignalReadSchema, status_code=201)
async def create_ai_signal(
    payload: AiSignalRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.ai.create")),
    db: AsyncSession = Depends(get_db),
):
    signal = m.ProjectAiSignal(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entity_type=payload.entity_type,
        entity_id=payload.entity_id,
        signal_type=payload.signal_type,
        score=payload.score,
        features_json=payload.features,
        explanation=payload.explanation,
        model_version="manual-v1",
        generated_at=utcnow(),
        review_status="pending",
    )
    db.add(signal)
    await db.flush()
    await _write_audit(db, user, request, "ai_signal", signal.id, "create", payload.model_dump())
    await db.commit()
    await db.refresh(signal)
    return _serialize(m.ProjectAiSignal, signal, user)


@router.post("/ai/signals/{signal_id}/review", response_model=AiSignalReadSchema)
async def review_ai_signal(
    signal_id: UUID,
    payload: AiActionDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.ai.review")),
    db: AsyncSession = Depends(get_db),
):
    signal = await get_or_404(db, user, m.ProjectAiSignal, signal_id)
    signal.review_status = "reviewed"
    signal.reviewed_by_id = user.id
    await db.flush()
    await _write_audit(db, user, request, "ai_signal", signal.id, "review", payload.model_dump())
    await db.commit()
    await db.refresh(signal)
    return _serialize(m.ProjectAiSignal, signal, user)


@router.post("/ai/actions", response_model=AiActionReadSchema, status_code=201)
async def propose_ai_action(
    payload: AiActionCreateSchema,
    request: Request,
    user: User = Depends(require_permissions("projects.ai.create")),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    guard_ai_prohibited_action(data.get("action_type"))
    if data.get("action_type") not in ALLOWED_AI_ACTIONS:
        raise ValidationError("AI action type is not allowed")
    await _project_id_for_entity(db, user, data["entity_type"], data["entity_id"])
    data["status"] = "proposed"
    data["requested_by_id"] = user.id
    action = m.ProjectAiAction(tenant_id=user.tenant_id, created_by_id=user.id, **data)
    db.add(action)
    await db.flush()
    await _write_audit(db, user, request, "ai_action", action.id, "create", payload.model_dump())
    await db.commit()
    await db.refresh(action)
    return _serialize(m.ProjectAiAction, action, user)


async def _ai_action_transition(
    db: AsyncSession,
    user: User,
    request: Request,
    action_id: UUID,
    event: str,
    payload: AiActionDecision,
) -> m.ProjectAiAction:
    action = await get_or_404(db, user, m.ProjectAiAction, action_id)
    target = next_status("ai_action", action.status, event)
    changes: dict[str, Any] = {"event": event, "from_status": action.status, "to_status": target}
    if payload.comment:
        changes["comment"] = payload.comment
    if event == "review":
        action.approved_by_id = user.id
    if event == "execute":
        guard_ai_prohibited_action(action.action_type)
        if action.action_type not in ALLOWED_AI_ACTIONS:
            raise ConflictError("AI action type is not executable")
        if action.approved_by_id is None:
            raise ConflictError("AI action requires human approval before execution")
        project_id = await _project_id_for_entity(db, user, action.entity_type, action.entity_id)
        proposal = action.proposed_json or {}
        if action.action_type == "draft_status_update":
            db.add(
                m.ProjectStatusUpdate(
                    tenant_id=user.tenant_id,
                    created_by_id=user.id,
                    project_id=project_id,
                    period=proposal.get("period", date.today().strftime("%Y-W%W")),
                    health=proposal.get("health", "unknown"),
                    summary=proposal.get("summary", action.explanation if hasattr(action, "explanation") else None),
                    status="draft",
                    author_employee_id=await resolve_employee_id(db, user),
                )
            )
        elif action.action_type == "draft_risk":
            db.add(
                m.ProjectRisk(
                    tenant_id=user.tenant_id,
                    created_by_id=user.id,
                    project_id=project_id,
                    title=proposal.get("title", "AI-suggested risk"),
                    description=proposal.get("description"),
                    probability=as_decimal(proposal.get("probability", 1)),
                    impact=as_decimal(proposal.get("impact", 1)),
                    score=as_decimal(proposal.get("score", 1)),
                    status="identified",
                )
            )
        elif action.action_type == "draft_issue":
            db.add(
                m.ProjectIssue(
                    tenant_id=user.tenant_id,
                    created_by_id=user.id,
                    project_id=project_id,
                    title=proposal.get("title", "AI-suggested issue"),
                    description=proposal.get("description"),
                    severity=proposal.get("severity", "medium"),
                    status="open",
                )
            )
        elif action.action_type == "draft_work_item":
            board = await _ensure_default_board(db, user, project_id)
            db.add(
                m.Task(
                    tenant_id=user.tenant_id,
                    created_by_id=user.id,
                    project_id=project_id,
                    title=proposal.get("title", "AI-suggested work item"),
                    number=await sequence_number(db, user, "work_item", "PRJ-T"),
                    description=proposal.get("description"),
                    status="backlog",
                    board_id=board.id,
                    board_column_id=await _default_column_id(db, board, "backlog"),
                )
            )
        action.executed_at = utcnow()
        action.on_behalf_of_id = action.requested_by_id
    if event == "reverse":
        action.reversal_reference = payload.reversal_reference or f"reversal:{uuid4().hex}"
    action.status = target
    await db.flush()
    await _write_audit(
        db,
        user,
        request,
        "ai_action",
        action.id,
        f"ai_action.{event}",
        changes,
        on_behalf_of=action.requested_by_id if event == "execute" else None,
    )
    await enqueue_event(
        db,
        user,
        f"ai_action.{target}",
        {"ai_action_id": str(action.id), "action_type": action.action_type},
        correlation_id=request.headers.get("x-correlation-id"),
    )
    return action


@router.post("/ai/actions/{action_id}/review", response_model=AiActionReadSchema)
async def review_ai_action(
    action_id: UUID,
    payload: AiActionDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.ai.review")),
    db: AsyncSession = Depends(get_db),
):
    action = await _ai_action_transition(db, user, request, action_id, "review", payload)
    await db.commit()
    await db.refresh(action)
    return _serialize(m.ProjectAiAction, action, user)


@router.post("/ai/actions/{action_id}/reject", response_model=AiActionReadSchema)
async def reject_ai_action(
    action_id: UUID,
    payload: AiActionDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.ai.review")),
    db: AsyncSession = Depends(get_db),
):
    action = await _ai_action_transition(db, user, request, action_id, "reject", payload)
    await db.commit()
    await db.refresh(action)
    return _serialize(m.ProjectAiAction, action, user)


@router.post("/ai/actions/{action_id}/execute", response_model=AiActionReadSchema)
async def execute_ai_action(
    action_id: UUID,
    payload: AiActionDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.ai.execute")),
    db: AsyncSession = Depends(get_db),
):
    action = await _ai_action_transition(db, user, request, action_id, "execute", payload)
    await db.commit()
    await db.refresh(action)
    return _serialize(m.ProjectAiAction, action, user)


@router.post("/ai/actions/{action_id}/reverse", response_model=AiActionReadSchema)
async def reverse_ai_action(
    action_id: UUID,
    payload: AiActionDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.ai.reverse")),
    db: AsyncSession = Depends(get_db),
):
    action = await _ai_action_transition(db, user, request, action_id, "reverse", payload)
    await db.commit()
    await db.refresh(action)
    return _serialize(m.ProjectAiAction, action, user)


@router.post("/automation/runs", response_model=list[AutomationRunReadSchema], status_code=201)
async def run_automation(
    payload: AutomationRunRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.automation.run")),
    db: AsyncSession = Depends(get_db),
):
    runs = await run_automation_rules(db, user, payload.trigger_entity, payload.trigger_id)
    await _write_audit(
        db,
        user,
        request,
        "automation_run",
        payload.trigger_id,
        "run",
        payload.model_dump(),
    )
    await db.commit()
    return [_serialize(m.ProjectAutomationRun, run, user) for run in runs]


@router.get("/outbox/stats")
async def outbox_stats(
    user: User = Depends(require_permissions("projects.outbox.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(m.ProjectOutboxEvent.status, func.count()).group_by(m.ProjectOutboxEvent.status)
    if user.tenant_id:
        stmt = stmt.where(m.ProjectOutboxEvent.tenant_id == user.tenant_id)
    counts = dict((await db.execute(stmt)).all())
    return {
        "pending": int(counts.get("pending", 0)),
        "published": int(counts.get("published", 0)),
        "failed": int(counts.get("failed", 0)),
    }


@router.post("/outbox/dispatch")
async def dispatch_project_outbox(
    limit: int = Query(50, ge=1, le=200),
    request: Request = None,
    user: User = Depends(require_permissions("projects.outbox.dispatch")),
    db: AsyncSession = Depends(get_db),
):
    result = await dispatch_outbox(db, limit)
    if request is not None:
        await record_audit(
            db,
            user=user,
            action="dispatch",
            module="projects",
            entity="outbox_event",
            changes=result,
            request=request,
        )
    await db.commit()
    return result


@router.post("/projects/{project_id}/hold", response_model=ProjectReadSchema)
async def hold_project(
    project_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.project.update")),
    db: AsyncSession = Depends(get_db),
):
    payload.event = "hold"
    item = await _transition(db, user, request, m.Project, project_id, "project", payload, "project")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Project, item, user)


@router.post("/projects/{project_id}/cancel", response_model=ProjectReadSchema)
async def cancel_project(
    project_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.project.update")),
    db: AsyncSession = Depends(get_db),
):
    approval = await db.scalar(
        select(m.ProjectApproval).where(
            m.ProjectApproval.entity_type == "project",
            m.ProjectApproval.entity_id == project_id,
            m.ProjectApproval.approval_type == "cancellation",
            m.ProjectApproval.status == "approved",
        )
    )
    if approval is None:
        raise ConflictError("Cancelling a project requires an approved cancellation")
    payload.event = "cancel"
    item = await _transition(db, user, request, m.Project, project_id, "project", payload, "project")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.Project, item, user)


@router.patch("/projects/{project_id}/health", response_model=ProjectReadSchema)
async def update_project_health(
    project_id: UUID,
    payload: dict[str, Any],
    request: Request,
    user: User = Depends(require_permissions("projects.project.update")),
    db: AsyncSession = Depends(get_db),
):
    project = await get_or_404(db, user, m.Project, project_id)
    health = str(payload.get("health") or "").strip().lower()
    if health not in ("green", "amber", "red", "unknown"):
        raise ValidationError("health must be green, amber, red, or unknown")
    project.health = health
    project.health_reason = payload.get("health_reason")
    project.version = int(project.version or 1) + 1
    await db.flush()
    await _write_audit(db, user, request, "project", project.id, "health.update", payload)
    await db.commit()
    await db.refresh(project)
    return _serialize(m.Project, project, user)


@router.get("/projects/{project_id}/backlog", response_model=list[TaskReadSchema])
async def get_backlog(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.workitem.read")),
    db: AsyncSession = Depends(get_db),
):
    await get_or_404(db, user, m.Project, project_id)
    stmt = select(m.Task).where(m.Task.project_id == project_id, m.Task.is_active.is_(True))
    if user.tenant_id and not user.is_superuser:
        stmt = stmt.where(m.Task.tenant_id == user.tenant_id)
    items = list((await db.scalars(stmt.order_by(m.Task.rank, m.Task.number))).all())
    return [_serialize(m.Task, item, user) for item in items]


@router.patch("/projects/{project_id}/backlog", response_model=list[TaskReadSchema])
async def patch_backlog(
    project_id: UUID,
    payload: BacklogUpdate,
    request: Request,
    user: User = Depends(require_permissions("projects.workitem.update")),
    db: AsyncSession = Depends(get_db),
):
    project = await get_or_404(db, user, m.Project, project_id)
    items = await wf.reorder_backlog(db, user, project, payload.moves)
    await _write_audit(
        db,
        user,
        request,
        "project",
        project.id,
        "backlog.reordered",
        {"moves": [move.model_dump(mode="json") for move in payload.moves]},
    )
    await db.commit()
    for item in items:
        await db.refresh(item)
    return [_serialize(m.Task, item, user) for item in items]


@router.get("/work-items/search", response_model=list[TaskReadSchema])
async def search_work_items(
    dsl_filter: str = Query(..., alias="filter"),
    limit: int = Query(100, ge=1, le=500),
    user: User = Depends(require_permissions("projects.workitem.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(m.Task).where(m.Task.is_active.is_(True))
    if user.tenant_id and not user.is_superuser:
        stmt = stmt.where(m.Task.tenant_id == user.tenant_id)
    stmt = apply_filter(stmt, "Task", dsl_filter, user).limit(limit)
    items = list((await db.scalars(stmt)).all())
    return [_serialize(m.Task, item, user) for item in items]


@router.post("/work-items/{item_id}/links", response_model=dict[str, Any], status_code=201)
async def create_work_item_link(
    item_id: UUID,
    payload: WorkItemLinkCreate,
    request: Request,
    user: User = Depends(require_permissions("projects.workitem.update")),
    db: AsyncSession = Depends(get_db),
):
    link = await wf.create_work_item_link(db, user, item_id, payload)
    await _write_audit(db, user, request, "work_item", item_id, "link.create", payload.model_dump())
    await enqueue_event(
        db,
        user,
        "work_item.linked",
        {"work_item_id": str(item_id), "linked_work_item_id": str(payload.linked_work_item_id)},
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await db.refresh(link)
    result = _serialize(m.ProjectWorkItemLink, link, user)
    await db.commit()
    return result


@router.delete("/work-items/{item_id}/links/{link_id}", response_model=dict[str, Any])
async def delete_work_item_link(
    item_id: UUID,
    link_id: UUID,
    request: Request,
    user: User = Depends(require_permissions("projects.workitem.update")),
    db: AsyncSession = Depends(get_db),
):
    await wf.delete_work_item_link(db, user, item_id, link_id)
    await _write_audit(db, user, request, "work_item", item_id, "link.delete", {})
    await db.commit()
    return {"id": str(link_id), "work_item_id": str(item_id), "deleted": True}


@router.post("/work-items/{item_id}/comments", response_model=dict[str, Any], status_code=201)
async def create_work_item_comment(
    item_id: UUID,
    payload: CommentCreate,
    request: Request,
    user: User = Depends(require_permissions("projects.comment.create")),
    db: AsyncSession = Depends(get_db),
):
    project_id = await wf.entity_project_id(db, user, "work_item", item_id)
    comment = await wf.create_comment(db, user, "work_item", item_id, payload, project_id)
    await _write_audit(db, user, request, "comment", comment.id, "create", payload.model_dump())
    await db.refresh(comment)
    result = _serialize(m.ProjectComment, comment, user)
    await db.commit()
    return result


@router.patch("/comments/{comment_id}", response_model=dict[str, Any])
async def update_work_item_comment(
    comment_id: UUID,
    payload: CommentUpdate,
    request: Request,
    user: User = Depends(require_permissions("projects.comment.update")),
    db: AsyncSession = Depends(get_db),
):
    comment = await wf.update_comment(db, user, comment_id, payload)
    await _write_audit(db, user, request, "comment", comment.id, "update", payload.model_dump())
    await db.refresh(comment)
    result = _serialize(m.ProjectComment, comment, user)
    await db.commit()
    return result


@router.post("/sprints/{item_id}/start", response_model=SprintReadSchema)
async def start_sprint(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.sprint.update")),
    db: AsyncSession = Depends(get_db),
):
    payload.event = "start"
    item = await _transition(db, user, request, m.ProjectSprint, item_id, "sprint", payload, "sprint")
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectSprint, item, user)


@router.post("/sprints/{item_id}/complete", response_model=SprintMetrics)
async def complete_sprint(
    item_id: UUID,
    payload: SprintCompleteRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.sprint.update")),
    db: AsyncSession = Depends(get_db),
):
    sprint = await get_or_404(db, user, m.ProjectSprint, item_id)
    metrics = await wf.complete_sprint(db, user, sprint, payload)
    await _write_audit(
        db, user, request, "sprint", sprint.id, "sprint.complete", metrics.model_dump(mode="json")
    )
    await enqueue_event(
        db,
        user,
        "sprint.completed",
        {
            "sprint_id": str(sprint.id),
            "project_id": str(sprint.project_id),
            "velocity": str(metrics.velocity),
            "carryover": metrics.carryover,
        },
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await run_automation_rules(db, user, "sprint.completed", sprint.id, sprint.project_id)
    await db.commit()
    return metrics


@router.post("/milestones/{item_id}/accept", response_model=MilestoneReadSchema)
async def accept_milestone(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.milestone.update")),
    db: AsyncSession = Depends(get_db),
):
    payload.event = "accept"
    item = await _transition(
        db, user, request, m.ProjectMilestone, item_id, "milestone", payload, "milestone"
    )
    item.accepted_by_id = user.id
    item.accepted_at = utcnow()
    await db.flush()
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectMilestone, item, user)


@router.get("/projects/{project_id}/gantt", response_model=Any)
async def project_gantt(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.schedule.read")),
    db: AsyncSession = Depends(get_db),
):
    return (await wf.gantt_data(db, user, project_id)).model_dump(mode="json")


@router.post("/projects/{project_id}/baselines", response_model=dict[str, Any], status_code=201)
async def create_project_baseline(
    project_id: UUID,
    payload: BaselineCreate,
    request: Request,
    user: User = Depends(require_permissions("projects.schedule.update")),
    db: AsyncSession = Depends(get_db),
):
    project = await get_or_404(db, user, m.Project, project_id)
    baseline = await wf.create_baseline(db, user, project, payload)
    await _write_audit(db, user, request, "baseline", baseline.id, "create", payload.model_dump())
    await enqueue_event(
        db,
        user,
        "baseline.created",
        {"baseline_id": str(baseline.id), "project_id": str(project_id)},
        correlation_id=request.headers.get("x-correlation-id"),
    )
    await db.refresh(baseline)
    result = _serialize(m.ProjectBaseline, baseline, user)
    await db.commit()
    return result


@router.get("/projects/{project_id}/schedule-variance", response_model=list[ScheduleVarianceRow])
async def project_schedule_variance(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.schedule.read")),
    db: AsyncSession = Depends(get_db),
):
    return await wf.schedule_variance(db, user, project_id)


@router.get("/projects/{project_id}/unbilled", response_model=UnbilledReport)
async def project_unbilled(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.billing.read")),
    db: AsyncSession = Depends(get_db),
):
    project = await get_or_404(db, user, m.Project, project_id)
    return await wf.unbilled_report(db, user, project)


@router.get("/projects/{project_id}/costs", response_model=list[CostRow])
async def project_costs(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.finance.read")),
    db: AsyncSession = Depends(get_db),
):
    rows = await wf.project_costs(db, user, project_id)
    return [CostRow.model_validate(mask_sensitive("CostRow", row, user)) for row in rows]


@router.get("/projects/{project_id}/profitability", response_model=list[ProfitabilitySummary])
async def project_profitability(
    project_id: UUID,
    user: User = Depends(require_permissions("projects.finance.read")),
    db: AsyncSession = Depends(get_db),
):
    return await profitability_report(project_id=project_id, user=user, db=db)


@router.post("/billing-runs/{item_id}/review", response_model=BillingRunReadSchema)
async def review_billing_run(
    item_id: UUID,
    payload: BillingReviewRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.billing.update")),
    db: AsyncSession = Depends(get_db),
):
    run = await get_or_404(db, user, m.ProjectBillingRun, item_id)
    result = await wf.review_billing_run(db, user, run, payload.tax_code)
    await _write_audit(db, user, request, "billing_run", run.id, "review", result)
    await db.commit()
    await db.refresh(run)
    return _serialize(m.ProjectBillingRun, run, user)


@router.post("/billing-runs/{item_id}/approve", response_model=BillingRunReadSchema)
async def approve_billing_run(
    item_id: UUID,
    payload: TransitionRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.billing.approve")),
    db: AsyncSession = Depends(get_db),
):
    payload.event = "approve"
    item = await _transition(
        db, user, request, m.ProjectBillingRun, item_id, "billing_run", payload, "billing_run"
    )
    await db.commit()
    await db.refresh(item)
    return _serialize(m.ProjectBillingRun, item, user)


@router.get("/reports/{key}", response_model=ReportResponse)
async def named_report(
    key: str,
    project_id: Optional[UUID] = None,
    user: User = Depends(require_permissions("projects.report.read")),
    db: AsyncSession = Depends(get_db),
):
    return await wf.run_report(db, user, key, project_id)


@router.get("/ai/signals", response_model=list[AiSignalReadSchema])
async def list_ai_signals(
    project_id: Optional[UUID] = None,
    user: User = Depends(require_permissions("projects.ai.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(m.ProjectAiSignal)
    if user.tenant_id and not user.is_superuser:
        stmt = stmt.where(m.ProjectAiSignal.tenant_id == user.tenant_id)
    if project_id:
        stmt = stmt.where(m.ProjectAiSignal.entity_id == project_id)
    rows = list((await db.scalars(stmt.order_by(m.ProjectAiSignal.created_at.desc()))).all())
    return [_serialize(m.ProjectAiSignal, row, user) for row in rows]


@router.get("/ai/actions", response_model=list[AiActionReadSchema])
async def list_ai_actions(
    project_id: Optional[UUID] = None,
    user: User = Depends(require_permissions("projects.ai.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(m.ProjectAiAction)
    if user.tenant_id and not user.is_superuser:
        stmt = stmt.where(m.ProjectAiAction.tenant_id == user.tenant_id)
    if project_id:
        stmt = stmt.where(m.ProjectAiAction.entity_id == project_id)
    rows = list((await db.scalars(stmt.order_by(m.ProjectAiAction.created_at.desc()))).all())
    return [_serialize(m.ProjectAiAction, row, user) for row in rows]


@router.post("/imports", response_model=dict[str, Any], status_code=201)
async def stage_import(
    payload: ImportSubmit,
    request: Request,
    user: User = Depends(require_permissions("projects.settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    batch = await wf.stage_import(db, user, payload)
    await _write_audit(
        db, user, request, "import_batch", batch.id, "create", {"provider": payload.provider}
    )
    await db.refresh(batch)
    result = _serialize(m.ProjectImportBatch, batch, user)
    await db.commit()
    return result


@router.get("/imports/{batch_id}", response_model=dict[str, Any])
async def get_import_batch(
    batch_id: UUID,
    user: User = Depends(require_permissions("projects.import.read")),
    db: AsyncSession = Depends(get_db),
):
    batch = await get_or_404(db, user, m.ProjectImportBatch, batch_id)
    return _serialize(m.ProjectImportBatch, batch, user)


@router.post("/imports/{batch_id}/approve", response_model=dict[str, Any])
async def approve_import(
    batch_id: UUID,
    payload: ImportMappingDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    batch = await get_or_404(db, user, m.ProjectImportBatch, batch_id)
    batch = await wf.approve_import(db, user, batch, payload)
    await _write_audit(db, user, request, "import_batch", batch.id, "approve", payload.model_dump())
    await db.refresh(batch)
    result = _serialize(m.ProjectImportBatch, batch, user)
    await db.commit()
    return result


@router.post("/imports/{batch_id}/commit", response_model=dict[str, Any])
async def commit_import(
    batch_id: UUID,
    request: Request,
    user: User = Depends(require_permissions("projects.settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    batch = await get_or_404(db, user, m.ProjectImportBatch, batch_id)
    batch = await wf.commit_import(db, user, batch)
    await _write_audit(db, user, request, "import_batch", batch.id, "commit", {})
    await db.refresh(batch)
    result = _serialize(m.ProjectImportBatch, batch, user)
    await db.commit()
    return result


@router.post("/imports/{batch_id}/rollback", response_model=dict[str, Any])
async def rollback_import(
    batch_id: UUID,
    request: Request,
    user: User = Depends(require_permissions("projects.settings.manage")),
    db: AsyncSession = Depends(get_db),
):
    batch = await get_or_404(db, user, m.ProjectImportBatch, batch_id)
    batch = await wf.rollback_import(db, user, batch)
    await _write_audit(db, user, request, "import_batch", batch.id, "rollback", {})
    await db.refresh(batch)
    result = _serialize(m.ProjectImportBatch, batch, user)
    await db.commit()
    return result


@router.post("/intake", response_model=dict[str, Any], status_code=201)
async def submit_intake(
    payload: IntakeSubmit,
    request: Request,
    user: User = Depends(require_permissions("projects.project.create")),
    db: AsyncSession = Depends(get_db),
):
    approval = await wf.submit_intake(db, user, payload)
    await _write_audit(db, user, request, "approval", approval.id, "intake.submit", payload.model_dump())
    await db.refresh(approval)
    result = _serialize(m.ProjectApproval, approval, user)
    await db.commit()
    return result


@router.post("/intake/{approval_id}/decide", response_model=ProjectReadSchema)
async def decide_intake(
    approval_id: UUID,
    payload: IntakeDecision,
    request: Request,
    user: User = Depends(require_permissions("projects.approval.update")),
    db: AsyncSession = Depends(get_db),
):
    approval = await get_or_404(db, user, m.ProjectApproval, approval_id)
    project = await wf.decide_intake(db, user, approval, payload)
    await _write_audit(db, user, request, "project", project.id, "intake.decide", payload.model_dump())
    await db.commit()
    await db.refresh(project)
    return _serialize(m.Project, project, user)


@router.post("/notifications", response_model=dict[str, Any], status_code=201)
async def send_project_notification(
    payload: NotificationRequest,
    request: Request,
    user: User = Depends(require_permissions("projects.comment.create")),
    db: AsyncSession = Depends(get_db),
):
    activity = await wf.send_notification(db, user, payload)
    await _write_audit(
        db, user, request, "project_activity", activity.id, "notification.send", payload.model_dump()
    )
    await db.refresh(activity)
    result = _serialize(m.ProjectActivity, activity, user)
    await db.commit()
    return result


def week_start_date(value: date) -> date:
    return value - timedelta(days=value.weekday())


def _include(
    model: Any,
    path: str,
    permission: str,
    entity: str,
    *,
    search_fields: tuple[str, ...] = (),
    filter_fields: tuple[str, ...] = (),
    number_field: Optional[str] = None,
    number_prefix: Optional[str] = None,
    base_path: str = "",
) -> None:
    immutable = model.__name__ in IMMUTABLE_MODELS

    async def update_guard(
        db: AsyncSession, user: User, item_id: str, raw_body: dict[str, Any]
    ) -> None:
        obj = await get_or_404(db, user, model, UUID(str(item_id)))
        legacy_submit = (
            model is m.ProjectTimesheet
            and raw_body == {"status": "submitted"}
            and obj.status == "draft"
        )
        guard_update_fields(model.__name__, {} if legacy_submit else raw_body)
        guard_immutable(model.__name__, obj)
        await guard_resource_scope(db, user, model.__name__, obj)
        if not legacy_submit and "status" in raw_body:
            raise ForbiddenError("Status changes must use a dedicated transition endpoint")
        if model in (m.Task,) and "parent_work_item_id" in raw_body:
            parent_id = raw_body.get("parent_work_item_id")
            if parent_id:
                await assert_no_parent_cycle(db, obj.id, UUID(str(parent_id)))
                children = await db.scalar(
                    select(func.count())
                    .select_from(m.Task)
                    .where(
                        m.Task.parent_work_item_id == obj.id,
                        m.Task.is_active.is_(True),
                    )
                )
                if children:
                    raise ConflictError("A work item with subtasks cannot become a subtask")
        if legacy_submit:
            obj.status = "submitted"
            await db.flush()

    async def delete_guard(db: AsyncSession, user: User, item_id: str) -> None:
        obj = await get_or_404(db, user, model, UUID(str(item_id)))
        guard_immutable(model.__name__, obj)
        await guard_resource_scope(db, user, model.__name__, obj)

    child, _ = build_crud_router(
        model=model,
        read_schema=schema_for(model, "read"),
        create_schema=schema_for(model, "create"),
        update_schema=schema_for(model, "update"),
        prefix=path,
        tags=["Project Management"],
        permission_prefix=permission,
        module="projects",
        entity=entity,
        search_fields=search_fields,
        filter_fields=filter_fields,
        number_field=number_field,
        number_prefix=number_prefix,
        serializer=lambda obj, user, model=model: _serialize(model, obj, user),
        base_path=base_path,
        immutable=immutable,
        update_guard=update_guard,
        delete_guard=delete_guard,
        idempotency_hooks=(idempotency_lookup, idempotency_store),
    )
    router.include_router(child)


_include(m.Task, "/tasks", "projects.task", "task", search_fields=("title", "number"), filter_fields=("project_id", "status", "assignee_id", "sprint_id"), number_field="number", number_prefix="PRJ-T")
_include(m.ProjectPortfolio, "/portfolios", "projects.portfolio", "portfolio", search_fields=("name", "code"), filter_fields=("status", "health"))
_include(m.ProjectProgram, "/programs", "projects.program", "program", search_fields=("name", "code"), filter_fields=("status", "portfolio_id"))
_include(m.ProjectPhase, "/phases", "projects.phase", "phase", search_fields=("name",), filter_fields=("project_id", "status"))
_include(m.ProjectSprint, "/sprints", "projects.sprint", "sprint", search_fields=("name", "number"), filter_fields=("project_id", "status"), number_field="number", number_prefix="SPR")
_include(m.ProjectBoard, "/boards", "projects.board", "board", search_fields=("name",), filter_fields=("project_id", "status"))
_include(m.ProjectBoardColumn, "/board-columns", "projects.boardcolumn", "board_column", search_fields=("name",), filter_fields=("board_id", "status_category"))
_include(m.Task, "/work-items", "projects.workitem", "work_item", search_fields=("title", "number"), filter_fields=("project_id", "status", "work_item_type", "assignee_id", "sprint_id", "board_id"), number_field="number", number_prefix="PRJ-T")
_include(m.ProjectWorkItemLink, "/work-item-links", "projects.workitemlink", "work_item_link", filter_fields=("work_item_id", "linked_work_item_id", "link_type"))
_include(m.ProjectLabel, "/labels", "projects.label", "label", search_fields=("name",), filter_fields=("project_id", "status"))
_include(m.ProjectWorkItemLabel, "/work-item-labels", "projects.label", "work_item_label", filter_fields=("work_item_id", "label_id"))
_include(m.ProjectCustomField, "/custom-fields", "projects.customfield", "custom_field", search_fields=("label", "code"), filter_fields=("entity_type", "status"))
_include(m.ProjectWorkItemFieldValue, "/field-values", "projects.fieldvalue", "field_value", filter_fields=("work_item_id", "field_id"))
_include(m.ProjectWorkflowScheme, "/workflows", "projects.workflow", "workflow", search_fields=("name",), filter_fields=("entity_type", "status"))
_include(m.ProjectWorkflowTransition, "/transitions", "projects.transition", "workflow_transition", filter_fields=("scheme_id", "from_status", "event"))
_include(m.ProjectApproval, "/approvals", "projects.approval", "approval", filter_fields=("entity_type", "entity_id", "status", "approval_type"))
_include(m.ProjectTemplate, "/templates", "projects.template", "template", search_fields=("name",), filter_fields=("type", "status"))
_include(m.ProjectMilestone, "/milestones", "projects.milestone", "milestone", search_fields=("name",), filter_fields=("project_id", "status"))
_include(m.ProjectDependency, "/dependencies", "projects.dependency", "dependency", filter_fields=("predecessor_id", "successor_id", "status"))
_include(m.ProjectBaseline, "/baselines", "projects.baseline", "baseline", search_fields=("name",), filter_fields=("project_id", "status"))
_include(m.ProjectBaselineSnapshot, "/baseline-snapshots", "projects.baselinesnapshot", "baseline_snapshot", filter_fields=("baseline_id", "entity_type", "entity_id"))
_include(m.ProjectRelease, "/releases", "projects.release", "release", search_fields=("name",), filter_fields=("project_id", "status"))
_include(m.ProjectChangeRequest, "/change-requests", "projects.changerequest", "change_request", search_fields=("title",), filter_fields=("project_id", "status"))
_include(m.ProjectTimeEntry, "/time-entries", "projects.timeentry", "time_entry", filter_fields=("work_item_id", "employee_id", "entry_date", "status", "billable"))
_include(m.ProjectTimesheet, "/timesheets", "projects.timesheet", "timesheet", filter_fields=("employee_id", "week_start", "status"))
_include(m.ProjectTimesheetEntry, "/timesheet-entries", "projects.timesheetentry", "timesheet_entry", filter_fields=("timesheet_id", "time_entry_id"))
_include(m.ProjectExpense, "/expenses", "projects.expense", "expense", filter_fields=("project_id", "work_item_id", "category", "status"))
_include(m.ProjectCostEntry, "/cost-entries", "projects.costentry", "cost_entry", filter_fields=("project_id", "cost_type", "source"))
_include(m.ProjectBillingRun, "/billing-runs", "projects.billingrun", "billing_run", filter_fields=("project_id", "status", "period"))
_include(m.ProjectBillingLine, "/billing-lines", "projects.billingline", "billing_line", filter_fields=("billing_run_id", "source_type", "status"))
_include(m.ProjectInvoiceLink, "/invoice-links", "projects.invoicelink", "invoice_link", filter_fields=("project_id", "billing_run_id", "status"))
_include(m.ProjectBudget, "/budgets", "projects.budget", "budget", filter_fields=("project_id", "status"))
_include(m.ProjectBudgetRevision, "/budget-revisions", "projects.budgetrevision", "budget_revision", filter_fields=("budget_id", "status"))
_include(m.ProjectResourceRole, "/resource-roles", "projects.resourcerole", "resource_role", search_fields=("code", "name"), filter_fields=("status",))
_include(m.ProjectEmployeeSkill, "/employee-skills", "projects.employeeskill", "employee_skill", filter_fields=("employee_id", "skill_code"))
_include(m.ProjectCapacityCalendar, "/capacity-calendars", "projects.capacitycalendar", "capacity_calendar", filter_fields=("employee_id", "week_start"))
_include(m.ProjectResourceBooking, "/bookings", "projects.booking", "booking", filter_fields=("project_id", "employee_id", "status"))
_include(m.ProjectWorkloadSnapshot, "/workload-snapshots", "projects.workload", "workload_snapshot", filter_fields=("employee_id", "week_start", "overallocated"))
_include(m.ProjectRisk, "/risks", "projects.risk", "risk", search_fields=("title",), filter_fields=("project_id", "status", "owner_employee_id"))
_include(m.ProjectIssue, "/issues", "projects.issue", "issue", search_fields=("title",), filter_fields=("project_id", "status", "severity"))
_include(m.ProjectDecision, "/decisions", "projects.decision", "decision", search_fields=("title",), filter_fields=("project_id", "status"))
_include(m.ProjectStatusUpdate, "/status-updates", "projects.statusupdate", "status_update", filter_fields=("project_id", "period", "health"))
_include(m.ProjectGoal, "/goals", "projects.goal", "goal", search_fields=("title",), filter_fields=("project_id", "program_id", "portfolio_id", "status"))
_include(m.ProjectRetrospective, "/retrospectives", "projects.retrospective", "retrospective", filter_fields=("project_id", "sprint_id", "status"))
_include(m.ProjectComment, "/comments", "projects.comment", "comment", filter_fields=("entity_type", "entity_id", "parent_comment_id"))
_include(m.ProjectActivity, "/activities", "projects.activity", "activity", filter_fields=("entity_type", "entity_id", "action"))
_include(m.ProjectAttachment, "/attachments", "projects.attachment", "attachment", filter_fields=("entity_type", "entity_id"))
_include(m.ProjectAutomationRule, "/automation-rules", "projects.automation", "automation_rule", search_fields=("name",), filter_fields=("project_id", "status"))
_include(m.ProjectAutomationRun, "/automation-runs", "projects.automationrun", "automation_run", filter_fields=("rule_id", "status"))
_include(m.ProjectIntegration, "/integrations", "projects.integration", "integration", search_fields=("provider", "external_id"), filter_fields=("provider", "status"))
_include(m.ProjectImportBatch, "/import-batches", "projects.importbatch", "import_batch", filter_fields=("provider", "status"))
_include(m.ProjectAiSignal, "/ai-signals", "projects.aisignal", "ai_signal", filter_fields=("entity_type", "entity_id", "signal_type", "review_status"))
_include(m.ProjectAiAction, "/ai-actions", "projects.aiaction", "ai_action", filter_fields=("action_type", "entity_type", "entity_id", "status"))
_include(m.ProjectOutboxEvent, "/outbox", "projects.outbox", "outbox_event", filter_fields=("event_name", "status"))
_include(m.Project, "", "projects.project", "project", search_fields=("name", "code", "number"), filter_fields=("status", "health", "priority", "portfolio_id", "program_id"), number_field="number", number_prefix="PRJ", base_path="/")
