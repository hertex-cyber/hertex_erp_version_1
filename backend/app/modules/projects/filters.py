import shlex
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import Select
from sqlalchemy.exc import StatementError

from app.core.exceptions import ForbiddenError, ValidationError
from app.modules.identity.models import User
from app.modules.projects import models as m

ALLOWED_FIELDS: dict[str, dict[str, tuple[Any, bool]]] = {
    "Project": {
        "id": (m.Project.id, False),
        "number": (m.Project.number, False),
        "name": (m.Project.name, False),
        "code": (m.Project.code, False),
        "status": (m.Project.status, False),
        "health": (m.Project.health, False),
        "priority": (m.Project.priority, False),
        "methodology": (m.Project.methodology, False),
        "billing_type": (m.Project.billing_type, False),
        "customer_id": (m.Project.customer_id, False),
        "portfolio_id": (m.Project.portfolio_id, False),
        "program_id": (m.Project.program_id, False),
        "manager_employee_id": (m.Project.manager_employee_id, False),
        "start_date": (m.Project.start_date, False),
        "end_date": (m.Project.end_date, False),
        "planned_start_date": (m.Project.planned_start_date, False),
        "planned_end_date": (m.Project.planned_end_date, False),
        "budget": (m.Project.budget, True),
        "budget_cost": (m.Project.budget_cost, True),
        "budget_revenue": (m.Project.budget_revenue, True),
        "contract_value": (m.Project.contract_value, True),
        "total_billed": (m.Project.total_billed, True),
        "margin_amount": (m.Project.margin_amount, True),
    },
    "Task": {
        "id": (m.Task.id, False),
        "number": (m.Task.number, False),
        "title": (m.Task.title, False),
        "project_id": (m.Task.project_id, False),
        "status": (m.Task.status, False),
        "work_item_type": (m.Task.work_item_type, False),
        "priority": (m.Task.priority, False),
        "assignee_id": (m.Task.assignee_id, False),
        "employee_id": (m.Task.employee_id, False),
        "sprint_id": (m.Task.sprint_id, False),
        "board_id": (m.Task.board_id, False),
        "board_column_id": (m.Task.board_column_id, False),
        "parent_work_item_id": (m.Task.parent_work_item_id, False),
        "milestone_id": (m.Task.milestone_id, False),
        "release_id": (m.Task.release_id, False),
        "rank": (m.Task.rank, False),
        "story_points": (m.Task.story_points, False),
        "estimated_hours": (m.Task.estimated_hours, False),
        "remaining_hours": (m.Task.remaining_hours, False),
        "start_date": (m.Task.start_date, False),
        "due_date": (m.Task.due_date, False),
        "completed_at": (m.Task.completed_at, False),
        "billable": (m.Task.is_billable, False),
        "billable_rate": (m.Task.billable_rate, True),
        "actual_cost": (m.Task.actual_cost, True),
        "actual_revenue": (m.Task.actual_revenue, True),
        "invoiced_amount": (m.Task.invoiced_amount, True),
    },
}

OPERATORS = {"=", "!=", ">", ">=", "<", "<=", "~", "in", "not in"}
NEGATED_OPERATORS = {"!=", "not in"}


def _coerce(column: Any, raw: str) -> Any:
    python_type = getattr(column.type, "python_type", str)
    if python_type is UUID:
        try:
            return UUID(raw)
        except ValueError as exc:
            raise ValidationError(f"Invalid UUID in filter: {raw}") from exc
    if python_type is Decimal:
        try:
            return Decimal(raw)
        except InvalidOperation as exc:
            raise ValidationError(f"Invalid number in filter: {raw}") from exc
    if python_type is date:
        try:
            return date.fromisoformat(raw)
        except ValueError as exc:
            raise ValidationError(f"Invalid date in filter: {raw}") from exc
    if python_type is bool:
        if raw.lower() in ("true", "1", "yes"):
            return True
        if raw.lower() in ("false", "0", "no"):
            return False
        raise ValidationError(f"Invalid boolean in filter: {raw}")
    if python_type is int:
        try:
            return int(raw)
        except ValueError as exc:
            raise ValidationError(f"Invalid integer in filter: {raw}") from exc
    return raw


def _condition(column: Any, operator: str, raw: str) -> Any:
    if operator in ("in", "not in"):
        values = [_coerce(column, token.strip()) for token in raw.split(",") if token.strip()]
        if not values:
            raise ValidationError("Filter IN requires at least one value")
        return column.in_(values) if operator == "in" else column.notin_(values)
    value = _coerce(column, raw)
    if operator == "=":
        return column == value
    if operator == "!=":
        return column != value
    if operator == ">":
        return column > value
    if operator == ">=":
        return column >= value
    if operator == "<":
        return column < value
    if operator == "<=":
        return column <= value
    if operator == "~":
        return column.ilike(f"%{raw}%")
    raise ValidationError(f"Unsupported filter operator: {operator}")


def apply_filter(stmt: Select, model_name: str, expression: str | None, user: User) -> Select:
    if not expression or not expression.strip():
        return stmt
    fields = ALLOWED_FIELDS.get(model_name)
    if fields is None:
        raise ValidationError(f"Filtering is not supported for {model_name}")
    try:
        tokens = shlex.split(expression, posix=True)
    except ValueError as exc:
        raise ValidationError("Malformed filter expression") from exc
    if len(tokens) < 3:
        raise ValidationError("Filter must contain at least one field/operator/value triple")
    index = 0
    while index < len(tokens):
        if tokens[index].upper() in ("AND", "&&"):
            index += 1
            continue
        if index + 2 >= len(tokens):
            raise ValidationError("Malformed filter expression")
        field, operator, raw = tokens[index : index + 3]
        operator = operator.lower()
        if field not in fields:
            raise ValidationError(f"Unknown filter field: {field}")
        column, sensitive = fields[field]
        if sensitive and not (user.is_superuser or user.has_permission("projects.finance.read")):
            raise ForbiddenError(f"Filter field requires projects.finance.read: {field}")
        if operator not in OPERATORS:
            raise ValidationError(f"Unknown filter operator: {operator}")
        try:
            stmt = stmt.where(_condition(column, operator, raw))
        except StatementError as exc:
            raise ValidationError("Invalid filter value") from exc
        index += 3
    return stmt
