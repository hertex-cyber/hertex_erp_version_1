import math
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import Integer, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.core.numbering import next_number as legacy_next_number
from app.modules.finance.service import create_invoice_from_proposal
from app.modules.hr.models import Employee, LeaveRequest
from app.modules.identity.models import User
from app.modules.projects import models as m
from app.modules.projects.schemas import (
    SENSITIVE_UPDATE_FIELDS,
    BillingLinePreview,
    BillingPreview,
    CapacityRow,
    CriticalPathResponse,
    CriticalPathStep,
    WorkloadRow,
)
from app.modules.settings.models import NumberSequence

SENSITIVE_FIELDS = {
    "Project": {
        "budget",
        "budget_hours",
        "budget_cost",
        "budget_revenue",
        "contract_value",
        "total_billed",
        "total_cost",
        "total_expense",
        "wip_amount",
        "margin_amount",
        "margin_percent",
    },
    "Task": {
        "billable_rate",
        "budget_amount",
        "actual_cost",
        "actual_revenue",
        "billable_amount",
        "invoiced_amount",
    },
    "ProjectTimeEntry": {"billable_rate", "cost_rate"},
    "ProjectResourceRole": {"default_cost_rate", "default_billable_rate"},
    "ProjectBillingRun": {"gross_amount", "tax_amount"},
    "ProjectBillingLine": {"quantity", "rate", "amount"},
    "ProjectBudget": {"budget_hours", "budget_cost", "budget_revenue"},
    "ProjectInvoiceLink": {"amount"},
    "ProjectSummary": {"billable_value", "actual_hours"},
    "ProfitabilitySummary": {
        "budget_revenue", "budget_cost", "billed", "labour_cost", "expense_cost",
        "other_cost", "wip", "margin_amount", "margin_percent",
    },
    "BillingPreview": {"gross_amount", "tax_amount", "total_amount"},
    "BillingLinePreview": {"rate", "amount"},
    "ProjectAiSignal": {"features_json"},
}

IMMUTABLE_MODELS = {
    "ProjectBaseline",
    "ProjectBaselineSnapshot",
    "ProjectInvoiceLink",
    "ProjectActivity",
    "ProjectOutboxEvent",
    "ProjectAiAction",
}
CONDITIONALLY_IMMUTABLE = {
    "ProjectTimesheet": ("status", "approved"),
    "ProjectTimeEntry": ("status", "invoiced"),
    "ProjectBillingRun": ("status", "invoiced"),
    "ProjectBillingLine": ("status", "invoiced"),
    "ProjectApproval": ("status", "approved"),
    "ProjectSprint": ("status", "completed"),
}
PROHIBITED_AI_ACTIONS = {
    "auto_close_work_item", "close_work_item", "approve_timesheet", "approve_time",
    "post_invoice", "post_billing", "change_baseline", "book_capacity",
    "send_notification", "deny_leave", "change_access", "terminate_employee",
}
SCOPE_BYPASS_ROLES = {"superadmin", "tenant_admin", "projects", "manager", "finance"}
DONE_STATUSES = {"done", "accepted", "closed", "cancelled", "paid", "invoiced"}
IDEMPOTENCY_EVENT_PREFIX = "idempotency:"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_decimal(value: Any) -> Decimal:
    return Decimal(str(value or 0))


def mask_sensitive(model_name: str, data: dict[str, Any], user: User) -> dict[str, Any]:
    if user.is_superuser or user.has_permission("projects.finance.read"):
        return data
    numeric_reports = {
        "ProjectSummary", "ProfitabilitySummary", "BillingPreview", "BillingLinePreview",
    }
    masked_value = Decimal("0") if model_name in numeric_reports else None
    for field in SENSITIVE_FIELDS.get(model_name, set()):
        if field in data:
            data[field] = masked_value
    if model_name == "Project" and isinstance(data.get("tasks"), list):
        data["tasks"] = [mask_sensitive("Task", task, user) for task in data["tasks"]]
    if model_name == "BillingPreview" and isinstance(data.get("lines"), list):
        data["lines"] = [mask_sensitive("BillingLinePreview", line, user) for line in data["lines"]]
    return data


def guard_update_fields(model_name: str, data: dict[str, Any]) -> None:
    forbidden = sorted(set(data) & SENSITIVE_UPDATE_FIELDS)
    if forbidden:
        raise ForbiddenError(
            f"{model_name} fields are derived or controlled by dedicated endpoints: "
            + ", ".join(forbidden)
        )


def guard_immutable(model_name: str, obj: Any) -> None:
    if model_name in IMMUTABLE_MODELS:
        raise ForbiddenError(f"{model_name} records are immutable")
    if model_name == "ProjectTimeEntry" and getattr(obj, "status", None) in ("approved", "invoiced"):
        raise ForbiddenError("ProjectTimeEntry records are immutable after creation")
    condition = CONDITIONALLY_IMMUTABLE.get(model_name)
    if condition and getattr(obj, condition[0], None) == condition[1]:
        raise ForbiddenError(f"{model_name} records are immutable in the current state")


def guard_baseline_immutable(obj: Any) -> None:
    if obj.__class__.__name__ in ("ProjectBaseline", "ProjectBaselineSnapshot"):
        raise ForbiddenError("Approved baselines and their snapshots are immutable")


async def guard_resource_scope(db: AsyncSession, user: User, model_name: str, obj: Any) -> None:
    if user.is_superuser or any(role.slug in SCOPE_BYPASS_ROLES for role in user.roles):
        return
    if model_name not in ("Task", "ProjectTimeEntry", "ProjectTimesheet"):
        return
    owner_id = getattr(obj, "employee_id", None) or getattr(obj, "assignee_id", None)
    if owner_id is None:
        raise ForbiddenError("Ownership is required for this resource")
    own_id = await resolve_employee_id(db, user)
    if own_id is None or owner_id != own_id:
        raise ForbiddenError("You may only modify resources assigned to you")


