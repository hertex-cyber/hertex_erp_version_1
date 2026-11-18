from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.modules.finance.models import TaxCode
from app.modules.identity.models import User
from app.modules.integrations.service import send_message
from app.modules.projects import models as m
from app.modules.projects.schemas import (
    BacklogMove,
    BaselineCreate,
    CommentCreate,
    CommentUpdate,
    GanttResponse,
    GanttTask,
    ImportMappingDecision,
    ImportSubmit,
    IntakeDecision,
    IntakeSubmit,
    NotificationRequest,
    ReportResponse,
    ScheduleVarianceRow,
    SprintCompleteRequest,
    SprintMetrics,
    UnbilledReport,
    WorkItemLinkCreate,
)
from app.modules.projects.services import (
    as_decimal,
    billing_preview,
    get_or_404,
    record_activity,
    sequence_number,
    utcnow,
)

ENTITY_MODELS: dict[str, Any] = {
    "project": m.Project,
    "work_item": m.Task,
    "task": m.Task,
    "sprint": m.ProjectSprint,
    "milestone": m.ProjectMilestone,
    "risk": m.ProjectRisk,
    "issue": m.ProjectIssue,
    "decision": m.ProjectDecision,
    "status_update": m.ProjectStatusUpdate,
    "change_request": m.ProjectChangeRequest,
    "time_entry": m.ProjectTimeEntry,
    "billing_run": m.ProjectBillingRun,
    "booking": m.ProjectResourceBooking,
    "comment": m.ProjectComment,
}

REPORT_KEYS = {
    "project-health",
    "budget-vs-actual",
    "earned-value",
    "utilisation",
    "workload-heatmap",
    "unbilled-wip",
    "billing-leakage",
    "velocity",
    "cycle-lead-time",
    "cumulative-flow",
    "throughput-rework",
    "risk-heatmap",
    "milestone-schedule",
    "timesheet-compliance",
    "portfolio-benefits",
    "ai-review-queue",
}

REPORT_ALIASES = {
    "health": "project-health",
    "budget_vs_actual": "budget-vs-actual",
    "earned_value": "earned-value",
    "utilisation": "utilisation",
    "workload": "workload-heatmap",
    "unbilled_wip": "unbilled-wip",
    "billing_leakage": "billing-leakage",
    "velocity": "velocity",
    "cycle_lead_time": "cycle-lead-time",
    "cumulative_flow": "cumulative-flow",
    "throughput_rework": "throughput-rework",
    "risk_heatmap": "risk-heatmap",
    "milestone_schedule": "milestone-schedule",
    "timesheet_compliance": "timesheet-compliance",
    "portfolio_benefits": "portfolio-benefits",
    "ai_governance": "ai-review-queue",
}

SENSITIVE_REPORT_FIELDS = {
    "budget", "budget_cost", "budget_revenue", "contract_value", "cost_rate",
    "billable_rate", "amount", "billed", "labour_cost", "expense_cost",
    "other_cost", "wip", "margin", "margin_amount", "margin_percent",
    "total", "gross_amount", "tax_amount", "rate",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (datetime, date, UUID)):
        return str(value)
    return value


def _days(start: Optional[date], end: Optional[date]) -> int:
    if start is None or end is None:
        return 0
    return (end - start).days


async def entity_project_id(
    db: AsyncSession, user: User, entity_type: str, entity_id: UUID
) -> UUID:
    model = ENTITY_MODELS.get(entity_type)
    if model is None:
        raise ValidationError(f"Unsupported entity type: {entity_type}")
    obj = await get_or_404(db, user, model, entity_id)
    if entity_type in ("project",):
        return obj.id
    if entity_type in ("time_entry",):
        return (await get_or_404(db, user, m.Task, obj.work_item_id)).project_id
    if getattr(obj, "project_id", None):
        return obj.project_id
    raise ValidationError(f"{entity_type} is not linked to a project")


async def reorder_backlog(
    db: AsyncSession, user: User, project: m.Project, moves: list[BacklogMove]
) -> list[m.Task]:
    tasks: list[m.Task] = []
    for index, move in enumerate(moves):
        item = await get_or_404(db, user, m.Task, move.work_item_id)
        if item.project_id != project.id:
            raise ValidationError("Backlog item belongs to another project")
        rank = move.rank if move.rank is not None else Decimal((index + 1) * 1000)
        item.rank = rank
        if "sprint_id" in move.model_fields_set:
            if move.sprint_id is not None:
                sprint = await get_or_404(db, user, m.ProjectSprint, move.sprint_id)
                if sprint.project_id != project.id or sprint.status == "completed":
                    raise ConflictError("Sprint is not available for backlog moves")
            item.sprint_id = move.sprint_id
        if "board_column_id" in move.model_fields_set:
            if move.board_column_id is not None:
                column = await get_or_404(db, user, m.ProjectBoardColumn, move.board_column_id)
                board = await get_or_404(db, user, m.ProjectBoard, column.board_id)
                if board.project_id != project.id:
                    raise ValidationError("Board column belongs to another project")
            item.board_column_id = move.board_column_id
        item.version = int(item.version or 1) + 1
        item.last_activity_at = utcnow()
        tasks.append(item)
    await db.flush()
    return tasks


