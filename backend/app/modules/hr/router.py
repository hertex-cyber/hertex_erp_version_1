import math
from datetime import datetime, timezone
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
from app.core.exceptions import ConflictError, NotFoundError
from app.core.schemas import Page
from app.db.session import get_db
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
from app.modules.identity.models import User

router = APIRouter(prefix="/hr")


def _include(**kwargs):
    child, _ = build_crud_router(module="hr", **kwargs)
    router.include_router(child)


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
    await db.refresh(leave)
    return leave


@router.post("/payroll-runs/{run_id}/process", response_model=PayrollRunRead, tags=["HR · Payroll"])
async def process_payroll(
    run_id: UUID,
    request: Request,
    user: User = Depends(process_payroll_dep),
    db: AsyncSession = Depends(get_db),
):
    run = await db.scalar(select(PayrollRun).where(PayrollRun.id == run_id))
    if run is None:
        raise NotFoundError("Payroll run not found")
    if not user.is_superuser and run.tenant_id != user.tenant_id:
        raise NotFoundError("Payroll run not found")
    if run.status == "processed":
        raise ConflictError("Payroll run is already processed")

    stmt = select(Employee).where(Employee.is_active.is_(True), Employee.status == "active")
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Employee.tenant_id == user.tenant_id)
    employees = list((await db.scalars(stmt)).all())

    total_gross = Decimal("0")
    total_deductions = Decimal("0")
    total_net = Decimal("0")
    for employee in employees:
        gross = Decimal(employee.salary or 0)
        pf = (gross * Decimal("0.12")).quantize(Decimal("0.01"))
        esi = (gross * Decimal("0.0075")).quantize(Decimal("0.01")) if gross <= 21000 else Decimal("0")
        tds = (gross * Decimal("0.05")).quantize(Decimal("0.01")) if gross > 50000 else Decimal("0")
        deductions = pf + esi + tds
        net = gross - deductions
        db.add(
            Payslip(
                tenant_id=user.tenant_id,
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

    run.total_gross = total_gross
    run.total_deductions = total_deductions
    run.total_net = total_net
    run.status = "processed"
    run.processed_at = datetime.now(timezone.utc)

    await record_audit(
        db,
        user=user,
        action="process",
        module="hr",
        entity="PayrollRun",
        entity_id=run.id,
        changes={"period": run.period, "employees": len(employees)},
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
