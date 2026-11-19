from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Numeric, String, Text, Time, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBaseModel

"""hr module models"""
class Department(TenantBaseModel):
    __tablename__ = "hr_departments"

    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class Employee(TenantBaseModel):
    __tablename__ = "hr_employees"

    employee_code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    designation: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    department_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    date_of_joining: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    date_of_exit: Mapped[Optional[date]] = mapped_column(Date, nullable=True, index=True)
    employment_type: Mapped[str] = mapped_column(String(40), default="full_time")
    salary: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    bank_account: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)

    department: Mapped[Optional[Department]] = relationship(lazy="selectin")


class Attendance(TenantBaseModel):
    __tablename__ = "hr_attendance"

    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    check_in: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    check_out: Mapped[Optional[time]] = mapped_column(Time, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="present", index=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class LeaveRequest(TenantBaseModel):
    __tablename__ = "hr_leave_requests"

    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    leave_type: Mapped[str] = mapped_column(String(40), default="casual")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[Decimal] = mapped_column(Numeric(6, 1), default=1)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class PayrollRun(TenantBaseModel):
    __tablename__ = "hr_payroll_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "period", name="uq_hr_payroll_runs_tenant_period"),
    )

    period: Mapped[str] = mapped_column(String(7), nullable=False, index=True)  # YYYY-MM
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    total_gross: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_deductions: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_net: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    journal_entry_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("finance_journal_entries.id", ondelete="RESTRICT"),
        nullable=True,
        unique=True,
    )


class Payslip(TenantBaseModel):
    __tablename__ = "hr_payslips"

    payroll_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_payroll_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    employee_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("hr_employees.id", ondelete="CASCADE"), nullable=False, index=True
    )
    gross: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    pf: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    esi: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    tds: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    other_deductions: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    net: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
