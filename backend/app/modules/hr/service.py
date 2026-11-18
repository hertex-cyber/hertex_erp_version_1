from datetime import date
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import publish
from app.modules.hr.models import Employee
from app.modules.identity.models import User


def _employee_event_payload(employee: Employee, user: User, date_of_exit: date | None) -> dict[str, Any]:
    user_id = employee.created_by_id or user.id if user is not None else employee.created_by_id
    return {
        "tenant_id": str(employee.tenant_id) if employee.tenant_id else None,
        "employee_id": str(employee.id),
        "user_id": str(user_id) if user_id else None,
        "date_of_exit": date_of_exit.isoformat() if date_of_exit else None,
        "status": employee.status,
    }


async def publish_employee_onboarded(employee: Employee, user: User) -> None:
    await publish(
        "employee.onboarded",
        _employee_event_payload(employee, user, None),
        correlation_id=str(user.id) if user is not None else None,
    )


async def publish_employee_exited(
    employee: Employee, user: User, date_of_exit: date | None = None
) -> None:
    exit_date = date_of_exit or employee.date_of_exit
    await publish(
        "employee.exited",
        _employee_event_payload(employee, user, exit_date),
        correlation_id=str(user.id) if user is not None else None,
    )


async def record_employee_exit(
    db: AsyncSession, employee: Employee, user: User, date_of_exit: date
) -> Employee:
    employee.date_of_exit = date_of_exit
    employee.status = "exited"
    employee.is_active = False
    await db.flush()
    return employee