async def create_work_item_link(
    db: AsyncSession, user: User, work_item_id: UUID, payload: WorkItemLinkCreate
) -> m.ProjectWorkItemLink:
    source = await get_or_404(db, user, m.Task, work_item_id)
    target = await get_or_404(db, user, m.Task, payload.linked_work_item_id)
    if source.id == target.id:
        raise ValidationError("A work item cannot be linked to itself")
    if user.tenant_id and source.tenant_id != target.tenant_id:
        raise NotFoundError("Work item not found")
    stem = payload.link_type.strip().lower()
    if stem in ("blocked_by", "duplicate_of", "relates_to", "caused_by"):
        existing = await db.scalar(
            select(m.ProjectWorkItemLink).where(
                m.ProjectWorkItemLink.work_item_id == source.id,
                m.ProjectWorkItemLink.linked_work_item_id == target.id,
                m.ProjectWorkItemLink.link_type == stem,
            )
        )
        if existing is not None:
            return existing
    link = m.ProjectWorkItemLink(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        work_item_id=source.id,
        linked_work_item_id=target.id,
        link_type=stem,
    )
    db.add(link)
    if stem == "blocked_by":
        source.blocked_by_id = target.id
        source.status = "blocked"
        source.blocked_reason = source.blocked_reason or f"Blocked by {target.number}"
        await record_activity(
            db, user, "work_item", source.id, "work_item.blocked", {"blocker_id": str(target.id)}
        )
    if stem == "duplicate_of":
        source.duplicate_of_id = target.id
    await db.flush()
    return link


async def delete_work_item_link(
    db: AsyncSession, user: User, work_item_id: UUID, link_id: UUID
) -> m.ProjectWorkItemLink:
    link = await get_or_404(db, user, m.ProjectWorkItemLink, link_id)
    if link.work_item_id != work_item_id:
        raise NotFoundError("Link not found")
    if link.link_type == "blocked_by":
        source = await get_or_404(db, user, m.Task, work_item_id)
        if source.blocked_by_id == link.linked_work_item_id:
            source.blocked_by_id = None
            source.blocked_reason = None
            if source.status == "blocked":
                source.status = "todo"
    await db.delete(link)
    await db.flush()
    return link


async def create_comment(
    db: AsyncSession,
    user: User,
    entity_type: str,
    entity_id: UUID,
    payload: CommentCreate,
    project_id: UUID,
) -> m.ProjectComment:
    if payload.parent_comment_id:
        parent = await get_or_404(db, user, m.ProjectComment, payload.parent_comment_id)
        if parent.entity_type != entity_type or parent.entity_id != entity_id:
            raise ValidationError("Parent comment belongs to another entity")
    comment = m.ProjectComment(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entity_type=entity_type,
        entity_id=entity_id,
        author_id=user.id,
        body=payload.body,
        mentions_json=payload.mentions,
        parent_comment_id=payload.parent_comment_id,
    )
    db.add(comment)
    await db.flush()
    await record_activity(
        db,
        user,
        entity_type,
        entity_id,
        "comment.created",
        {"comment_id": str(comment.id), "mentions": payload.mentions, "project_id": str(project_id)},
    )
    return comment


async def update_comment(
    db: AsyncSession, user: User, comment_id: UUID, payload: CommentUpdate
) -> m.ProjectComment:
    comment = await get_or_404(db, user, m.ProjectComment, comment_id)
    if comment.author_id != user.id and not user.is_superuser:
        raise ForbiddenError("Only the author may edit a comment")
    if payload.body is not None:
        comment.body = payload.body
    if payload.mentions is not None:
        comment.mentions_json = payload.mentions
    await db.flush()
    return comment


async def complete_sprint(
    db: AsyncSession, user: User, sprint: m.ProjectSprint, payload: SprintCompleteRequest
) -> SprintMetrics:
    if sprint.status == "completed":
        raise ConflictError("Completed sprints are immutable")
    if sprint.status not in ("active", "in_progress", "started"):
        raise ConflictError("Only an active sprint can be completed")
    target_sprint = None
    if payload.move_to_sprint_id:
        target_sprint = await get_or_404(db, user, m.ProjectSprint, payload.move_to_sprint_id)
        if target_sprint.project_id != sprint.project_id or target_sprint.status == "completed":
            raise ConflictError("Target sprint is not available")
    items = list(
        (
            await db.scalars(
                select(m.Task).where(
                    m.Task.sprint_id == sprint.id,
                    m.Task.is_active.is_(True),
                )
            )
        ).all()
    )
    done = {"done", "accepted", "closed"}
    completed = [item for item in items if item.status in done]
    unfinished = [item for item in items if item.status not in done]
    for item in unfinished:
        item.sprint_id = target_sprint.id if target_sprint else None
        item.rank = as_decimal(item.rank) + Decimal("1000")
        item.version = int(item.version or 1) + 1
    cycle_days = []
    lead_days = []
    for item in completed:
        if item.completed_at:
            completed_date = item.completed_at.date()
            cycle_days.append(Decimal((completed_date - (item.start_date or completed_date)).days))
            lead_days.append(Decimal((completed_date - item.created_at.date()).days))
    velocity = sum((as_decimal(item.story_points) for item in completed), Decimal("0"))
    unplanned = sum(
        1 for item in completed if item.created_at.date() > sprint.start_date
    )
    metrics = SprintMetrics(
        velocity=velocity,
        throughput=len(completed),
        cycle_time_days=(sum(cycle_days, Decimal("0")) / len(cycle_days)).quantize(Decimal("0.01"))
        if cycle_days
        else Decimal("0"),
        lead_time_days=(sum(lead_days, Decimal("0")) / len(lead_days)).quantize(Decimal("0.01"))
        if lead_days
        else Decimal("0"),
        carryover=len(unfinished),
        unplanned=unplanned,
        completed_at=utcnow().isoformat(),
    )
    sprint.status = "completed"
    sprint.metrics_json = _jsonable(metrics.model_dump(mode="json"))
    await db.flush()
    return metrics