async def _completion_waiver_approval(
    db: AsyncSession,
    project: Any,
    *,
    waiver_code: str | None,
    waiver_approval_id: UUID | None,
) -> Any:
    stmt = select(m.ProjectApproval).where(
        m.ProjectApproval.entity_type == "project",
        m.ProjectApproval.entity_id == project.id,
        m.ProjectApproval.approval_type == "completion_waiver",
        m.ProjectApproval.status == "approved",
    )
    if getattr(project, "tenant_id", None) is not None:
        stmt = stmt.where(m.ProjectApproval.tenant_id == project.tenant_id)
    approvals = list((await db.scalars(stmt)).all())
    matches = []
    for approval in approvals:
        if waiver_approval_id is not None and approval.id != waiver_approval_id:
            continue
        if waiver_code is not None and waiver_code not in (approval.comments or ""):
            continue
        matches.append(approval)
    if not matches:
        raise ConflictError(
            "Project completion blockers require an approved completion waiver with a valid "
            "waiver code or approval ID"
        )
    return matches[0]


async def guard_project_completion(
    db: AsyncSession,
    project: Any,
    *,
    user: User | None = None,
    waiver_code: str | None = None,
    waiver_approval_id: UUID | None = None,
) -> None:
    violations: list[str] = []
    blocking = select(func.count()).select_from(m.Task).where(
        m.Task.project_id == project.id,
        m.Task.is_active.is_(True),
        m.Task.status.notin_(DONE_STATUSES),
        or_(
            m.Task.status == "blocked",
            m.Task.priority.in_(("high", "critical")),
        ),
    )
    if await db.scalar(blocking):
        violations.append("open blocking work items")
    milestones = select(func.count()).select_from(m.ProjectMilestone).where(
        m.ProjectMilestone.project_id == project.id,
        m.ProjectMilestone.status != "accepted",
        m.ProjectMilestone.amount > 0,
    )
    if await db.scalar(milestones):
        violations.append("unaccepted critical milestones")
    unbilled = (
        select(func.count())
        .select_from(m.ProjectTimeEntry)
        .join(m.Task, m.Task.id == m.ProjectTimeEntry.work_item_id)
        .where(
            m.Task.project_id == project.id,
            m.ProjectTimeEntry.status == "approved",
            m.ProjectTimeEntry.invoice_link_id.is_(None),
        )
    )
    if await db.scalar(unbilled):
        violations.append("approved unbilled time")
    if not violations:
        return
    if waiver_code is None and waiver_approval_id is None:
        raise ConflictError(
            "Project has " + ", ".join(violations) + "; an approved completion waiver is required",
            extra={"violations": violations},
        )
    approval = await _completion_waiver_approval(
        db,
        project,
        waiver_code=waiver_code,
        waiver_approval_id=waiver_approval_id,
    )
    if user is not None:
        await record_activity(
            db,
            user,
            "project",
            project.id,
            "project.completion_waived",
            {
                "violations": violations,
                "waiver_code": waiver_code,
                "waiver_approval_id": str(approval.id),
            },
        )


async def guard_self_approval(
    db: AsyncSession,
    user: User,
    *,
    entity_type: str,
    entity_id: UUID,
    owner_employee_id: Optional[UUID] = None,
    delegated: bool = False,
) -> None:
    own_id = await resolve_employee_id(db, user)
    if owner_employee_id is None or own_id is None or owner_employee_id != own_id:
        return
    if delegated:
        return
    delegation = select(func.count()).select_from(m.ProjectApproval).where(
        m.ProjectApproval.entity_type == entity_type,
        m.ProjectApproval.entity_id == entity_id,
        m.ProjectApproval.approval_type == "delegation",
        m.ProjectApproval.status == "approved",
        m.ProjectApproval.approver_employee_id == own_id,
    )
    if await db.scalar(delegation):
        return
    raise ConflictError("Self-approval is not permitted unless the approval is delegated")


async def guard_reviewer_not_assignee(
    db: AsyncSession,
    user: User,
    work_item: Any,
    *,
    delegated: bool = False,
) -> None:
    own_id = await resolve_employee_id(db, user)
    if own_id is None or work_item.employee_id is None or own_id != work_item.employee_id:
        return
    if delegated:
        return
    delegation = select(func.count()).select_from(m.ProjectApproval).where(
        m.ProjectApproval.entity_type == "work_item",
        m.ProjectApproval.entity_id == work_item.id,
        m.ProjectApproval.approval_type == "delegation",
        m.ProjectApproval.status == "approved",
        m.ProjectApproval.approver_employee_id == own_id,
    )
    if await db.scalar(delegation):
        return
    raise ConflictError("The assignee cannot mark a reviewed work item done")


async def guard_subtask_completion(db: AsyncSession, work_item: Any) -> None:
    children = (
        select(func.count())
        .select_from(m.Task)
        .where(
            m.Task.parent_work_item_id == work_item.id,
            m.Task.is_active.is_(True),
            m.Task.status.notin_(DONE_STATUSES),
        )
    )
    if await db.scalar(children):
        raise ConflictError("Required subtasks must be done before the parent can be completed")


async def guard_wip_limit(
    db: AsyncSession,
    column: Any,
    occupant_count: int,
    *,
    user: Optional[User] = None,
    entity_id: Optional[UUID] = None,
) -> None:
    limit = int(getattr(column, "wip_limit", 0) or 0)
    if limit <= 0 or occupant_count < limit:
        return
    if bool(getattr(column, "wip_enforced", False)):
        raise ConflictError("WIP limit reached for this board column")
    if user is not None and entity_id is not None:
        await record_activity(
            db,
            user,
            "board_column",
            column.id,
            "wip.limit.exceeded",
            {"wip_limit": limit, "work_item_id": str(entity_id)},
        )


