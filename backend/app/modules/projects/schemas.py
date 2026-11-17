from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class ProjectBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=1, max_length=50)
    description: Optional[str] = None
    status: str = "planning"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Decimal = Decimal("0")
    client_name: Optional[str] = None
    manager_id: Optional[UUID] = None


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(ORMModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Optional[Decimal] = None
    client_name: Optional[str] = None
    manager_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class TaskRead(ORMModel):
    id: UUID
    project_id: UUID
    title: str
    description: Optional[str] = None
    status: str
    priority: str
    assignee_id: Optional[UUID] = None
    estimated_hours: Decimal
    actual_hours: Decimal
    billable_rate: Decimal
    budget_amount: Decimal
    due_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    is_billable: bool
    created_at: datetime


class ProjectRead(ORMModel):
    id: UUID
    name: str
    code: str
    description: Optional[str] = None
    status: str
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    budget: Decimal
    client_name: Optional[str] = None
    manager_id: Optional[UUID] = None
    is_active: bool
    created_at: datetime
    tasks: list[TaskRead] = []


class TaskCreate(ORMModel):
    project_id: UUID
    title: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    status: str = "todo"
    priority: str = "medium"
    assignee_id: Optional[UUID] = None
    estimated_hours: Decimal = Decimal("0")
    actual_hours: Decimal = Decimal("0")
    billable_rate: Decimal = Decimal("0")
    budget_amount: Decimal = Decimal("0")
    due_date: Optional[date] = None
    is_billable: bool = True


class TaskUpdate(ORMModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee_id: Optional[UUID] = None
    estimated_hours: Optional[Decimal] = None
    actual_hours: Optional[Decimal] = None
    billable_rate: Optional[Decimal] = None
    budget_amount: Optional[Decimal] = None
    due_date: Optional[date] = None
    completed_at: Optional[datetime] = None
    is_billable: Optional[bool] = None
    is_active: Optional[bool] = None


class ProjectSummary(ORMModel):
    project_id: UUID
    total_tasks: int
    done_tasks: int
    open_tasks: int
    total_budget: Decimal
    estimated_hours: Decimal
    actual_hours: Decimal
    billable_value: Decimal