async def gantt_data(db: AsyncSession, user: User, project_id: UUID) -> GanttResponse:
    project = await get_or_404(db, user, m.Project, project_id)
    tasks = list(
        (
            await db.scalars(
                select(m.Task).where(
                    m.Task.project_id == project_id,
                    m.Task.is_active.is_(True),
                ).order_by(m.Task.rank)
            )
        ).all()
    )
    dependencies = list(
        (
            await db.scalars(
                select(m.ProjectDependency).where(
                    m.ProjectDependency.status == "active",
                    m.ProjectDependency.predecessor_id.in_([task.id for task in tasks])
                    if tasks
                    else False,
                )
            )
        ).all()
    )
    by_id = {task.id: task for task in tasks}
    scheduled: dict[UUID, tuple[date, date]] = {}
    base_start = project.start_date or project.planned_start_date or date.today()
    for task in tasks:
        duration = (
            _days(task.start_date, task.due_date) + 1
            if task.due_date
            else max(1, int((as_decimal(task.estimated_hours) / Decimal("8")).to_integral_value()))
        )
        start = task.start_date or base_start
        scheduled[task.id] = (start, start + timedelta(days=duration - 1))
    for _ in range(len(tasks) + 1):
        changed = False
        for dep in dependencies:
            pred = by_id.get(dep.predecessor_id)
            succ = by_id.get(dep.successor_id)
            if pred is None or succ is None:
                continue
            pred_start, pred_end = scheduled[pred.id]
            succ_start, succ_end = scheduled[succ.id]
            duration = (succ_end - succ_start).days + 1
            lag = int(dep.lag_days or 0)
            if dep.type == "FS":
                candidate = pred_end + timedelta(days=1 + lag)
            elif dep.type == "SS":
                candidate = pred_start + timedelta(days=lag)
            elif dep.type == "FF":
                candidate = pred_end + timedelta(days=lag - duration + 1)
            elif dep.type == "SF":
                candidate = pred_start + timedelta(days=lag - duration + 1)
            else:
                raise ValidationError(f"Unsupported dependency type: {dep.type}")
            if candidate > succ_start:
                scheduled[succ.id] = (candidate, candidate + timedelta(days=duration - 1))
                changed = True
        if not changed:
            break
    else:
        raise ConflictError("Dependency graph contains a cycle")
    end_dates = {key: value[1] for key, value in scheduled.items()}
    max_end = max(end_dates.values()) if end_dates else base_start
    rows: list[GanttTask] = []
    critical_ids = set()
    for task in tasks:
        start, end = scheduled[task.id]
        total_float = (max_end - end).days
        if total_float == 0:
            critical_ids.add(task.id)
        rows.append(
            GanttTask(
                work_item_id=task.id,
                title=task.title,
                start_date=task.start_date,
                end_date=task.due_date,
                scheduled_start=start,
                scheduled_end=end,
                duration_days=(end - start).days + 1,
                total_float_days=total_float,
                critical=total_float == 0,
                status=task.status,
            )
        )
    return GanttResponse(
        project_id=project_id,
        tasks=rows,
        dependencies=[
            {
                "dependency_id": str(dep.id),
                "predecessor_id": str(dep.predecessor_id),
                "successor_id": str(dep.successor_id),
                "type": dep.type,
                "lag_days": dep.lag_days,
            }
            for dep in dependencies
        ],
    )


async def create_baseline(
    db: AsyncSession, user: User, project: m.Project, payload: BaselineCreate
) -> m.ProjectBaseline:
    if payload.change_request_id:
        change = await get_or_404(db, user, m.ProjectChangeRequest, payload.change_request_id)
        if change.project_id != project.id or change.status != "approved":
            raise ConflictError("Baseline changes require an approved change request")
    if payload.approval_id:
        approval = await get_or_404(db, user, m.ProjectApproval, payload.approval_id)
        if approval.entity_id != project.id or approval.status != "approved":
            raise ConflictError("Baseline requires an approved approval record")
    baseline = m.ProjectBaseline(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        project_id=project.id,
        name=payload.name,
        approved_by_id=user.id,
        approved_at=utcnow(),
        status="approved",
    )
    db.add(baseline)
    await db.flush()
    snapshots = [
        ("project", project.id, {
            "planned_start_date": str(project.planned_start_date) if project.planned_start_date else None,
            "planned_end_date": str(project.planned_end_date) if project.planned_end_date else None,
            "budget": str(project.budget),
        })
    ]
    tasks = list(
        (
            await db.scalars(
                select(m.Task).where(m.Task.project_id == project.id, m.Task.is_active.is_(True))
            )
        ).all()
    )
    snapshots.extend(
        (
            "work_item",
            task.id,
            {
                "start_date": str(task.start_date) if task.start_date else None,
                "due_date": str(task.due_date) if task.due_date else None,
                "estimate": str(task.estimated_hours),
                "rank": str(task.rank),
            },
        )
        for task in tasks
    )
    for entity_type, entity_id, snapshot in snapshots:
        db.add(
            m.ProjectBaselineSnapshot(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                baseline_id=baseline.id,
                entity_type=entity_type,
                entity_id=entity_id,
                snapshot_json=snapshot,
                captured_at=utcnow(),
            )
        )
    await db.flush()
    return baseline


