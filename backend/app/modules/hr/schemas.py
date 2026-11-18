from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import Field, field_validator

from app.core.schemas import ORMModel


class DepartmentBase(ORMModel):
    name: str = Field(min_length=1, max_length=150)
    description: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    pass


class DepartmentUpdate(ORMModel):
    name: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class DepartmentRead(ORMModel):
    id: UUID
    name: str
    description: Optional[str] = None
    is_active: bool
    created_at: datetime


class EmployeeBase(ORMModel):
    employee_code: str = Field(min_length=1, max_length=50)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    department_id: Optional[UUID] = None
    date_of_joining: Optional[date] = None
    date_of_birth: Optional[date] = None
    date_of_exit: Optional[date] = None
    employment_type: str = "full_time"
    salary: Decimal = Decimal("0")
    bank_account: Optional[str] = None
    address: Optional[str] = None
    status: str = "active"


class EmployeeCreate(EmployeeBase):
    pass


class EmployeeUpdate(ORMModel):
    employee_code: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    department_id: Optional[UUID] = None
    date_of_joining: Optional[date] = None
    date_of_birth: Optional[date] = None
    date_of_exit: Optional[date] = None
    employment_type: Optional[str] = None
    salary: Optional[Decimal] = None
    bank_account: Optional[str] = None
    address: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class EmployeeExitRequest(ORMModel):
    date_of_exit: date


class EmployeeRead(ORMModel):
    id: UUID
    employee_code: str
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    designation: Optional[str] = None
    department_id: Optional[UUID] = None
    date_of_joining: Optional[date] = None
    date_of_exit: Optional[date] = None
    employment_type: str
    salary: Decimal
    status: str
    is_active: bool
    created_at: datetime
    department: Optional[DepartmentRead] = None


class AttendanceBase(ORMModel):
    employee_id: UUID
    work_date: date
    check_in: Optional[time] = None
    check_out: Optional[time] = None
    status: str = "present"
    notes: Optional[str] = None


class AttendanceCreate(AttendanceBase):
    pass


class AttendanceUpdate(ORMModel):
    check_in: Optional[time] = None
    check_out: Optional[time] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class AttendanceRead(ORMModel):
    id: UUID
    employee_id: UUID
    work_date: date
    check_in: Optional[time] = None
    check_out: Optional[time] = None
    status: str
    notes: Optional[str] = None
    created_at: datetime


class LeaveBase(ORMModel):
    employee_id: UUID
    leave_type: str = "casual"
    start_date: date
    end_date: date
    days: Decimal = Decimal("1")
    reason: Optional[str] = None
    status: str = "pending"


class LeaveCreate(LeaveBase):
    pass


class LeaveUpdate(ORMModel):
    leave_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    days: Optional[Decimal] = None
    reason: Optional[str] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class LeaveRead(ORMModel):
    id: UUID
    employee_id: UUID
    leave_type: str
    start_date: date
    end_date: date
    days: Decimal
    reason: Optional[str] = None
    status: str
    approved_at: Optional[datetime] = None
    created_at: datetime


class PayrollRunBase(ORMModel):
    period: str = Field(pattern=r"^\d{4}-\d{2}$")

    @field_validator("period")
    @classmethod
    def validate_period(cls, value: str) -> str:
        year, month = (int(part) for part in value.split("-"))
        if year < 1 or not 1 <= month <= 12:
            raise ValueError("Payroll period must be a valid YYYY-MM month")
        return value


class PayrollRunCreate(PayrollRunBase):
    pass


class PayrollRunUpdate(ORMModel):
    pass


class PayrollRunRead(ORMModel):
    id: UUID
    period: str
    status: str
    total_gross: Decimal
    total_deductions: Decimal
    total_net: Decimal
    processed_at: Optional[datetime] = None
    journal_entry_id: Optional[UUID] = None
    created_at: datetime


class PayslipRead(ORMModel):
    id: UUID
    payroll_run_id: UUID
    employee_id: UUID
    gross: Decimal
    pf: Decimal
    esi: Decimal
    tds: Decimal
    other_deductions: Decimal
    net: Decimal
    notes: Optional[str] = None
    created_at: datetime


class PayslipUpdate(ORMModel):
    other_deductions: Optional[Decimal] = None
    notes: Optional[str] = None
