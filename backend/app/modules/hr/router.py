import math
from calendar import monthrange
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.events import publish
from app.core.exceptions import ConflictError, NotFoundError
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.finance.service import post_payroll_journal
from app.modules.hr.models import (
    Attendance,
    Department,
    Employee,
    LeaveRequest,
    PayrollRun,
    Payslip,
)
from app.modules.hr.schemas import (
    AttendanceCreate,
    AttendanceRead,
    AttendanceUpdate,
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    EmployeeCreate,
    EmployeeExitRequest,
    EmployeeRead,
    EmployeeUpdate,
    LeaveCreate,
    LeaveRead,
    LeaveUpdate,
    PayrollRunCreate,
    PayrollRunRead,
    PayrollRunUpdate,
    PayslipRead,
)
from app.modules.hr.service import (
    publish_employee_exited,
    publish_employee_onboarded,
    record_employee_exit,
)
from app.modules.identity.models import User

router = APIRouter(prefix="/hr")


def _include(**kwargs):
    child, _ = build_crud_router(module="hr", **kwargs)
    router.include_router(child)


async def employee_created(db, user, employee, data, request):
    await publish_employee_onboarded(employee, user)


async def employee_updated(db, user, employee, data, request):
    if data.get("date_of_exit") is not None:
        await publish_employee_exited(employee, user, employee.date_of_exit)
    elif data.get("status") in ("active", "onboarded"):
        await publish_employee_onboarded(employee, user)


_include(
    model=Department,
    read_schema=DepartmentRead,
    create_schema=DepartmentCreate,
    update_schema=DepartmentUpdate,
    prefix="/departments",
    tags=["HR · Departments"],
    permission_prefix="hr.department",
    entity="Department",
    search_fields=("name",),
)

_include(
    model=Employee,
    read_schema=EmployeeRead,
    create_schema=EmployeeCreate,
    update_schema=EmployeeUpdate,
    prefix="/employees",
    tags=["HR · Employees"],
    permission_prefix="hr.employee",
    entity="Employee",
    search_fields=("employee_code", "first_name", "last_name", "email"),
    filter_fields=("department_id", "status", "employment_type"),
    load_options=(selectinload(Employee.department),),
    after_create=employee_created,
    after_update=employee_updated,
)

_include(
    model=Attendance,
    read_schema=AttendanceRead,
    create_schema=AttendanceCreate,
    update_schema=AttendanceUpdate,
    prefix="/attendance",
    tags=["HR · Attendance"],
    permission_prefix="hr.attendance",
    entity="Attendance",
    search_fields=("notes",),
    filter_fields=("employee_id", "status"),
    soft_delete=False,
)

_include(
    model=LeaveRequest,
    read_schema=LeaveRead,
    create_schema=LeaveCreate,
    update_schema=LeaveUpdate,
    prefix="/leave-requests",
    tags=["HR · Leave"],
    permission_prefix="hr.leaverequest",
    entity="LeaveRequest",
    search_fields=("reason", "leave_type"),
    filter_fields=("employee_id", "status", "leave_type"),
)

_include(
    model=PayrollRun,
    read_schema=PayrollRunRead,
    create_schema=PayrollRunCreate,
    update_schema=PayrollRunUpdate,
    prefix="/payroll-runs",
    tags=["HR · Payroll"],
    permission_prefix="hr.payrollrun",
    entity="PayrollRun",
    search_fields=("period",),
    filter_fields=("status",),
)

approve_leave_dep = require_permissions("hr.leaverequest.update")
process_payroll_dep = require_permissions("hr.payrollrun.update")
exit_employee_dep = require_permissions("hr.employee.update")


@router.post("/employees/{employee_id}/exit", response_model=EmployeeRead, tags=["HR · Employees"])
async def exit_employee(
    employee_id: UUID,
    payload: EmployeeExitRequest,
    request: Request,
    user: User = Depends(exit_employee_dep),
    db: AsyncSession = Depends(get_db),
):
    employee = await db.scalar(select(Employee).where(Employee.id == employee_id))
    if employee is None or (not user.is_superuser and employee.tenant_id != user.tenant_id):
        raise NotFoundError("Employee not found")
    await record_employee_exit(db, employee, user, payload.date_of_exit)
    await record_audit(
        db,
        user=user,
        action="exit",
        module="hr",
        entity="Employee",
        entity_id=employee.id,
        changes={"date_of_exit": payload.date_of_exit.isoformat(), "status": "exited"},
        request=request,
    )
    await db.commit()
    await db.refresh(employee)
    await publish_employee_exited(employee, user, payload.date_of_exit)
    return employee