async def schedule_variance(
    db: AsyncSession, user: User, project_id: UUID
) -> list[ScheduleVarianceRow]:
    await get_or_404(db, user, m.Project, project_id)
    baseline = await db.scalar(
        select(m.ProjectBaseline)
        .where(
            m.ProjectBaseline.project_id == project_id,
            m.ProjectBaseline.status == "approved",
        )
        .order_by(m.ProjectBaseline.created_at.desc())
    )
    if baseline is None:
        raise NotFoundError("No approved baseline exists for this project")
    snapshots = list(
        (
            await db.scalars(
                select(m.ProjectBaselineSnapshot).where(
                    m.ProjectBaselineSnapshot.baseline_id == baseline.id
                )
            )
        ).all()
    )
    rows: list[ScheduleVarianceRow] = []
    for snapshot in snapshots:
        if snapshot.entity_type == "project":
            project = await get_or_404(db, user, m.Project, project_id)
            rows.append(
                ScheduleVarianceRow(
                    entity_type="project",
                    entity_id=project.id,
                    title=project.name,
                    baseline_start=_parse_date(snapshot.snapshot_json.get("planned_start_date")),
                    baseline_end=_parse_date(snapshot.snapshot_json.get("planned_end_date")),
                    current_start=project.start_date or project.planned_start_date,
                    current_end=project.end_date or project.planned_end_date,
                    start_variance_days=0,
                    end_variance_days=0,
                )
            )
            continue
        task = await db.scalar(
            select(m.Task).where(m.Task.id == snapshot.entity_id, m.Task.is_active.is_(True))
        )
        if task is None:
            continue
        base_start = _parse_date(snapshot.snapshot_json.get("start_date"))
        base_end = _parse_date(snapshot.snapshot_json.get("due_date"))
        rows.append(
            ScheduleVarianceRow(
                entity_type="work_item",
                entity_id=task.id,
                title=task.title,
                baseline_start=base_start,
                baseline_end=base_end,
                current_start=task.start_date,
                current_end=task.due_date,
                start_variance_days=_days(base_start, task.start_date),
                end_variance_days=_days(base_end, task.due_date),
            )
        )
    return rows