async def guard_capacity_override(db: AsyncSession, user: User, booking: Any) -> None:
    if bool(getattr(booking, "capacity_override", False)):
        if not (getattr(booking, "override_reason", None) or "").strip():
            raise ConflictError("A capacity override requires a reason")
        return
    employee = await db.scalar(select(Employee).where(Employee.id == booking.employee_id))
    if employee is None:
        return
    base_hours = Decimal("20") if employee.employment_type == "part_time" else Decimal("40")
    leave_hours = Decimal("0")
    leaves = (
        await db.scalars(
            select(LeaveRequest).where(
                LeaveRequest.employee_id == booking.employee_id,
                LeaveRequest.status == "approved",
                LeaveRequest.start_date <= booking.end_date,
                LeaveRequest.end_date >= booking.start_date,
            )
        )
    ).all()
    for leave in leaves:
        days = len(date_range(max(leave.start_date, booking.start_date), min(leave.end_date, booking.end_date)))
        leave_hours += min(as_decimal(leave.days), Decimal(days)) * Decimal("8")
    weeks = {week_start(day) for day in date_range(booking.start_date, booking.end_date)}
    for week in weeks:
        week_end = week + timedelta(days=6)
        overlap_days = len(date_range(max(booking.start_date, week), min(booking.end_date, week_end)))
        booked = as_decimal(booking.hours_per_day) * Decimal(overlap_days)
        stmt = (
            select(func.coalesce(func.sum(m.ProjectResourceBooking.hours_per_day), 0))
            .where(
                m.ProjectResourceBooking.employee_id == booking.employee_id,
                m.ProjectResourceBooking.status == "confirmed",
                m.ProjectResourceBooking.start_date <= week_end,
                m.ProjectResourceBooking.end_date >= week,
            )
        )
        if booking.id is not None:
            stmt = stmt.where(m.ProjectResourceBooking.id != booking.id)
        booked += as_decimal(await db.scalar(stmt))
        if booked > max(Decimal("0"), base_hours - leave_hours):
            raise ConflictError("Booking exceeds available capacity; an explicit override is required")


async def guard_no_double_billing(
    db: AsyncSession,
    *,
    source_type: str,
    source_id: UUID,
    exclude_line_id: Optional[UUID] = None,
) -> None:
    stmt = select(func.count()).select_from(m.ProjectBillingLine).where(
        m.ProjectBillingLine.source_type == source_type,
        m.ProjectBillingLine.source_id == source_id,
        m.ProjectBillingLine.status.in_(("invoiced", "billed")),
    )
    if exclude_line_id is not None:
        stmt = stmt.where(m.ProjectBillingLine.id != exclude_line_id)
    if await db.scalar(stmt):
        raise ConflictError("Source record has already been billed")


def guard_ai_prohibited_action(action_type: str) -> None:
    if str(action_type or "").strip().lower().replace("-", "_") in PROHIBITED_AI_ACTIONS:
        raise ForbiddenError("AI actions may not approve, post, close, or change governed records")


async def idempotency_lookup(
    db: AsyncSession, user: User, scope: str, key: str
) -> Optional[dict[str, Any]]:
    stmt = select(m.ProjectOutboxEvent).where(
        m.ProjectOutboxEvent.event_name == f"{IDEMPOTENCY_EVENT_PREFIX}{scope}",
        m.ProjectOutboxEvent.idempotency_key == key,
    )
    if user.tenant_id and not user.is_superuser:
        stmt = stmt.where(m.ProjectOutboxEvent.tenant_id == user.tenant_id)
    event = await db.scalar(stmt)
    if event is None:
        return None
    payload = event.payload or {}
    return {"response": payload.get("response"), "status_code": payload.get("status_code", 200)}


async def idempotency_store(
    db: AsyncSession,
    user: User,
    scope: str,
    key: str,
    response: Any,
    status_code: int = 200,
) -> None:
    event = m.ProjectOutboxEvent(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        event_name=f"{IDEMPOTENCY_EVENT_PREFIX}{scope}",
        payload={"response": _jsonable(response), "status_code": status_code},
        status="published",
        attempts=0,
        available_at=utcnow(),
        published_at=utcnow(),
        idempotency_key=key,
    )
    db.add(event)
    await db.flush()


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (Decimal, UUID, date, datetime)):
        return str(value)
    return value


