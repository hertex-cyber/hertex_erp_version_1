from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBaseModel


class Project(TenantBaseModel):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_projects_tenant_number"),
        CheckConstraint("end_date IS NULL OR start_date IS NULL OR end_date >= start_date", name="ck_projects_date_order"),
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    planned_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    baseline_start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    baseline_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    forecast_end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    budget: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    budget_hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    budget_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    budget_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    contract_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_billed: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_expense: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    wip_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    margin_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    margin_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=0)
    client_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    customer_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True
    )
    billing_contact_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    portfolio_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_portfolios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    program_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_programs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    template_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_templates.id", ondelete="SET NULL"), nullable=True
    )
    manager_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    manager_employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    billing_type: Mapped[str] = mapped_column(String(30), default="time_and_material", index=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    health: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    health_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    methodology: Mapped[str] = mapped_column(String(20), default="agile")
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    tasks: Mapped[list["Task"]] = relationship(back_populates="project", lazy="selectin")


class Task(TenantBaseModel):
    __tablename__ = "project_tasks"
    __table_args__ = (
        UniqueConstraint("tenant_id", "number", name="uq_project_tasks_tenant_number"),
        Index("ix_project_tasks_board_rank", "board_id", "rank"),
    )

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="backlog", index=True)
    state_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    work_item_type: Mapped[str] = mapped_column(String(30), default="task", index=True)
    parent_work_item_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    assignee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sprint_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_sprints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    board_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_boards.id", ondelete="SET NULL"), nullable=True, index=True
    )
    board_column_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_board_columns.id", ondelete="SET NULL"), nullable=True
    )
    milestone_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_milestones.id", ondelete="SET NULL"), nullable=True
    )
    release_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_releases.id", ondelete="SET NULL"), nullable=True
    )
    rank: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=1000, nullable=False)
    story_points: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    business_value: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    impact: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    confidence: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    effort: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    estimated_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    actual_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    planned_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    remaining_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    actual_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    actual_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    billable_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    invoiced_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    billable_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_billable: Mapped[bool] = mapped_column(Boolean, default=True)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blocked_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="SET NULL"), nullable=True
    )
    duplicate_of_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    resolution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reopened_count: Mapped[int] = mapped_column(Integer, default=0)
    wip_limit_override: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ai_risk_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    project: Mapped[Project] = relationship(back_populates="tasks", lazy="selectin")


class ProjectPortfolio(TenantBaseModel):
    __tablename__ = "project_portfolios"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_pm_portfolios_tenant_code"),)

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    owner_employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    health: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    budget: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")


class ProjectProgram(TenantBaseModel):
    __tablename__ = "project_programs"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_pm_programs_tenant_code"),)

    portfolio_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_portfolios.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    manager_employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    benefits_json: Mapped[Any] = mapped_column(JSON, default=dict)
    health: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectPhase(TenantBaseModel):
    __tablename__ = "project_phases"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, default=1)
    start_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)


class ProjectSprint(TenantBaseModel):
    __tablename__ = "project_sprints"
    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "number", name="uq_pm_sprints_number"),)

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    capacity_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    capacity_points: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    metrics_json: Mapped[Any] = mapped_column(JSON, default=dict)


class ProjectBoard(TenantBaseModel):
    __tablename__ = "project_boards"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    type: Mapped[str] = mapped_column(String(30), default="kanban")
    wip_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectBoardColumn(TenantBaseModel):
    __tablename__ = "project_board_columns"
    __table_args__ = (UniqueConstraint("board_id", "sequence", name="uq_pm_board_columns_sequence"),)

    board_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_boards.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    wip_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    wip_enforced: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status_category: Mapped[str] = mapped_column(String(30), default="todo")
    status: Mapped[str] = mapped_column(String(30), default="active")


class ProjectWorkItemLink(TenantBaseModel):
    __tablename__ = "project_work_item_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "work_item_id", "linked_work_item_id", "link_type", name="uq_pm_work_item_links"),
    )

    work_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    linked_work_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    link_type: Mapped[str] = mapped_column(String(30), default="relates_to", index=True)


class ProjectLabel(TenantBaseModel):
    __tablename__ = "project_labels"
    __table_args__ = (UniqueConstraint("tenant_id", "project_id", "name", name="uq_pm_labels_tenant_project"),)

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    color: Mapped[str] = mapped_column(String(30), default="stone")
    status: Mapped[str] = mapped_column(String(30), default="active")


