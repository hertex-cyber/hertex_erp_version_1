from datetime import date
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import Field, create_model
from sqlalchemy import JSON
from sqlalchemy.sql.schema import Column

from app.core.schemas import ORMModel

CREATE_EXCLUDED = {
    "id",
    "tenant_id",
    "created_by_id",
    "created_at",
    "updated_at",
    "is_active",
    "version",
    "number",
    "idempotency_key",
    "actual_hours",
    "actual_cost",
    "actual_revenue",
    "billable_amount",
    "invoiced_amount",
    "total_billed",
    "total_cost",
    "total_expense",
    "wip_amount",
    "margin_amount",
    "margin_percent",
    "ai_risk_score",
    "score",
    "utilization_percent",
    "overallocated",
    "run_count",
    "metrics_json",
    "payload_json",
    "mapping_json",
    "validation_json",
    "dry_run_json",
    "approved_at",
    "committed_at",
    "rolled_back_at",
    "split_allowed",
}
SENSITIVE_UPDATE_FIELDS = {
    "status",
    "actual_hours",
    "remaining_hours",
    "actual_cost",
    "actual_revenue",
    "billable_rate",
    "cost_rate",
    "default_cost_rate",
    "default_billable_rate",
    "amount",
    "rate",
    "quantity",
    "budget",
    "budget_hours",
    "budget_cost",
    "budget_revenue",
    "contract_value",
    "total_billed",
    "total_cost",
    "total_expense",
    "gross_amount",
    "tax_amount",
    "wip_amount",
    "margin_amount",
    "margin_percent",
    "invoiced_amount",
    "billable_amount",
    "utilization_percent",
    "overallocated",
    "ai_risk_score",
    "score",
    "version",
    "approved_by_id",
    "approved_at",
    "accepted_by_id",
    "accepted_at",
    "posted_at",
    "published_at",
    "finance_invoice_id",
    "invoice_link_id",
    "on_behalf_of_id",
    "reversal_reference",
    "executed_at",
    "run_count",
    "metrics_json",
    "payload_json",
    "mapping_json",
    "validation_json",
    "dry_run_json",
    "committed_at",
    "rolled_back_at",
    "split_allowed",
    "template_code",
    "recipient",
    "message_id",
    "consent_reference",
}
UPDATE_EXCLUDED = CREATE_EXCLUDED | SENSITIVE_UPDATE_FIELDS
SCHEMA_CACHE: dict[tuple[str, str], type[ORMModel]] = {}


def _column_annotation(column: Column) -> Any:
    if isinstance(column.type, JSON):
        return Any
    try:
        return column.type.python_type
    except (NotImplementedError, AttributeError):
        return Any


def _is_optional(column: Column) -> bool:
    return (
        column.nullable
        or column.default is not None
        or column.server_default is not None
        or column.primary_key
    )


def schema_for(model: Any, mode: str) -> type[ORMModel]:
    cache_key = (model.__name__, mode)
    if cache_key in SCHEMA_CACHE:
        return SCHEMA_CACHE[cache_key]

    excluded = {
        "create": CREATE_EXCLUDED,
        "update": UPDATE_EXCLUDED,
        "read": set(),
    }[mode]
    fields: dict[str, tuple[Any, Any]] = {}
    for column in model.__table__.columns:
        if column.name in excluded:
            continue
        annotation = _column_annotation(column)
        if mode == "update":
            annotation = Optional[annotation]
            default = None
        elif mode != "read" and _is_optional(column):
            annotation = Optional[annotation]
            default = None
        elif mode == "read":
            annotation = Optional[annotation]
            default = None
        else:
            default = ...
        fields[column.name] = (annotation, default)

    schema = create_model(f"{model.__name__}{mode.title()}", __base__=ORMModel, **fields)
    SCHEMA_CACHE[cache_key] = schema
    return schema


class TransitionRequest(ORMModel):
    event: str = Field(min_length=1, max_length=50)
    comment: Optional[str] = None
    actor_employee_id: Optional[UUID] = None