@router.post("/leave-requests/{leave_id}/approve", response_model=LeaveRead, tags=["HR · Leave"])
async def approve_leave(
    leave_id: UUID,
    request: Request,
    user: User = Depends(approve_leave_dep),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(LeaveRequest).where(LeaveRequest.id == leave_id)
    leave = await db.scalar(stmt)
    if leave is None:
        raise NotFoundError("Leave request not found")
    if not user.is_superuser and leave.tenant_id != user.tenant_id:
        raise NotFoundError("Leave request not found")
    leave.status = "approved"
    leave.approved_by_id = user.id
    leave.approved_at = datetime.now(timezone.utc)
    await record_audit(
        db,
        user=user,
        action="approve",
        module="hr",
        entity="LeaveRequest",
        entity_id=leave.id,
        request=request,
    )
    await db.commit()
    await publish(
        "leave.approved",
        {
            "tenant_id": str(leave.tenant_id) if leave.tenant_id else None,
            "employee_id": str(leave.employee_id),
            "start_date": leave.start_date.isoformat(),
            "end_date": leave.end_date.isoformat(),
            "hours": str(leave.days * 8),
        },
    )
    await db.refresh(leave)
    return leave


@router.post("/payroll-runs/{run_id}/process", response_model=PayrollRunRead, tags=["HR · Payroll"])
async def process_payroll(
    run_id: UUID,
    request: Request,
    user: User = Depends(process_payroll_dep),
    db: AsyncSession = Depends(get_db),
):
    run = await db.scalar(
        select(PayrollRun).where(PayrollRun.id == run_id).with_for_update()
    )
    if run is None:
        raise NotFoundError("Payroll run not found")
    if not user.is_superuser and run.tenant_id != user.tenant_id:
        raise NotFoundError("Payroll run not found")
    if run.status == "processed":
        return run
    if run.status != "draft":
        raise ConflictError("Only draft payroll runs can be processed")

    if run.tenant_id is None:
        raise ConflictError("Payroll run must belong to a tenant")
    stmt = select(Employee).where(
        Employee.tenant_id == run.tenant_id,
        Employee.is_active.is_(True),
        Employee.status == "active",
    )
    employees = list((await db.scalars(stmt)).all())
    if not employees:
        raise ConflictError("Payroll cannot be processed without active employees")

    total_gross = Decimal("0")
    total_deductions = Decimal("0")
    total_net = Decimal("0")
    total_pf = Decimal("0")
    total_esi = Decimal("0")
    total_tds = Decimal("0")
    for employee in employees:
        gross = Decimal(employee.salary or 0)
        if not gross.is_finite() or gross < 0:
            raise ConflictError(f"Employee {employee.employee_code} has an invalid salary")
        pf = (gross * Decimal("0.12")).quantize(Decimal("0.01"))
        esi = (gross * Decimal("0.0075")).quantize(Decimal("0.01")) if gross <= 21000 else Decimal("0")
        tds = (gross * Decimal("0.05")).quantize(Decimal("0.01")) if gross > 50000 else Decimal("0")
        deductions = pf + esi + tds
        net = gross - deductions
        if net < 0:
            raise ConflictError(f"Payroll deductions exceed gross pay for {employee.employee_code}")
        db.add(
            Payslip(
                tenant_id=run.tenant_id,
                created_by_id=user.id,
                payroll_run_id=run.id,
                employee_id=employee.id,
                gross=gross,
                pf=pf,
                esi=esi,
                tds=tds,
                net=net,
            )
        )
        total_gross += gross
        total_deductions += deductions
        total_net += net
        total_pf += pf
        total_esi += esi
        total_tds += tds

    if total_gross <= 0:
        raise ConflictError("Payroll gross must be greater than zero")

    run.total_gross = total_gross
    run.total_deductions = total_deductions
    run.total_net = total_net
    await db.flush()
    year, month = (int(part) for part in run.period.split("-"))
    payroll_date = date(year, month, monthrange(year, month)[1])
    journal = await post_payroll_journal(
        db,
        user,
        run,
        entry_date=payroll_date,
        gross=total_gross,
        pf=total_pf,
        esi=total_esi,
        tds=total_tds,
        net=total_net,
    )
    run.status = "processed"
    run.processed_at = datetime.now(timezone.utc)

    await record_audit(
        db,
        user=user,
        action="process",
        module="hr",
        entity="PayrollRun",
        entity_id=run.id,
        changes={
            "period": run.period,
            "employees": len(employees),
            "journal_entry_id": journal.id,
            "total_gross": total_gross,
            "total_deductions": total_deductions,
            "total_net": total_net,
        },
        request=request,
    )
    await db.commit()
    await db.refresh(run)
    return run


@router.get("/payslips", response_model=Page[PayslipRead], tags=["HR · Payroll"])
async def list_payslips(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    payroll_run_id: Optional[str] = None,
    employee_id: Optional[str] = None,
    user: User = Depends(require_permissions("hr.payslip.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Payslip)
    count_stmt = select(func.count()).select_from(Payslip)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Payslip.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(Payslip.tenant_id == user.tenant_id)
    if payroll_run_id:
        stmt = stmt.where(Payslip.payroll_run_id == payroll_run_id)
        count_stmt = count_stmt.where(Payslip.payroll_run_id == payroll_run_id)
    if employee_id:
        stmt = stmt.where(Payslip.employee_id == employee_id)
        count_stmt = count_stmt.where(Payslip.employee_id == employee_id)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (await db.scalars(stmt.order_by(Payslip.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    )
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, math.ceil(total / size)),
    }