class ProjectWorkItemLabel(TenantBaseModel):
    __tablename__ = "project_work_item_labels"
    __table_args__ = (UniqueConstraint("work_item_id", "label_id", name="uq_pm_work_item_labels"),)

    work_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    label_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_labels.id", ondelete="CASCADE"), nullable=False, index=True
    )


class ProjectCustomField(TenantBaseModel):
    __tablename__ = "project_custom_fields"
    __table_args__ = (UniqueConstraint("tenant_id", "entity_type", "code", name="uq_pm_custom_fields"),)

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(150), nullable=False)
    type: Mapped[str] = mapped_column(String(30), default="text")
    options_json: Mapped[Any] = mapped_column(JSON, default=list)
    required: Mapped[bool] = mapped_column(Boolean, default=False)
    visible_roles: Mapped[Any] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="active")


class ProjectWorkItemFieldValue(TenantBaseModel):
    __tablename__ = "project_work_item_field_values"
    __table_args__ = (UniqueConstraint("work_item_id", "field_id", name="uq_pm_field_values"),)

    work_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    field_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_custom_fields.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value_json: Mapped[Any] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ProjectWorkflowScheme(TenantBaseModel):
    __tablename__ = "project_workflow_schemes"
    __table_args__ = (UniqueConstraint("tenant_id", "name", name="uq_pm_workflow_schemes_tenant_name"),)

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), default="work_item", index=True)
    work_item_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    statuses_json: Mapped[Any] = mapped_column(JSON, default=list)
    status_categories_json: Mapped[Any] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectWorkflowTransition(TenantBaseModel):
    __tablename__ = "project_workflow_transitions"

    scheme_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_workflow_schemes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[str] = mapped_column(String(50), nullable=False)
    event: Mapped[str] = mapped_column(String(50), nullable=False)
    to_status: Mapped[str] = mapped_column(String(50), nullable=False)
    guard_code: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    required_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    required_fields_json: Mapped[Any] = mapped_column(JSON, default=list)
    side_effects_json: Mapped[Any] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="active")


class ProjectApproval(TenantBaseModel):
    __tablename__ = "project_approvals"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    approval_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    approver_employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    decision: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    decision_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    comments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ProjectTemplate(TenantBaseModel):
    __tablename__ = "project_templates"

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), default="project", index=True)
    workflow_scheme_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_workflow_schemes.id", ondelete="SET NULL"), nullable=True
    )
    structure_json: Mapped[Any] = mapped_column(JSON, default=list)
    checklist_json: Mapped[Any] = mapped_column(JSON, default=list)
    default_billing_type: Mapped[str] = mapped_column(String(30), default="time_and_material")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectMilestone(TenantBaseModel):
    __tablename__ = "project_milestones"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    acceptance_criteria: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    accepted_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    invoice_link_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_invoice_links.id", ondelete="SET NULL"), nullable=True
    )


class ProjectDependency(TenantBaseModel):
    __tablename__ = "project_dependencies"
    __table_args__ = (
        UniqueConstraint("tenant_id", "predecessor_id", "successor_id", "type", name="uq_pm_dependencies"),
    )

    predecessor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    successor_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type: Mapped[str] = mapped_column(String(4), default="FS", index=True)
    lag_days: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectBaseline(TenantBaseModel):
    __tablename__ = "project_baselines"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectBaselineSnapshot(TenantBaseModel):
    __tablename__ = "project_baseline_snapshots"

    baseline_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_baselines.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    snapshot_json: Mapped[Any] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectRelease(TenantBaseModel):
    __tablename__ = "project_releases"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    release_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="planned", index=True)
    work_items_json: Mapped[Any] = mapped_column(JSON, default=list)


class ProjectChangeRequest(TenantBaseModel):
    __tablename__ = "project_change_requests"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scope_impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cost_impact: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    schedule_impact: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProjectTimeEntry(TenantBaseModel):
    __tablename__ = "project_time_entries"
    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_id", name="uq_pm_time_entries_source_external"),
        Index("ix_pm_time_entries_employee_date", "employee_id", "entry_date"),
    )

    work_item_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True, index=True
    )
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    billable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    billable_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    cost_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    source: Mapped[str] = mapped_column(String(30), default="manual", index=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    invoice_link_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_invoice_links.id", ondelete="SET NULL"), nullable=True
    )
    legacy_migrated: Mapped[bool] = mapped_column(Boolean, default=False)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ProjectTimesheet(TenantBaseModel):
    __tablename__ = "project_timesheets"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "week_start", name="uq_pm_timesheets_week"),)

    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    total_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    billable_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)