async def record_activity(
    db: AsyncSession,
    user: User,
    entity_type: str,
    entity_id: UUID,
    action: str,
    changes: Optional[dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> m.ProjectActivity:
    activity = m.ProjectActivity(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=user.id,
        action=action,
        changes_json=_jsonable(changes or {}),
        correlation_id=correlation_id,
    )
    db.add(activity)
    await db.flush()
    return activity


async def enqueue_event(
    db: AsyncSession,
    user: User,
    event_name: str,
    payload: dict[str, Any],
    available_at: Optional[datetime] = None,
    correlation_id: Optional[str] = None,
) -> m.ProjectOutboxEvent:
    payload.setdefault("tenant_id", str(user.tenant_id) if user.tenant_id else None)
    if correlation_id:
        payload.setdefault("correlation_id", correlation_id)
    event = m.ProjectOutboxEvent(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        event_name=event_name,
        payload=payload,
        status="pending",
        attempts=0,
        available_at=available_at or utcnow(),
        correlation_id=correlation_id,
    )
    db.add(event)
    await db.flush()
    return event


async def dispatch_outbox(
    db: AsyncSession, limit: int = 50, tenant_id: Optional[UUID] = None
) -> dict[str, int]:
    stmt = (
        select(m.ProjectOutboxEvent)
        .where(
            m.ProjectOutboxEvent.status == "pending",
            m.ProjectOutboxEvent.available_at <= utcnow(),
            m.ProjectOutboxEvent.event_name.not_like(f"{IDEMPOTENCY_EVENT_PREFIX}%"),
        )
        .order_by(m.ProjectOutboxEvent.created_at)
        .limit(limit)
    )
    if tenant_id is not None:
        stmt = stmt.where(m.ProjectOutboxEvent.tenant_id == tenant_id)
    events = list((await db.scalars(stmt)).all())
    result = {"published": 0, "failed": 0}
    for event in events:
        event.attempts += 1
        try:
            if event.correlation_id:
                event.payload.setdefault("correlation_id", event.correlation_id)
            await publish(event.event_name, event.payload)
            event.status = "published"
            event.published_at = utcnow()
            result["published"] += 1
        except Exception as exc:
            event.status = "failed"
            event.error = str(exc)[:1000]
            result["failed"] += 1
    await db.flush()
    return result


async def sequence_number(
    db: AsyncSession,
    user: User,
    key: str,
    prefix: str,
    width: int = 5,
) -> str:
    stmt = select(NumberSequence).where(
        NumberSequence.key == key,
        NumberSequence.tenant_id == user.tenant_id,
    )
    if hasattr(select(NumberSequence), "with_for_update"):
        stmt = stmt.with_for_update()
    sequence = await db.scalar(stmt)
    if sequence is None:
        sequence = NumberSequence(
            tenant_id=user.tenant_id,
            created_by_id=user.id,
            key=key,
            prefix=prefix,
            next_number=1,
            padding=width,
        )
        db.add(sequence)
        await db.flush()
    model_by_key = {
        "project": (m.Project, "number"),
        "work_item": (m.Task, "number"),
        "sprint": (m.ProjectSprint, "number"),
    }
    mapping = model_by_key.get(key)
    existing_max = 0
    if mapping is not None:
        model, field = mapping
        number_stmt = select(getattr(model, field)).where(
            getattr(model, field).like(f"{prefix}%")
        )
        if user.tenant_id:
            number_stmt = number_stmt.where(model.tenant_id == user.tenant_id)
        for existing_number in (await db.scalars(number_stmt)).all():
            suffix = str(existing_number)[len(prefix) :].lstrip("-")
            if suffix.isdigit():
                existing_max = max(existing_max, int(suffix))
    value = max(sequence.next_number or 1, existing_max + 1)
    sequence.next_number = value + 1
    sequence.prefix = prefix
    sequence.padding = width
    await db.flush()
    return f"{prefix}-{value:0{width}d}"


async def legacy_number(
    db: AsyncSession,
    user: User,
    model: Any,
    field: str,
    prefix: str,
) -> str:
    return await legacy_next_number(db, model, field, prefix, user.tenant_id)


async def get_or_404(db: AsyncSession, user: User, model: Any, item_id: UUID) -> Any:
    stmt = select(model).where(model.id == item_id)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(model.tenant_id == user.tenant_id)
    item = await db.scalar(stmt)
    if item is None:
        raise NotFoundError(f"{model.__name__} not found")
    return item


async def resolve_employee_id(db: AsyncSession, user: User) -> Optional[UUID]:
    stmt = select(Employee).where(
        Employee.email == user.email,
        Employee.status == "active",
    )
    if user.tenant_id:
        stmt = stmt.where(Employee.tenant_id == user.tenant_id)
    employee = await db.scalar(stmt)
    return employee.id if employee else None


async def employee_label(db: AsyncSession, employee_id: Optional[UUID]) -> str:
    if employee_id is None:
        return "Unassigned"
    employee = await db.scalar(select(Employee).where(Employee.id == employee_id))
    if employee is None:
        return str(employee_id)
    return f"{employee.first_name} {employee.last_name or ''}".strip()


async def assert_no_parent_cycle(
    db: AsyncSession,
    work_item_id: UUID,
    parent_id: Optional[UUID],
) -> None:
    if parent_id is None:
        return
    if parent_id == work_item_id:
        raise ConflictError("A work item cannot be its own parent")
    seen: set[UUID] = set()
    current: Optional[UUID] = parent_id
    while current:
        if current in seen or current == work_item_id:
            raise ConflictError("Work item hierarchy contains a cycle")
        seen.add(current)
        parent = await db.scalar(select(m.Task.parent_work_item_id).where(m.Task.id == current))
        current = parent


async def assert_no_dependency_cycle(
    db: AsyncSession,
    tenant_id: Optional[UUID],
    predecessor_id: UUID,
    successor_id: UUID,
) -> None:
    if predecessor_id == successor_id:
        raise ConflictError("A task cannot depend on itself")
    stmt = select(m.ProjectDependency).where(
        m.ProjectDependency.status.in_(("proposed", "active"))
    )
    if tenant_id:
        stmt = stmt.where(m.ProjectDependency.tenant_id == tenant_id)
    edges = list((await db.scalars(stmt)).all())
    adjacency: dict[UUID, list[UUID]] = {}
    for edge in edges:
        adjacency.setdefault(edge.predecessor_id, []).append(edge.successor_id)
    stack = [successor_id]
    seen: set[UUID] = set()
    while stack:
        node = stack.pop()
        if node == predecessor_id:
            raise ConflictError("Dependency would create a cycle")
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, []))


async def recompute_task_actual_hours(db: AsyncSession, work_item_id: UUID) -> Decimal:
    stmt = select(func.coalesce(func.sum(m.ProjectTimeEntry.hours), 0)).where(
        m.ProjectTimeEntry.work_item_id == work_item_id,
        m.ProjectTimeEntry.is_active.is_(True),
        m.ProjectTimeEntry.status.in_(("approved", "invoiced", "paid")),
    )
    hours = as_decimal(await db.scalar(stmt))
    task = await db.scalar(select(m.Task).where(m.Task.id == work_item_id))
    if task is not None:
        task.actual_hours = hours
        task.remaining_hours = max(Decimal("0"), as_decimal(task.planned_hours) - hours)
        task.last_activity_at = utcnow()
        await db.flush()
    return hours


async def recompute_timesheet_totals(db: AsyncSession, timesheet_id: UUID) -> None:
    timesheet = await db.scalar(select(m.ProjectTimesheet).where(m.ProjectTimesheet.id == timesheet_id))
    if timesheet is None:
        return
    stmt = (
        select(
            func.coalesce(func.sum(m.ProjectTimeEntry.hours), 0),
            func.coalesce(
                func.sum(
                    func.cast(m.ProjectTimeEntry.billable, Integer) * m.ProjectTimeEntry.hours
                ),
                0,
            ),
        )
        .select_from(m.ProjectTimesheetEntry)
        .join(m.ProjectTimeEntry, m.ProjectTimeEntry.id == m.ProjectTimesheetEntry.time_entry_id)
        .where(m.ProjectTimesheetEntry.timesheet_id == timesheet_id)
    )
    result = (await db.execute(stmt)).one()
    timesheet.total_hours = as_decimal(result[0])
    timesheet.billable_hours = as_decimal(result[1])
    await db.flush()


def week_start(value: date) -> date:
    return value - timedelta(days=value.weekday())


def declared_weekly_hours(employee: Any) -> Decimal:
    for field in ("weekly_hours", "hours_per_week", "declared_weekly_hours", "standard_hours"):
        value = getattr(employee, field, None)
        if value is not None:
            return as_decimal(value)
    if str(getattr(employee, "employment_type", "full_time")).lower() in ("part_time", "part-time", "contract"):
        return Decimal("20")
    return Decimal("40")