def _parse_date(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


async def unbilled_report(db: AsyncSession, user: User, project: m.Project) -> UnbilledReport:
    preview = await billing_preview(db, user, project, project.billing_type)
    return UnbilledReport(
        project_id=project.id,
        currency=project.currency,
        billing_type=preview.billing_type,
        lines=[
            {
                "source_type": line.source_type,
                "source_id": line.source_id,
                "description": line.description,
                "quantity": line.quantity,
                "rate": line.rate,
                "amount": line.amount,
                "tax_code": None,
            }
            for line in preview.lines
        ],
        total=preview.gross_amount,
    )


async def project_costs(db: AsyncSession, user: User, project_id: UUID) -> list[dict[str, Any]]:
    await get_or_404(db, user, m.Project, project_id)
    stmt = select(m.ProjectCostEntry).where(m.ProjectCostEntry.project_id == project_id)
    if user.tenant_id:
        stmt = stmt.where(m.ProjectCostEntry.tenant_id == user.tenant_id)
    entries = list((await db.scalars(stmt)).all())
    return [
        {
            "project_id": entry.project_id,
            "work_item_id": entry.work_item_id,
            "cost_type": entry.cost_type,
            "source": entry.source,
            "amount": entry.amount,
            "currency": entry.currency,
            "posted_at": entry.posted_at.isoformat(),
        }
        for entry in entries
    ]


async def review_billing_run(
    db: AsyncSession, user: User, run: m.ProjectBillingRun, tax_code: Optional[str]
) -> dict[str, Any]:
    if run.status != "draft":
        raise ConflictError("Only draft billing runs can be reviewed")
    lines = list(
        (
            await db.scalars(
                select(m.ProjectBillingLine).where(
                    m.ProjectBillingLine.billing_run_id == run.id,
                    m.ProjectBillingLine.is_active.is_(True),
                )
            )
        ).all()
    )
    tax_rate = Decimal("0")
    if tax_code:
        stmt = select(TaxCode).where(
            TaxCode.code == tax_code,
            TaxCode.is_active.is_(True),
        )
        if run.tenant_id is not None:
            stmt = stmt.where(TaxCode.tenant_id == run.tenant_id)
        elif user.tenant_id is not None:
            stmt = stmt.where(TaxCode.tenant_id == user.tenant_id)
        configured = await db.scalar(stmt)
        if configured is None:
            raise ValidationError(
                f"Finance tax code {tax_code!r} is not configured for this tenant; "
                "configure a GST tax code before reviewing billing"
            )
        tax_rate = as_decimal(configured.igst_rate) / Decimal("100")
    total_tax = Decimal("0")
    for line in lines:
        line.tax_code = tax_code
        total_tax += (as_decimal(line.amount) * tax_rate).quantize(Decimal("0.01"))
    run.tax_amount = total_tax
    run.version = int(run.version or 1) + 1
    await db.flush()
    return {"lines": len(lines), "tax_code": tax_code, "tax_amount": str(total_tax)}


async def submit_intake(
    db: AsyncSession, user: User, payload: IntakeSubmit
) -> m.ProjectApproval:
    draft = m.Project(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        name=payload.title,
        code=f"INT-{uuid4().hex[:8].upper()}",
        number=await sequence_number(db, user, "project", "INT"),
        description=payload.objective,
        client_name=payload.sponsor,
        customer_id=payload.customer_id,
        template_id=payload.template_id,
        currency=payload.currency,
        budget=payload.budget_range or Decimal("0"),
        start_date=payload.requested_start_date,
        end_date=payload.requested_end_date,
        status="intake",
    )
    db.add(draft)
    await db.flush()
    approval = m.ProjectApproval(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entity_type="project",
        entity_id=draft.id,
        approval_type="intake",
        status="pending",
        comments=payload.objective,
    )
    db.add(approval)
    await db.flush()
    await record_activity(
        db,
        user,
        "project",
        draft.id,
        "intake.submitted",
        {"approval_id": str(approval.id), "project_id": str(draft.id)},
    )
    return approval


async def decide_intake(
    db: AsyncSession, user: User, approval: m.ProjectApproval, payload: IntakeDecision
) -> m.Project:
    project = await get_or_404(db, user, m.Project, approval.entity_id)
    if approval.status != "pending":
        raise ConflictError("Intake approval has already been decided")
    approval.status = "approved" if payload.decision == "approve" else "rejected"
    approval.decision = payload.decision
    approval.decision_at = utcnow()
    approval.comments = payload.comment or payload.clarification
    if payload.decision == "approve":
        project.status = "draft"
        template = None
        if project.template_id:
            template = await db.scalar(
                select(m.ProjectTemplate).where(m.ProjectTemplate.id == project.template_id)
            )
        if template:
            for item in template.structure_json or []:
                if isinstance(item, dict) and item.get("title"):
                    board = await db.scalar(
                        select(m.ProjectBoard).where(m.ProjectBoard.project_id == project.id)
                    )
                    db.add(
                        m.Task(
                            tenant_id=user.tenant_id,
                            created_by_id=user.id,
                            project_id=project.id,
                            title=item["title"],
                            number=await sequence_number(db, user, "work_item", "PRJ-T"),
                            description=item.get("description"),
                            status="backlog",
                            work_item_type=item.get("work_item_type", "task"),
                            board_id=board.id if board else None,
                        )
                    )
    else:
        project.is_active = False
    await db.flush()
    return project


async def send_notification(
    db: AsyncSession, user: User, payload: NotificationRequest, project_id: Optional[UUID] = None
) -> m.ProjectActivity:
    if payload.channel == "whatsapp" and not payload.consent_reference:
        raise ForbiddenError("WhatsApp notifications require a consent reference")
    if project_id is None:
        project_id = await entity_project_id(db, user, payload.entity_type, payload.entity_id)
    message = await send_message(
        db,
        tenant_id=user.tenant_id,
        channel=payload.channel,
        to=payload.to,
        body=payload.body,
        template=payload.template,
        module="projects",
        related_id=payload.entity_id,
        payload={"project_id": str(project_id)},
    )
    activity = await record_activity(
        db,
        user,
        payload.entity_type,
        payload.entity_id,
        "notification.sent",
        {
            "project_id": str(project_id),
            "template": payload.template,
            "channel": payload.channel,
        },
    )
    activity.template_code = payload.template
    activity.recipient = payload.to
    activity.consent_reference = payload.consent_reference
    activity.message_id = getattr(message, "external_id", None)
    await db.flush()
    return activity


async def stage_import(db: AsyncSession, user: User, payload: ImportSubmit) -> m.ProjectImportBatch:
    mapping = dict(payload.mapping)
    batch = m.ProjectImportBatch(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        provider=payload.provider,
        file_document_id=payload.file_document_id,
        status="staged",
        rows_total=len(payload.rows),
        payload_json={"rows": payload.rows},
        mapping_json=mapping,
    )
    db.add(batch)
    await db.flush()
    for index, raw in enumerate(payload.rows, start=1):
        normalized = _normalize_import_row(raw, mapping)
        errors = _validate_import_row(normalized)
        db.add(
            m.ProjectImportRow(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                batch_id=batch.id,
                row_key=str(raw.get("external_id") or raw.get("key") or index),
                source_type=normalized.get("source_type", "work_item"),
                raw_json=_jsonable(raw),
                normalized_json=_jsonable(normalized),
                validation_json={"errors": errors},
                status="invalid" if errors else "staged",
                error_text="; ".join(errors) or None,
            )
        )
    batch.rows_failed = sum(1 for row in payload.rows if _validate_import_row(_normalize_import_row(row, mapping)))
    await db.flush()
    await record_activity(
        db, user, "import_batch", batch.id, "import.staged", {"rows": batch.rows_total}
    )
    return batch


def _normalize_import_row(raw: dict[str, Any], mapping: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for target, source in mapping.items():
        if not isinstance(source, str):
            continue
        value = raw.get(source)
        if value is not None:
            result[target] = value
    for key in ("title", "name", "project_id", "external_id", "source_type", "status"):
        if key in raw and key not in result:
            result[key] = raw[key]
    result["source_type"] = result.get("source_type") or "work_item"
    return result


def _validate_import_row(row: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not row.get("title") and not row.get("name"):
        errors.append("title is required")
    if row.get("source_type") == "work_item" and not row.get("project_id"):
        errors.append("project_id is required for work items")
    return errors


async def approve_import(
    db: AsyncSession, user: User, batch: m.ProjectImportBatch, payload: ImportMappingDecision
) -> m.ProjectImportBatch:
    if batch.status not in ("staged", "validated"):
        raise ConflictError("This import batch cannot be approved")
    if not payload.approved:
        batch.status = "rejected"
        await db.flush()
        return batch
    batch.mapping_json = payload.mapping
    batch.status = "approved"
    batch.approved_by_id = user.id
    batch.approved_at = utcnow()
    rows = list(
        (
            await db.scalars(
                select(m.ProjectImportRow).where(m.ProjectImportRow.batch_id == batch.id)
            )
        ).all()
    )
    plan: list[dict[str, Any]] = []
    for row in rows:
        errors = _validate_import_row(_normalize_import_row(row.raw_json or {}, payload.mapping))
        row.validation_json = {"errors": errors}
        row.error_text = "; ".join(errors) or None
        row.status = "invalid" if errors else "approved"
        plan.append({"row_id": str(row.id), "status": row.status, "errors": errors})
    batch.rows_failed = sum(1 for item in plan if item["errors"])
    batch.rows_imported = len(plan) - batch.rows_failed
    batch.dry_run_json = {"plan": plan}
    await db.flush()
    await record_activity(
        db,
        user,
        "import_batch",
        batch.id,
        "import.dry_run",
        {"rows": batch.rows_total, "failed": batch.rows_failed},
    )
    return batch


async def commit_import(db: AsyncSession, user: User, batch: m.ProjectImportBatch) -> m.ProjectImportBatch:
    if batch.status != "approved":
        raise ConflictError("Import batch must be approved before commit")
    rows = list(
        (
            await db.scalars(
                select(m.ProjectImportRow).where(
                    m.ProjectImportRow.batch_id == batch.id,
                    m.ProjectImportRow.status == "approved",
                )
            )
        ).all()
    )
    for row in rows:
        data = dict(row.normalized_json or {})
        data.pop("external_id", None)
        source_type = data.pop("source_type", "work_item")
        project_id = UUID(str(data.pop("project_id"))) if data.get("project_id") else None
        if not project_id:
            row.status = "invalid"
            row.error_text = "project_id is required"
            continue
        if source_type == "work_item":
            task = m.Task(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                project_id=project_id,
                title=data.get("title") or data.get("name") or "Imported work item",
                number=await sequence_number(db, user, "work_item", "PRJ-T"),
                description=data.get("description"),
                status=data.get("status", "backlog"),
                work_item_type=data.get("work_item_type", "task"),
                start_date=_parse_date(data.get("start_date")),
                due_date=_parse_date(data.get("end_date") or data.get("due_date")),
            )
            db.add(task)
            await db.flush()
            row.target_id = task.id
            row.status = "committed"
    batch.status = "committed"
    batch.committed_at = utcnow()
    await db.flush()
    await record_activity(
        db, user, "import_batch", batch.id, "import.committed", {"rows": len(rows)}
    )
    return batch


async def rollback_import(db: AsyncSession, user: User, batch: m.ProjectImportBatch) -> m.ProjectImportBatch:
    if batch.status != "committed":
        raise ConflictError("Only committed import batches can be rolled back")
    rows = list(
        (
            await db.scalars(
                select(m.ProjectImportRow).where(
                    m.ProjectImportRow.batch_id == batch.id,
                    m.ProjectImportRow.target_id.is_not(None),
                )
            )
        ).all()
    )
    for row in rows:
        task = await db.scalar(select(m.Task).where(m.Task.id == row.target_id))
        if task is not None and task.is_active and not task.invoiced_amount and not task.actual_hours:
            await db.delete(task)
        row.status = "rolled_back"
    batch.status = "rolled_back"
    batch.rolled_back_at = utcnow()
    await db.flush()
    await record_activity(
        db, user, "import_batch", batch.id, "import.rolled_back", {"rows": len(rows)}
    )
    return batch


def _mask_report_rows(rows: list[dict[str, Any]], user: User) -> list[dict[str, Any]]:
    if user.is_superuser or user.has_permission("projects.finance.read"):
        return rows
    masked = []
    for row in rows:
        item = dict(row)
        for field in SENSITIVE_REPORT_FIELDS:
            if field in item:
                item[field] = "0" if isinstance(item[field], str) else 0
        masked.append(item)
    return masked


async def run_report(
    db: AsyncSession, user: User, key: str, project_id: Optional[UUID] = None
) -> ReportResponse:
    resolved_key = REPORT_ALIASES.get(key, key)
    if resolved_key not in REPORT_KEYS:
        raise NotFoundError(f"Unknown report: {key}")
    if project_id:
        await get_or_404(db, user, m.Project, project_id)
    projects_stmt = select(m.Project).where(m.Project.is_active.is_(True))
    if user.tenant_id:
        projects_stmt = projects_stmt.where(m.Project.tenant_id == user.tenant_id)
    if project_id:
        projects_stmt = projects_stmt.where(m.Project.id == project_id)
    projects = list((await db.scalars(projects_stmt)).all())
    rows: list[dict[str, Any]] = []
    if resolved_key in ("project-health", "budget-vs-actual", "earned-value"):
        for project in projects:
            blockers = int(
                await db.scalar(
                    select(func.count()).select_from(m.Task).where(
                        m.Task.project_id == project.id,
                        m.Task.status == "blocked",
                        m.Task.is_active.is_(True),
                    )
                ) or 0
            )
            risks = as_decimal(
                await db.scalar(
                    select(func.coalesce(func.max(m.ProjectRisk.score), 0)).where(
                        m.ProjectRisk.project_id == project.id
                    )
                )
            )
            planned = as_decimal(
                await db.scalar(
                    select(func.coalesce(func.sum(m.Task.estimated_hours), 0)).where(
                        m.Task.project_id == project.id
                    )
                )
            )
            actual = as_decimal(
                await db.scalar(
                    select(func.coalesce(func.sum(m.Task.actual_hours), 0)).where(
                        m.Task.project_id == project.id
                    )
                )
            )
            earned = as_decimal(project.total_billed)
            rows.append(
                {
                    "project_id": str(project.id),
                    "name": project.name,
                    "status": project.status,
                    "health": project.health,
                    "blockers": blockers,
                    "risk_score": str(risks),
                    "schedule_variance_days": _days(
                        project.planned_end_date, project.end_date or project.planned_end_date
                    ),
                    "budget": str(project.budget),
                    "billed": str(project.total_billed),
                    "cost": str(project.total_cost),
                    "wip": str(project.wip_amount),
                    "margin": str(project.margin_amount),
                    "planned_hours": str(planned),
                    "actual_hours": str(actual),
                    "earned_value": str(earned),
                    "cpi": str((earned / as_decimal(project.total_cost)).quantize(Decimal("0.01")))
                    if as_decimal(project.total_cost) > 0
                    else "0",
                    "spi": str((earned / planned).quantize(Decimal("0.01")))
                    if planned > 0
                    else "0",
                }
            )
    elif resolved_key in ("utilisation", "workload-heatmap"):
        rows = [
            row.model_dump(mode="json")
            for row in await _workload_rows_for_report(db, user)
        ]
    elif resolved_key in ("unbilled-wip", "billing-leakage"):
        for project in projects:
            report = await unbilled_report(db, user, project)
            rows.append(
                {
                    "project_id": str(project.id),
                    "billing_type": report.billing_type,
                    "total": str(report.total),
                    "lines": len(report.lines),
                }
            )
            if resolved_key == "billing-leakage":
                billable = int(
                    await db.scalar(
                        select(func.count()).select_from(m.Task).where(
                            m.Task.project_id == project.id,
                            m.Task.is_billable.is_(True),
                            m.Task.is_active.is_(True),
                        ) or 0
                    )
                )
                with_time = int(
                    await db.scalar(
                        select(func.count(func.distinct(m.ProjectTimeEntry.work_item_id)))
                        .join(m.Task, m.Task.id == m.ProjectTimeEntry.work_item_id)
                        .where(
                            m.Task.project_id == project.id,
                            m.ProjectTimeEntry.status == "approved",
                        ) or 0
                    )
                )
                rows[-1]["billable_work_items"] = billable
                rows[-1]["without_approved_time"] = max(0, billable - with_time)
    elif resolved_key == "velocity":
        stmt = select(m.ProjectSprint).where(m.ProjectSprint.status == "completed")
        if user.tenant_id:
            stmt = stmt.where(m.ProjectSprint.tenant_id == user.tenant_id)
        if project_id:
            stmt = stmt.where(m.ProjectSprint.project_id == project_id)
        for sprint in await db.scalars(stmt.order_by(m.ProjectSprint.end_date.desc())):
            metrics = sprint.metrics_json or {}
            rows.append(
                {
                    "project_id": str(sprint.project_id),
                    "sprint_id": str(sprint.id),
                    "name": sprint.name,
                    "end_date": str(sprint.end_date),
                    "velocity": str(metrics.get("velocity", 0)),
                    "throughput": metrics.get("throughput", 0),
                    "carryover": metrics.get("carryover", 0),
                }
            )
    elif resolved_key in ("cycle-lead-time", "cumulative-flow", "throughput-rework"):
        stmt = select(m.Task).where(m.Task.is_active.is_(True))
        if user.tenant_id:
            stmt = stmt.where(m.Task.tenant_id == user.tenant_id)
        if project_id:
            stmt = stmt.where(m.Task.project_id == project_id)
        statuses: dict[str, int] = defaultdict(int)
        for task in await db.scalars(stmt):
            statuses[task.status] += 1
            if resolved_key == "cycle-lead-time" and task.completed_at:
                rows.append(
                    {
                        "project_id": str(task.project_id),
                        "work_item_id": str(task.id),
                        "cycle_time_days": str(
                            (task.completed_at.date() - (task.start_date or task.created_at.date())).days
                        ),
                        "lead_time_days": str(
                            (task.completed_at.date() - task.created_at.date()).days
                        ),
                    }
                )
            if resolved_key == "throughput-rework":
                rows.append(
                    {
                        "project_id": str(task.project_id),
                        "work_item_id": str(task.id),
                        "completed": task.completed_at is not None,
                        "reopened_count": task.reopened_count,
                    }
                )
        if resolved_key == "cumulative-flow":
            rows = [
                {"project_id": str(project_id) if project_id else "", "status": status, "count": count}
                for status, count in sorted(statuses.items())
            ]
    elif resolved_key == "risk-heatmap":
        stmt = select(m.ProjectRisk)
        if user.tenant_id:
            stmt = stmt.where(m.ProjectRisk.tenant_id == user.tenant_id)
        if project_id:
            stmt = stmt.where(m.ProjectRisk.project_id == project_id)
        for risk in await db.scalars(stmt):
            rows.append(
                {
                    "project_id": str(risk.project_id),
                    "risk_id": str(risk.id),
                    "title": risk.title,
                    "probability": str(risk.probability),
                    "impact": str(risk.impact),
                    "score": str(risk.score),
                    "status": risk.status,
                }
            )
    elif resolved_key == "milestone-schedule":
        stmt = select(m.ProjectMilestone)
        if user.tenant_id:
            stmt = stmt.where(m.ProjectMilestone.tenant_id == user.tenant_id)
        if project_id:
            stmt = stmt.where(m.ProjectMilestone.project_id == project_id)
        for milestone in await db.scalars(stmt):
            rows.append(
                {
                    "project_id": str(milestone.project_id),
                    "milestone_id": str(milestone.id),
                    "name": milestone.name,
                    "due_date": str(milestone.due_date) if milestone.due_date else None,
                    "accepted_at": milestone.accepted_at.isoformat() if milestone.accepted_at else None,
                    "amount": str(milestone.amount),
                    "status": milestone.status,
                }
            )
    elif resolved_key == "timesheet-compliance":
        stmt = select(m.ProjectTimesheet)
        if user.tenant_id:
            stmt = stmt.where(m.ProjectTimesheet.tenant_id == user.tenant_id)
        for timesheet in await db.scalars(stmt):
            rows.append(
                {
                    "timesheet_id": str(timesheet.id),
                    "employee_id": str(timesheet.employee_id),
                    "week_start": str(timesheet.week_start),
                    "status": timesheet.status,
                    "submitted_at": timesheet.submitted_at.isoformat()
                    if timesheet.submitted_at
                    else None,
                    "hours": str(timesheet.total_hours),
                }
            )
    elif resolved_key == "portfolio-benefits":
        stmt = select(m.ProjectGoal)
        if user.tenant_id:
            stmt = stmt.where(m.ProjectGoal.tenant_id == user.tenant_id)
        if project_id:
            stmt = stmt.where(m.ProjectGoal.project_id == project_id)
        for goal in await db.scalars(stmt):
            rows.append(
                {
                    "goal_id": str(goal.id),
                    "project_id": str(goal.project_id) if goal.project_id else None,
                    "program_id": str(goal.program_id) if goal.program_id else None,
                    "portfolio_id": str(goal.portfolio_id) if goal.portfolio_id else None,
                    "title": goal.title,
                    "metric": goal.metric,
                    "target": str(goal.target),
                    "current": str(goal.current),
                    "status": goal.status,
                }
            )
    elif resolved_key == "ai-review-queue":
        signal_stmt = select(m.ProjectAiSignal)
        action_stmt = select(m.ProjectAiAction)
        if user.tenant_id:
            signal_stmt = signal_stmt.where(m.ProjectAiSignal.tenant_id == user.tenant_id)
            action_stmt = action_stmt.where(m.ProjectAiAction.tenant_id == user.tenant_id)
        if project_id:
            signal_stmt = signal_stmt.where(m.ProjectAiSignal.entity_id == project_id)
            action_stmt = action_stmt.where(m.ProjectAiAction.entity_id == project_id)
        for signal in await db.scalars(signal_stmt):
            rows.append(
                {
                    "type": "signal",
                    "id": str(signal.id),
                    "signal_type": signal.signal_type,
                    "score": str(signal.score),
                    "review_status": signal.review_status,
                    "model_version": signal.model_version,
                    "features": _jsonable(signal.features_json or {}),
                }
            )
        for action in await db.scalars(action_stmt):
            rows.append(
                {
                    "type": "action",
                    "id": str(action.id),
                    "action_type": action.action_type,
                    "status": action.status,
                    "executed_at": action.executed_at.isoformat() if action.executed_at else None,
                    "reversal_reference": action.reversal_reference,
                }
            )
    return ReportResponse(
        key=key,
        project_id=project_id,
        rows=_mask_report_rows(rows, user),
        meta={"generated_at": utcnow().isoformat(), "row_count": len(rows)},
    )


async def _workload_rows_for_report(db: AsyncSession, user: User) -> list[Any]:
    from app.modules.projects.services import workload_rows

    return await workload_rows(db, user)