class ProjectTimesheetEntry(TenantBaseModel):
    __tablename__ = "project_timesheet_entries"
    __table_args__ = (UniqueConstraint("timesheet_id", "time_entry_id", name="uq_pm_timesheet_entries"),)

    timesheet_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_timesheets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    time_entry_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_time_entries.id", ondelete="CASCADE"), nullable=False, index=True
    )


class ProjectExpense(TenantBaseModel):
    __tablename__ = "project_expenses"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(60), default="other")
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    receipt_document_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    reimbursable: Mapped[bool] = mapped_column(Boolean, default=True)
    billable: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    invoice_link_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_invoice_links.id", ondelete="SET NULL"), nullable=True
    )


class ProjectCostEntry(TenantBaseModel):
    __tablename__ = "project_cost_entries"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cost_type: Mapped[str] = mapped_column(String(30), default="labour", index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    source: Mapped[str] = mapped_column(String(50), default="manual")
    reference_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProjectBillingRun(TenantBaseModel):
    __tablename__ = "project_billing_runs"
    __table_args__ = (UniqueConstraint("tenant_id", "idempotency_key", name="uq_pm_billing_runs_idempotency"),)

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    billing_type: Mapped[str] = mapped_column(String(30), default="time_and_material")
    gross_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    finance_invoice_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_invoices.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    posted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)


class ProjectBillingLine(TenantBaseModel):
    __tablename__ = "project_billing_lines"
    __table_args__ = (
        UniqueConstraint("tenant_id", "billing_run_id", "source_type", "source_id", name="uq_pm_billing_lines_source"),
    )

    billing_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_billing_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    source_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tax_code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)


class ProjectInvoiceLink(TenantBaseModel):
    __tablename__ = "project_invoice_links"
    __table_args__ = (UniqueConstraint("tenant_id", "finance_invoice_id", "project_id", name="uq_pm_invoice_links"),)

    finance_invoice_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("finance_invoices.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    billing_run_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_billing_runs.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectBudget(TenantBaseModel):
    __tablename__ = "project_budgets"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)
    budget_hours: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    budget_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    budget_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    effective_from: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectBudgetRevision(TenantBaseModel):
    __tablename__ = "project_budget_revisions"

    budget_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_budgets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    change_json: Mapped[Any] = mapped_column(JSON, default=dict)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)


class ProjectResourceRole(TenantBaseModel):
    __tablename__ = "project_resource_roles"
    __table_args__ = (UniqueConstraint("tenant_id", "code", name="uq_pm_resource_roles_tenant_code"),)

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    default_cost_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    default_billable_rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    currency: Mapped[str] = mapped_column(String(10), default="INR")
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectEmployeeSkill(TenantBaseModel):
    __tablename__ = "project_employee_skills"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "skill_code", name="uq_pm_employee_skills"),)

    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    skill_code: Mapped[str] = mapped_column(String(80), nullable=False)
    proficiency: Mapped[int] = mapped_column(Integer, default=1)
    evidence_document_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    verified_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectCapacityCalendar(TenantBaseModel):
    __tablename__ = "project_capacity_calendars"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "week_start", name="uq_pm_capacity_employee_week"),)

    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    capacity_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=40)
    planned_leave_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    holiday_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    source: Mapped[str] = mapped_column(String(20), default="hr", index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectResourceBooking(TenantBaseModel):
    __tablename__ = "project_resource_bookings"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role_code: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    hours_per_day: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=8)
    allocation_percent: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=100)
    status: Mapped[str] = mapped_column(String(30), default="requested", index=True)
    requested_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    capacity_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    split_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class ProjectWorkloadSnapshot(TenantBaseModel):
    __tablename__ = "project_workload_snapshots"
    __table_args__ = (UniqueConstraint("tenant_id", "employee_id", "week_start", name="uq_pm_workload_employee_week"),)

    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    week_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    booked_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    available_hours: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=0)
    utilization_percent: Mapped[Decimal] = mapped_column(Numeric(7, 2), default=0)
    overallocated: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectRisk(TenantBaseModel):
    __tablename__ = "project_risks"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    probability: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=1)
    impact: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=1)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=1, index=True)
    owner_employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    response_strategy: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    mitigation_plan: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="identified", index=True)
    due_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class ProjectIssue(TenantBaseModel):
    __tablename__ = "project_issues"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_item_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(30), default="open", index=True)
    owner_employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    linked_risk_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_risks.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectDecision(TenantBaseModel):
    __tablename__ = "project_decisions"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    decided_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)