class ProjectCompletionRequest(TransitionRequest):
    waiver_code: Optional[str] = Field(default=None, min_length=4, max_length=100)
    waiver_approval_id: Optional[UUID] = None


class TimeEntryDecision(ORMModel):
    comment: Optional[str] = None


class BillingRunCreate(ORMModel):
    project_id: UUID
    period: str = Field(min_length=4, max_length=20)
    billing_type: Optional[str] = None
    idempotency_key: Optional[str] = None


class BillingPostRequest(ORMModel):
    customer_id: Optional[UUID] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None
    tax_amount: Decimal = Decimal("0")
    tax_code: Optional[str] = None
    notes: Optional[str] = None


class RateChangeRequest(ORMModel):
    cost_rate: Optional[Decimal] = None
    billable_rate: Optional[Decimal] = None
    reason: str = Field(min_length=3, max_length=500)


class CapacityQuery(ORMModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    employee_id: Optional[UUID] = None


class AiSignalRequest(ORMModel):
    signal_type: str = Field(min_length=1, max_length=50)
    entity_type: str = Field(min_length=1, max_length=50)
    entity_id: UUID
    score: Decimal = Decimal("0")
    features: dict[str, Any] = Field(default_factory=dict)
    explanation: Optional[str] = None


class AiActionDecision(ORMModel):
    comment: Optional[str] = None
    reversal_reference: Optional[str] = None


class AutomationRunRequest(ORMModel):
    trigger_entity: str = Field(min_length=1, max_length=50)
    trigger_id: UUID


class ProjectSummary(ORMModel):
    project_id: UUID
    total_tasks: int
    done_tasks: int
    open_tasks: int
    total_budget: Decimal
    estimated_hours: Decimal
    actual_hours: Decimal
    billable_value: Decimal


class ProfitabilitySummary(ORMModel):
    project_id: UUID
    budget_revenue: Decimal
    budget_cost: Decimal
    billed: Decimal
    labour_cost: Decimal
    expense_cost: Decimal
    other_cost: Decimal
    wip: Decimal
    margin_amount: Decimal
    margin_percent: Decimal


class CapacityRow(ORMModel):
    employee_id: UUID
    employee_name: str
    week_start: date
    capacity_hours: Decimal
    planned_leave_hours: Decimal
    holiday_hours: Decimal = Decimal("0")
    employment_type: str = "full_time"
    declared_weekly_hours: Decimal = Decimal("40")
    capacity_source: str = "hr"
    booked_hours: Decimal
    available_hours: Decimal
    utilization_percent: Decimal
    overallocated: bool


class WorkloadRow(ORMModel):
    employee_id: UUID
    employee_name: str
    week_start: date
    booked_hours: Decimal
    available_hours: Decimal
    utilization_percent: Decimal
    overallocated: bool


class CriticalPathStep(ORMModel):
    work_item_id: UUID
    title: str
    start_date: Optional[date]
    end_date: Optional[date]
    duration_days: int


class CriticalPathResponse(ORMModel):
    project_id: UUID
    steps: list[CriticalPathStep]
    total_days: int


class BillingLinePreview(ORMModel):
    source_type: str
    source_id: UUID
    description: str
    quantity: Decimal
    rate: Decimal
    amount: Decimal


class BillingPreview(ORMModel):
    project_id: UUID
    billing_type: str
    lines: list[BillingLinePreview]
    gross_amount: Decimal
    tax_amount: Decimal
    total_amount: Decimal


class GovernanceSummary(ORMModel):
    project_id: UUID
    open_risks: int
    escalated_risks: int
    open_issues: int
    pending_approvals: int
    status_updates: int
    goals: int


class OutboxStats(ORMModel):
    pending: int
    published: int
    failed: int


class WorkItemLinkCreate(ORMModel):
    linked_work_item_id: UUID
    link_type: str = Field(default="relates_to", min_length=3, max_length=30)


class CommentCreate(ORMModel):
    body: str = Field(min_length=1)
    mentions: list[str] = Field(default_factory=list)
    parent_comment_id: Optional[UUID] = None


class CommentUpdate(ORMModel):
    body: Optional[str] = Field(default=None, min_length=1)
    mentions: Optional[list[str]] = None


class BacklogMove(ORMModel):
    work_item_id: UUID
    rank: Optional[Decimal] = None
    sprint_id: Optional[UUID] = None
    board_column_id: Optional[UUID] = None


class BacklogUpdate(ORMModel):
    moves: list[BacklogMove]


class SprintCompleteRequest(ORMModel):
    move_to_sprint_id: Optional[UUID] = None
    comment: Optional[str] = None


class SprintMetrics(ORMModel):
    velocity: Decimal
    throughput: int
    cycle_time_days: Decimal
    lead_time_days: Decimal
    carryover: int
    unplanned: int
    completed_at: Optional[str] = None


class GanttTask(ORMModel):
    work_item_id: UUID
    title: str
    start_date: Optional[date]
    end_date: Optional[date]
    scheduled_start: date
    scheduled_end: date
    duration_days: int
    total_float_days: int = 0
    critical: bool = False
    status: str


class GanttResponse(ORMModel):
    project_id: UUID
    tasks: list[GanttTask]
    dependencies: list[dict[str, Any]]


class BaselineCreate(ORMModel):
    name: str = Field(min_length=2, max_length=150)
    change_request_id: Optional[UUID] = None
    approval_id: Optional[UUID] = None
    comment: Optional[str] = None


class ScheduleVarianceRow(ORMModel):
    entity_type: str
    entity_id: UUID
    title: str
    baseline_start: Optional[date]
    baseline_end: Optional[date]
    current_start: Optional[date]
    current_end: Optional[date]
    start_variance_days: int
    end_variance_days: int


class UnbilledRow(ORMModel):
    source_type: str
    source_id: UUID
    description: str
    quantity: Decimal
    rate: Decimal
    amount: Decimal
    tax_code: Optional[str] = None


class UnbilledReport(ORMModel):
    project_id: UUID
    currency: str
    billing_type: str
    lines: list[UnbilledRow]
    total: Decimal


class CostRow(ORMModel):
    project_id: UUID
    work_item_id: Optional[UUID]
    cost_type: str
    source: str
    amount: Decimal
    currency: str
    posted_at: Optional[str] = None


class BillingReviewRequest(ORMModel):
    tax_code: Optional[str] = None
    tax_amount: Optional[Decimal] = None
    comment: Optional[str] = None


class IntakeSubmit(ORMModel):
    title: str = Field(min_length=3, max_length=200)
    objective: str = Field(min_length=3)
    sponsor: Optional[str] = None
    budget_range: Optional[Decimal] = None
    requested_start_date: Optional[date] = None
    requested_end_date: Optional[date] = None
    template_id: Optional[UUID] = None
    customer_id: Optional[UUID] = None
    currency: str = "INR"


class IntakeDecision(ORMModel):
    decision: str = Field(default="approve", pattern="^(approve|reject)$")
    comment: Optional[str] = None
    clarification: Optional[str] = None
    notify: Optional[dict[str, Any]] = None


class NotificationRequest(ORMModel):
    channel: str = Field(pattern="^(email|whatsapp|calendar)$")
    to: str = Field(min_length=3)
    template: str = Field(min_length=2, max_length=80)
    body: str = Field(min_length=1)
    entity_type: str = "project"
    entity_id: UUID
    consent_reference: Optional[str] = None


class ImportSubmit(ORMModel):
    provider: str = Field(pattern="^(jira|microsoft_project|csv)$")
    rows: list[dict[str, Any]]
    mapping: dict[str, Any] = Field(default_factory=dict)
    file_document_id: Optional[UUID] = None


class ImportMappingDecision(ORMModel):
    mapping: dict[str, Any] = Field(default_factory=dict)
    approved: bool = True
    comment: Optional[str] = None


class ReportResponse(ORMModel):
    key: str
    project_id: Optional[UUID] = None
    rows: list[dict[str, Any]]
    meta: dict[str, Any] = Field(default_factory=dict)
