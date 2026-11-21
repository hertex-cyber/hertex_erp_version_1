import re
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.db.session import AsyncSessionLocal
from app.modules.hr.models import Employee, PayrollRun
from app.modules.identity.models import User

PAYSLIP_PATTERN = re.compile(r"^PSL/\d{2}-\d{2}/\d{5}$")


@pytest.mark.asyncio
async def test_create_payslip_allocates_number(client, auth):
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        assert user is not None
        employee = Employee(
            tenant_id=user.tenant_id,
            created_by_id=user.id,
            employee_code=f"EMP-{uuid4().hex[:8]}",
            first_name="Payroll",
            last_name="Test",
            salary="50000",
        )
        run = PayrollRun(
            tenant_id=user.tenant_id,
            created_by_id=user.id,
            period="2026-01",
        )
        db.add_all([employee, run])
        await db.commit()
        await db.refresh(employee)
        await db.refresh(run)
        employee_id = employee.id
        run_id = run.id

    response = await client.post(
        "/api/v1/hr/payslips",
        headers=auth,
        json={
            "payroll_run_id": str(run_id),
            "employee_id": str(employee_id),
            "gross": "50000.00",
            "net": "46000.00",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert PAYSLIP_PATTERN.match(body["payslip_number"])
    assert body["gross"] == "50000.00"