def date_range(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        days.append(current)
        current += timedelta(days=1)
    return days


async def refresh_capacity(
    db: AsyncSession,
    user: User,
    start_date: date,
    end_date: date,
    employee_id: Optional[UUID] = None,
) -> list[CapacityRow]:
    if end_date < start_date:
        raise ValidationError("end_date must be on or after start_date")
    employee_stmt = select(Employee).where(Employee.status == "active")
    if user.tenant_id:
        employee_stmt = employee_stmt.where(Employee.tenant_id == user.tenant_id)
    if employee_id:
        employee_stmt = employee_stmt.where(Employee.id == employee_id)
    employees = list((await db.scalars(employee_stmt)).all())

    leave_stmt = select(LeaveRequest).where(
        LeaveRequest.status == "approved",
        LeaveRequest.start_date <= end_date,
        LeaveRequest.end_date >= start_date,
    )
    if user.tenant_id:
        leave_stmt = leave_stmt.where(LeaveRequest.tenant_id == user.tenant_id)
    if employee_id:
        leave_stmt = leave_stmt.where(LeaveRequest.employee_id == employee_id)
    leaves = list((await db.scalars(leave_stmt)).all())

    booking_stmt = select(m.ProjectResourceBooking).where(
        m.ProjectResourceBooking.status == "confirmed",
        m.ProjectResourceBooking.start_date <= end_date,
        m.ProjectResourceBooking.end_date >= start_date,
    )
    if user.tenant_id:
        booking_stmt = booking_stmt.where(m.ProjectResourceBooking.tenant_id == user.tenant_id)
    if employee_id:
        booking_stmt = booking_stmt.where(m.ProjectResourceBooking.employee_id == employee_id)
    bookings = list((await db.scalars(booking_stmt)).all())

    weeks = sorted({week_start(day) for day in date_range(start_date, end_date)})
    rows: list[CapacityRow] = []
    for employee in employees:
        base_hours = declared_weekly_hours(employee)
        employment_type = str(getattr(employee, "employment_type", "full_time") or "full_time")

        for week in weeks:
            week_end = week + timedelta(days=6)
            capacity_stmt = select(m.ProjectCapacityCalendar).where(
                m.ProjectCapacityCalendar.employee_id == employee.id,
                m.ProjectCapacityCalendar.week_start == week,
            )
            if user.tenant_id:
                capacity_stmt = capacity_stmt.where(
                    m.ProjectCapacityCalendar.tenant_id == user.tenant_id
                )
            capacity = await db.scalar(capacity_stmt)
            holiday_hours = (
                as_decimal(capacity.holiday_hours) if capacity is not None else Decimal("0")
            )
            leave_hours = Decimal("0")
            for leave in leaves:
                if leave.employee_id != employee.id:
                    continue
                overlap = [
                    day
                    for day in date_range(max(leave.start_date, week), min(leave.end_date, week_end))
                ]
                leave_hours += min(as_decimal(leave.days), Decimal(len(overlap))) * Decimal("8")
            booked_hours = Decimal("0")
            for booking in bookings:
                if booking.employee_id != employee.id:
                    continue
                overlap_days = len(
                    date_range(max(booking.start_date, week), min(booking.end_date, week_end))
                )
                booked_hours += as_decimal(booking.hours_per_day) * Decimal(overlap_days)
            available_hours = max(
                Decimal("0"), base_hours - leave_hours - holiday_hours - booked_hours
            )
            utilization = Decimal("0")
            if base_hours > 0:
                utilization = (booked_hours / base_hours * Decimal("100")).quantize(Decimal("0.01"))
            overallocated = booked_hours > base_hours - leave_hours - holiday_hours

            if capacity is None:
                capacity = m.ProjectCapacityCalendar(
                    tenant_id=user.tenant_id,
                    created_by_id=user.id,
                    employee_id=employee.id,
                    week_start=week,
                )
                db.add(capacity)
            capacity.capacity_hours = base_hours
            capacity.planned_leave_hours = leave_hours
            capacity.holiday_hours = holiday_hours
            capacity.source = "hr"
            capacity.status = "active"

            workload_stmt = select(m.ProjectWorkloadSnapshot).where(
                m.ProjectWorkloadSnapshot.employee_id == employee.id,
                m.ProjectWorkloadSnapshot.week_start == week,
            )
            if user.tenant_id:
                workload_stmt = workload_stmt.where(
                    m.ProjectWorkloadSnapshot.tenant_id == user.tenant_id
                )
            workload = await db.scalar(workload_stmt)
            if workload is None:
                workload = m.ProjectWorkloadSnapshot(
                    tenant_id=user.tenant_id,
                    created_by_id=user.id,
                    employee_id=employee.id,
                    week_start=week,
                )
                db.add(workload)
            workload.booked_hours = booked_hours
            workload.available_hours = available_hours
            workload.utilization_percent = utilization
            workload.overallocated = overallocated
            workload.status = "active"
            rows.append(
                CapacityRow(
                    employee_id=employee.id,
                    employee_name=f"{employee.first_name} {employee.last_name or ''}".strip(),
                    week_start=week,
                    capacity_hours=base_hours,
                    planned_leave_hours=leave_hours,
                    holiday_hours=holiday_hours,
                    employment_type=employment_type,
                    declared_weekly_hours=base_hours,
                    capacity_source="hr",
                    booked_hours=booked_hours,
                    available_hours=available_hours,
                    utilization_percent=utilization,
                    overallocated=overallocated,
                )
            )
    await db.flush()
    return rows


async def workload_rows(db: AsyncSession, user: User) -> list[WorkloadRow]:
    stmt = select(m.ProjectWorkloadSnapshot).where(m.ProjectWorkloadSnapshot.is_active.is_(True))
    if user.tenant_id:
        stmt = stmt.where(m.ProjectWorkloadSnapshot.tenant_id == user.tenant_id)
    snapshots = list((await db.scalars(stmt.order_by(m.ProjectWorkloadSnapshot.week_start))).all())
    rows: list[WorkloadRow] = []
    for snapshot in snapshots:
        rows.append(
            WorkloadRow(
                employee_id=snapshot.employee_id,
                employee_name=await employee_label(db, snapshot.employee_id),
                week_start=snapshot.week_start,
                booked_hours=snapshot.booked_hours,
                available_hours=snapshot.available_hours,
                utilization_percent=snapshot.utilization_percent,
                overallocated=snapshot.overallocated,
            )
        )
    return rows


async def critical_path(db: AsyncSession, user: User, project_id: UUID) -> CriticalPathResponse:
    task_stmt = select(m.Task).where(
        m.Task.project_id == project_id,
        m.Task.is_active.is_(True),
    )
    dep_stmt = select(m.ProjectDependency).where(
        m.ProjectDependency.status == "active",
        m.ProjectDependency.is_active.is_(True),
    )
    if user.tenant_id:
        task_stmt = task_stmt.where(m.Task.tenant_id == user.tenant_id)
        dep_stmt = dep_stmt.where(m.ProjectDependency.tenant_id == user.tenant_id)
    tasks = {task.id: task for task in (await db.scalars(task_stmt)).all()}
    dependencies = [dep for dep in (await db.scalars(dep_stmt)).all() if dep.predecessor_id in tasks and dep.successor_id in tasks]

    successors: dict[UUID, list[UUID]] = {}
    lag_days: dict[tuple[UUID, UUID], int] = {}
    indegree = {task_id: 0 for task_id in tasks}
    for dep in dependencies:
        successors.setdefault(dep.predecessor_id, []).append(dep.successor_id)
        lag_days[(dep.predecessor_id, dep.successor_id)] = int(dep.lag_days or 0)
        indegree[dep.successor_id] += 1

    def duration(task: m.Task) -> int:
        if task.start_date and task.due_date:
            return max(1, (task.due_date - task.start_date).days + 1)
        return max(1, math.ceil(as_decimal(task.estimated_hours) / Decimal("8")))

    earliest_start = {task_id: 0 for task_id in tasks}
    earliest_finish = {task_id: duration(task) for task_id, task in tasks.items()}
    queue = [task_id for task_id, degree in indegree.items() if degree == 0]
    ordered: list[UUID] = []
    while queue:
        node = queue.pop(0)
        ordered.append(node)
        for successor in successors.get(node, []):
            earliest_start[successor] = max(
                earliest_start[successor],
                earliest_finish[node] + lag_days.get((node, successor), 0),
            )
            earliest_finish[successor] = earliest_start[successor] + duration(tasks[successor])
            indegree[successor] -= 1
            if indegree[successor] == 0:
                queue.append(successor)

    if not ordered:
        ordered = list(tasks)
        for task_id in ordered:
            earliest_start[task_id] = 0
            earliest_finish[task_id] = duration(tasks[task_id])
    total_days = max(earliest_finish.values(), default=0)
    steps = []
    for task_id in sorted(ordered, key=lambda item: (-earliest_finish[item], item)):
        task = tasks[task_id]
        steps.append(
            CriticalPathStep(
                work_item_id=task.id,
                title=task.title,
                start_date=task.start_date,
                end_date=task.due_date,
                duration_days=duration(task),
            )
        )
    return CriticalPathResponse(project_id=project_id, steps=steps[:50], total_days=total_days)


async def billing_preview(db: AsyncSession, user: User, project: m.Project, billing_type: Optional[str] = None) -> BillingPreview:
    selected = billing_type or project.billing_type
    lines: list[BillingLinePreview] = []

    if selected in ("time_and_material", "fixed"):
        entry_stmt = (
            select(m.ProjectTimeEntry)
            .join(m.Task, m.Task.id == m.ProjectTimeEntry.work_item_id)
            .where(
                m.Task.project_id == project.id,
                m.ProjectTimeEntry.is_active.is_(True),
                m.ProjectTimeEntry.status == "approved",
                m.ProjectTimeEntry.billable.is_(True),
                m.ProjectTimeEntry.invoice_link_id.is_(None),
            )
        )
        if user.tenant_id:
            entry_stmt = entry_stmt.where(m.ProjectTimeEntry.tenant_id == user.tenant_id)
        for entry in (await db.scalars(entry_stmt)).all():
            lines.append(
                BillingLinePreview(
                    source_type="time",
                    source_id=entry.id,
                    description=entry.description or "Billable time",
                    quantity=entry.hours,
                    rate=entry.billable_rate,
                    amount=as_decimal(entry.hours) * as_decimal(entry.billable_rate),
                )
            )

        expense_stmt = select(m.ProjectExpense).where(
            m.ProjectExpense.project_id == project.id,
            m.ProjectExpense.is_active.is_(True),
            m.ProjectExpense.status == "approved",
            m.ProjectExpense.billable.is_(True),
            m.ProjectExpense.invoice_link_id.is_(None),
        )
        if user.tenant_id:
            expense_stmt = expense_stmt.where(m.ProjectExpense.tenant_id == user.tenant_id)
        for expense in (await db.scalars(expense_stmt)).all():
            lines.append(
                BillingLinePreview(
                    source_type="expense",
                    source_id=expense.id,
                    description=expense.category,
                    quantity=Decimal("1"),
                    rate=expense.amount,
                    amount=expense.amount,
                )
            )

    if selected in ("milestone", "fixed"):
        milestone_stmt = select(m.ProjectMilestone).where(
            m.ProjectMilestone.project_id == project.id,
            m.ProjectMilestone.is_active.is_(True),
            m.ProjectMilestone.status == "accepted",
            m.ProjectMilestone.amount > 0,
            m.ProjectMilestone.invoice_link_id.is_(None),
        )
        if user.tenant_id:
            milestone_stmt = milestone_stmt.where(m.ProjectMilestone.tenant_id == user.tenant_id)
        for milestone in (await db.scalars(milestone_stmt)).all():
            lines.append(
                BillingLinePreview(
                    source_type="milestone",
                    source_id=milestone.id,
                    description=milestone.name,
                    quantity=Decimal("1"),
                    rate=milestone.amount,
                    amount=milestone.amount,
                )
            )

    if selected == "fixed" and not lines:
        lines.append(
            BillingLinePreview(
                source_type="fixed_fee",
                source_id=project.id,
                description=f"Fixed fee for {project.name}",
                quantity=Decimal("1"),
                rate=project.contract_value or project.budget,
                amount=project.contract_value or project.budget,
            )
        )

    gross = sum((line.amount for line in lines), Decimal("0"))
    return BillingPreview(
        project_id=project.id,
        billing_type=selected,
        lines=lines,
        gross_amount=gross,
        tax_amount=Decimal("0"),
        total_amount=gross,
    )


async def post_billing_run(
    db: AsyncSession,
    user: User,
    run: m.ProjectBillingRun,
    request: Any,
) -> dict[str, Any]:
    if run.status != "approved":
        raise ConflictError("Only an approved billing run can be posted")
    if run.finance_invoice_id is not None:
        raise ConflictError("Billing run already has a finance invoice")

    line_stmt = select(m.ProjectBillingLine).where(
        m.ProjectBillingLine.billing_run_id == run.id,
        m.ProjectBillingLine.is_active.is_(True),
    )
    lines = list((await db.scalars(line_stmt)).all())
    if not lines:
        raise ConflictError("Billing run has no lines")
    for line in lines:
        if line.source_id is not None and line.source_type:
            await guard_no_double_billing(
                db,
                source_type=line.source_type,
                source_id=line.source_id,
                exclude_line_id=line.id,
            )
    gross = sum((as_decimal(line.amount) for line in lines), Decimal("0"))
    tax = as_decimal(getattr(request, "tax_amount", 0))
    total = gross + tax

    invoice = await create_invoice_from_proposal(
        db,
        user,
        customer_id=getattr(request, "customer_id", None),
        issue_date=getattr(request, "issue_date", None) or date.today(),
        due_date=getattr(request, "due_date", None),
        subtotal=gross,
        tax=tax,
        total=total,
        currency=run.currency,
        notes=getattr(request, "notes", None),
        reference=f"PM-BILL:{run.idempotency_key}",
    )

    link = m.ProjectInvoiceLink(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        finance_invoice_id=invoice.id,
        project_id=run.project_id,
        billing_run_id=run.id,
        amount=total,
        status="open",
    )
    db.add(link)
    await db.flush()

    for line in lines:
        if line.source_type == "time":
            entry = await db.scalar(select(m.ProjectTimeEntry).where(m.ProjectTimeEntry.id == line.source_id))
            if entry and entry.invoice_link_id is None:
                entry.invoice_link_id = link.id
                entry.status = "invoiced"
        elif line.source_type == "expense":
            expense = await db.scalar(select(m.ProjectExpense).where(m.ProjectExpense.id == line.source_id))
            if expense and expense.invoice_link_id is None:
                expense.invoice_link_id = link.id
                expense.status = "invoiced"
        elif line.source_type == "milestone":
            milestone = await db.scalar(select(m.ProjectMilestone).where(m.ProjectMilestone.id == line.source_id))
            if milestone and milestone.invoice_link_id is None:
                milestone.invoice_link_id = link.id
                milestone.status = "billed"
        line.status = "invoiced"

    project = await db.scalar(select(m.Project).where(m.Project.id == run.project_id))
    if project:
        project.total_billed = as_decimal(project.total_billed) + total
        project.wip_amount = max(Decimal("0"), as_decimal(project.wip_amount) - gross)
        project.margin_amount = as_decimal(project.total_billed) - as_decimal(project.total_cost)
        if as_decimal(project.total_billed) > 0:
            project.margin_percent = (project.margin_amount / project.total_billed * Decimal("100")).quantize(
                Decimal("0.01")
            )

    run.finance_invoice_id = invoice.id
    run.gross_amount = gross
    run.tax_amount = tax
    run.posted_at = utcnow()
    await db.flush()
    await enqueue_event(
        db,
        user,
        "billing.posted",
        {
            "billing_run_id": str(run.id),
            "finance_invoice_id": str(invoice.id),
            "project_id": str(run.project_id),
            "amount": str(total),
        },
        correlation_id=getattr(request, "headers", {}).get("x-correlation-id"),
    )
    return {
        "billing_run_id": run.id,
        "finance_invoice_id": invoice.id,
        "invoice_number": invoice.invoice_number,
        "amount": total,
    }


async def change_resource_rate(
    db: AsyncSession,
    user: User,
    role: Any,
    *,
    cost_rate: Optional[Decimal] = None,
    billable_rate: Optional[Decimal] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    if not user.has_permission("projects.finance.read"):
        raise ForbiddenError("projects.finance.read is required to change rates")
    changes: dict[str, Any] = {"reason": reason}
    if cost_rate is not None:
        changes["default_cost_rate"] = str(cost_rate)
        role.default_cost_rate = cost_rate
    if billable_rate is not None:
        changes["default_billable_rate"] = str(billable_rate)
        role.default_billable_rate = billable_rate
    if len(changes) == 1:
        raise ValidationError("At least one rate is required")
    await db.flush()
    await record_activity(db, user, "resource_role", role.id, "rate.changed", changes)
    return changes


async def refresh_ai_signals(db: AsyncSession, user: User, project_id: Optional[UUID] = None) -> list[m.ProjectAiSignal]:
    project_stmt = select(m.Project).where(m.Project.is_active.is_(True))
    if user.tenant_id:
        project_stmt = project_stmt.where(m.Project.tenant_id == user.tenant_id)
    if project_id:
        project_stmt = project_stmt.where(m.Project.id == project_id)
    projects = list((await db.scalars(project_stmt)).all())
    created: list[m.ProjectAiSignal] = []
    for project in projects:
        open_tasks_stmt = select(func.count()).select_from(m.Task).where(
            m.Task.project_id == project.id,
            m.Task.due_date < date.today(),
            m.Task.status.notin_(("done", "accepted", "closed", "cancelled")),
            m.Task.is_active.is_(True),
        )
        overdue = int(await db.scalar(open_tasks_stmt) or 0)
        leakage_stmt = (
            select(func.coalesce(func.sum(m.ProjectTimeEntry.hours), 0))
            .join(m.Task, m.Task.id == m.ProjectTimeEntry.work_item_id)
            .where(
                m.Task.project_id == project.id,
                m.ProjectTimeEntry.status == "approved",
                m.ProjectTimeEntry.billable.is_(True),
                m.ProjectTimeEntry.invoice_link_id.is_(None),
            )
        )
        unbilled_hours = as_decimal(await db.scalar(leakage_stmt))
        candidates = [
            (
                "delay_risk",
                Decimal(min(100, 40 + overdue * 10)),
                {"overdue_tasks": overdue, "health": project.health},
                f"{overdue} overdue work items indicate schedule risk",
            ),
            (
                "billing_leakage",
                Decimal(min(100, int(unbilled_hours * 2))),
                {"unbilled_hours": str(unbilled_hours), "billing_type": project.billing_type},
                f"{unbilled_hours} approved billable hours are not linked to an invoice",
            ),
        ]
        for signal_type, score, features, explanation in candidates:
            existing_stmt = select(m.ProjectAiSignal).where(
                m.ProjectAiSignal.entity_type == "project",
                m.ProjectAiSignal.entity_id == project.id,
                m.ProjectAiSignal.signal_type == signal_type,
                m.ProjectAiSignal.review_status == "pending",
            )
            if user.tenant_id:
                existing_stmt = existing_stmt.where(m.ProjectAiSignal.tenant_id == user.tenant_id)
            existing = await db.scalar(existing_stmt)
            if existing:
                existing.score = score
                existing.features_json = features
                existing.explanation = explanation
                existing.generated_at = utcnow()
                created.append(existing)
                continue
            signal = m.ProjectAiSignal(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                entity_type="project",
                entity_id=project.id,
                signal_type=signal_type,
                score=score,
                features_json=features,
                explanation=explanation,
                model_version="rules-v1",
                generated_at=utcnow(),
                review_status="pending",
            )
            db.add(signal)
            created.append(signal)
    await db.flush()
    return created


AUTOMATION_TRIGGER_MODELS = {
    "project": m.Project,
    "work_item": m.Task,
    "task": m.Task,
    "time_entry": m.ProjectTimeEntry,
    "timesheet": m.ProjectTimesheet,
    "billing_run": m.ProjectBillingRun,
    "booking": m.ProjectResourceBooking,
    "risk": m.ProjectRisk,
    "issue": m.ProjectIssue,
    "sprint": m.ProjectSprint,
    "milestone": m.ProjectMilestone,
    "status_update": m.ProjectStatusUpdate,
}

AUTOMATION_ACTION_PERMISSIONS = {
    "record_activity": None,
    "set_health": "projects.project.update",
    "create_comment": "projects.comment.create",
}


def _condition_matches(condition: Any, entity: Any) -> bool:
    if not isinstance(condition, dict) or entity is None:
        return False
    field = condition.get("field")
    if not field:
        return False
    actual = getattr(entity, field, None)
    if actual is None:
        return False
    expected = condition.get("value")
    op = str(condition.get("op", "eq")).lower()
    actual_text = str(actual)
    if op in ("eq", "=="):
        return actual_text == str(expected)
    if op in ("neq", "!="):
        return actual_text != str(expected)
    if op == "in":
        return actual_text in {str(value) for value in expected or []}
    return False


async def run_automation_rules(
    db: AsyncSession,
    user: User,
    trigger_entity: str,
    trigger_id: UUID,
    project_id: Optional[UUID] = None,
) -> list[m.ProjectAutomationRun]:
    event_name = trigger_entity
    trigger_entity = trigger_entity.split(".", 1)[0]
    stmt = select(m.ProjectAutomationRule).where(
        m.ProjectAutomationRule.status == "active",
        m.ProjectAutomationRule.is_active.is_(True),
    )
    if user.tenant_id:
        stmt = stmt.where(m.ProjectAutomationRule.tenant_id == user.tenant_id)
    rules = list((await db.scalars(stmt)).all())
    entity_model = AUTOMATION_TRIGGER_MODELS.get(trigger_entity)
    entity = None
    if entity_model is not None:
        try:
            entity = await get_or_404(db, user, entity_model, trigger_id)
        except Exception:
            entity = None
    runs: list[m.ProjectAutomationRun] = []
    for rule in rules:
        if rule.project_id and project_id and rule.project_id != project_id:
            continue
        trigger = rule.trigger_json or {}
        if (
            isinstance(trigger, dict)
            and trigger.get("event")
            and trigger.get("event") not in (trigger_entity, event_name)
        ):
            continue
        conditions = rule.conditions_json or []
        if conditions and not all(_condition_matches(item, entity) for item in conditions):
            continue
        actor = user
        if rule.owner_id:
            owner = await db.scalar(select(User).where(User.id == rule.owner_id))
            if owner is None:
                actor = None
            else:
                actor = owner
        run_status = "success"
        run_error: Optional[str] = None
        if actor is None:
            run_status = "paused"
            run_error = "Rule owner is unavailable"
            rule.status = "paused"
        else:
            for action in rule.actions_json or []:
                if not isinstance(action, dict):
                    continue
                action_type = str(action.get("type") or "").strip().lower()
                required = AUTOMATION_ACTION_PERMISSIONS.get(action_type, "projects.automation.run")
                if required and not actor.is_superuser and not actor.has_permission(required):
                    run_status = "paused"
                    run_error = f"Missing permission: {required}"
                    rule.status = "paused"
                    await record_activity(
                        db,
                        actor,
                        trigger_entity,
                        trigger_id,
                        "automation.rule.paused",
                        {"rule_id": str(rule.id), "rule_name": rule.name, "reason": run_error},
                    )
                    break
                if action_type == "record_activity":
                    await record_activity(
                        db,
                        actor,
                        trigger_entity,
                        trigger_id,
                        action.get("action") or "automation.action.executed",
                        {
                            "rule_id": str(rule.id),
                            "rule_name": rule.name,
                            "message": action.get("message"),
                        },
                    )
                elif action_type == "set_health" and project_id:
                    project = await get_or_404(db, actor, m.Project, project_id)
                    project.health = str(action.get("health") or "unknown")
                    await record_activity(
                        db,
                        actor,
                        "project",
                        project.id,
                        "automation.health_changed",
                        {"rule_id": str(rule.id), "health": project.health},
                    )
                elif action_type == "create_comment":
                    body = str(action.get("body") or "")
                    if body:
                        db.add(
                            m.ProjectComment(
                                tenant_id=actor.tenant_id or user.tenant_id,
                                created_by_id=actor.id,
                                entity_type=trigger_entity,
                                entity_id=trigger_id,
                                author_id=actor.id,
                                body=body,
                            )
                        )
                elif action_type not in AUTOMATION_ACTION_PERMISSIONS:
                    run_status = "failed"
                    run_error = f"Unsupported automation action: {action_type}"
        run = m.ProjectAutomationRun(
            tenant_id=user.tenant_id,
            created_by_id=user.id,
            rule_id=rule.id,
            trigger_entity=trigger_entity,
            trigger_id=trigger_id,
            status=run_status,
            error=run_error,
            started_at=utcnow(),
            finished_at=utcnow(),
        )
        db.add(run)
        rule.run_count = int(rule.run_count or 0) + 1
        if run_status == "success":
            await record_activity(
                db,
                actor or user,
                trigger_entity,
                trigger_id,
                "automation.rule_executed",
                {"rule_id": str(rule.id), "rule_name": rule.name},
            )
        runs.append(run)
    await db.flush()
    return runs