class ProjectStatusUpdate(TenantBaseModel):
    __tablename__ = "project_status_updates"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    period: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    health: Mapped[str] = mapped_column(String(20), default="unknown", index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    achievements: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    blockers: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectGoal(TenantBaseModel):
    __tablename__ = "project_goals"

    portfolio_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_portfolios.id", ondelete="CASCADE"), nullable=True, index=True
    )
    program_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_programs.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    metric: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    target: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    current: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    owner_employee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectRetrospective(TenantBaseModel):
    __tablename__ = "project_retrospectives"

    project_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sprint_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_sprints.id", ondelete="SET NULL"), nullable=True, index=True
    )
    what_went_well: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    what_did_not: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actions_json: Mapped[Any] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(30), default="draft", index=True)
    facilitator_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProjectComment(TenantBaseModel):
    __tablename__ = "project_comments"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    author_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions_json: Mapped[Any] = mapped_column(JSON, default=list)
    parent_comment_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_comments.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectActivity(TenantBaseModel):
    __tablename__ = "project_activities"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    actor_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    changes_json: Mapped[Any] = mapped_column(JSON, default=dict)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    template_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    recipient: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(150), nullable=True, index=True)
    consent_reference: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)


class ProjectAttachment(TenantBaseModel):
    __tablename__ = "project_attachments"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    document_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)


class ProjectAutomationRule(TenantBaseModel):
    __tablename__ = "project_automation_rules"

    project_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    trigger_json: Mapped[Any] = mapped_column(JSON, default=dict)
    conditions_json: Mapped[Any] = mapped_column(JSON, default=list)
    actions_json: Mapped[Any] = mapped_column(JSON, default=list)
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)


class ProjectAutomationRun(TenantBaseModel):
    __tablename__ = "project_automation_runs"

    rule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_automation_rules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_entity: Mapped[str] = mapped_column(String(50), nullable=False)
    trigger_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectIntegration(TenantBaseModel):
    __tablename__ = "project_integrations"
    __table_args__ = (UniqueConstraint("tenant_id", "provider", "external_id", name="uq_pm_integrations"),)

    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(200), nullable=False)
    config_json: Mapped[Any] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectImportBatch(TenantBaseModel):
    __tablename__ = "project_import_batches"

    provider: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    file_document_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="staged", index=True)
    rows_total: Mapped[int] = mapped_column(Integer, default=0)
    rows_imported: Mapped[int] = mapped_column(Integer, default=0)
    rows_failed: Mapped[int] = mapped_column(Integer, default=0)
    error_report_document_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    payload_json: Mapped[Any] = mapped_column(JSON, default=dict)
    mapping_json: Mapped[Any] = mapped_column(JSON, default=dict)
    validation_json: Mapped[Any] = mapped_column(JSON, default=dict)
    dry_run_json: Mapped[Any] = mapped_column(JSON, default=dict)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    committed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rolled_back_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ProjectImportRow(TenantBaseModel):
    __tablename__ = "project_import_rows"
    __table_args__ = (
        UniqueConstraint("tenant_id", "batch_id", "row_key", name="uq_pm_import_rows_key"),
        Index("ix_pm_import_rows_status", "batch_id", "status"),
    )

    batch_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("project_import_batches.id", ondelete="CASCADE"), nullable=False, index=True
    )
    row_key: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), default="work_item", index=True)
    raw_json: Mapped[Any] = mapped_column(JSON, default=dict)
    normalized_json: Mapped[Any] = mapped_column(JSON, default=dict)
    validation_json: Mapped[Any] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="staged", index=True)
    target_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    error_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class ProjectAiSignal(TenantBaseModel):
    __tablename__ = "project_ai_signals"

    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0, index=True)
    features_json: Mapped[Any] = mapped_column(JSON, default=dict)
    explanation: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    model_version: Mapped[str] = mapped_column(String(50), default="rules-v1")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    review_status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    reviewed_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ProjectAiAction(TenantBaseModel):
    __tablename__ = "project_ai_actions"

    action_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    proposed_json: Mapped[Any] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="proposed", index=True)
    requested_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    on_behalf_of_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reversal_reference: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class ProjectOutboxEvent(TenantBaseModel):
    __tablename__ = "project_outbox_events"
    __table_args__ = (
        UniqueConstraint(
            "event_name", "idempotency_key", name="uq_project_outbox_events_idempotency"
        ),
    )

    event_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    payload: Mapped[Any] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, index=True)
