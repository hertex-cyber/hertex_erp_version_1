from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.modules.finance.models import (
    Account,
    FinancialPeriod,
    JournalEntry,
    JournalLine,
)
from app.modules.hr.models import Employee, PayrollRun, Payslip


@pytest.mark.asyncio
async def test_payroll_process_posts_balanced_month_end_journal_once(client, auth):
    marker = uuid4().hex[:8].upper()
    period_name = f"Payroll test {marker}"
    employee_code = f"PAY-{marker}"
    payroll_period = "2097-02"
    employee_id = None
    run_id = None
    journal_id = None
    financial_period_id = None
    expected = {
        "gross": Decimal("0"),
        "pf": Decimal("0"),
        "esi": Decimal("0"),
        "tds": Decimal("0"),
        "net": Decimal("0"),
    }

    try:
        financial_period = await client.post(
            "/api/v1/finance/periods",
            headers=auth,
            json={
                "name": period_name,
                "start_date": "2097-01-01",
                "end_date": "2097-12-31",
            },
        )
        assert financial_period.status_code == 201, financial_period.text
        financial_period_id = financial_period.json()["id"]

        employee = await client.post(
            "/api/v1/hr/employees",
            headers=auth,
            json={
                "employee_code": employee_code,
                "first_name": "Payroll",
                "last_name": "Test",
                "salary": "60000.00",
                "status": "active",
            },
        )
        assert employee.status_code == 201, employee.text
        employee_id = employee.json()["id"]

        run = await client.post(
            "/api/v1/hr/payroll-runs",
            headers=auth,
            json={"period": payroll_period},
        )
        assert run.status_code == 201, run.text
        run_id = run.json()["id"]
        async with AsyncSessionLocal() as db:
            created_employee = await db.get(Employee, UUID(employee_id))
            employees = list(
                (
                    await db.scalars(
                        select(Employee).where(
                            Employee.tenant_id == created_employee.tenant_id,
                            Employee.is_active.is_(True),
                            Employee.status == "active",
                        )
                    )
                ).all()
            )
            for item in employees:
                gross = Decimal(item.salary or 0)
                pf = (gross * Decimal("0.12")).quantize(Decimal("0.01"))
                esi = (
                    (gross * Decimal("0.0075")).quantize(Decimal("0.01"))
                    if gross <= 21000
                    else Decimal("0")
                )
                tds = (
                    (gross * Decimal("0.05")).quantize(Decimal("0.01"))
                    if gross > 50000
                    else Decimal("0")
                )
                expected["gross"] += gross
                expected["pf"] += pf
                expected["esi"] += esi
                expected["tds"] += tds
                expected["net"] += gross - pf - esi - tds

        duplicate = await client.post(
            "/api/v1/hr/payroll-runs",
            headers=auth,
            json={"period": payroll_period},
        )
        assert duplicate.status_code == 409, duplicate.text

        processed = await client.post(
            f"/api/v1/hr/payroll-runs/{run_id}/process",
            headers=auth,
        )
        assert processed.status_code == 200, processed.text
        run_data = processed.json()
        journal_id = run_data["journal_entry_id"]
        assert run_data["status"] == "processed"
        assert Decimal(run_data["total_gross"]) == expected["gross"]
        assert Decimal(run_data["total_deductions"]) == (
            expected["pf"] + expected["esi"] + expected["tds"]
        )
        assert Decimal(run_data["total_net"]) == expected["net"]

        retry = await client.post(
            f"/api/v1/hr/payroll-runs/{run_id}/process",
            headers=auth,
        )
        assert retry.status_code == 200, retry.text
        assert retry.json()["journal_entry_id"] == journal_id

        attempted_status_change = await client.patch(
            f"/api/v1/hr/payroll-runs/{run_id}",
            headers=auth,
            json={"status": "draft"},
        )
        assert attempted_status_change.status_code == 200, attempted_status_change.text
        assert attempted_status_change.json()["status"] == "processed"

        async with AsyncSessionLocal() as db:
            entry = await db.scalar(
                select(JournalEntry).where(JournalEntry.id == UUID(journal_id))
            )
            assert entry is not None
            assert entry.status == "posted"
            assert entry.entry_date == date(2097, 2, 28)
            rows = (
                await db.execute(
                    select(JournalLine, Account.code)
                    .join(Account, Account.id == JournalLine.account_id)
                    .where(JournalLine.journal_entry_id == entry.id)
                )
            ).all()
            journal_accounts = {
                code: (line.debit, line.credit) for line, code in rows
            }
            assert journal_accounts["5200"] == (expected["gross"], Decimal("0.00"))
            assert journal_accounts["2240"] == (Decimal("0.00"), expected["net"])
            for code, key in (("2210", "pf"), ("2220", "esi"), ("2230", "tds")):
                if expected[key]:
                    assert journal_accounts[code] == (Decimal("0.00"), expected[key])

    finally:
        async with AsyncSessionLocal() as db:
            if run_id:
                await db.execute(delete(Payslip).where(Payslip.payroll_run_id == UUID(run_id)))
                await db.execute(delete(PayrollRun).where(PayrollRun.id == UUID(run_id)))
            if journal_id:
                await db.execute(
                    delete(JournalLine).where(
                        JournalLine.journal_entry_id == UUID(journal_id)
                    )
                )
                await db.execute(
                    delete(JournalEntry).where(JournalEntry.id == UUID(journal_id))
                )
            if employee_id:
                await db.execute(delete(Employee).where(Employee.id == UUID(employee_id)))
            if financial_period_id:
                await db.execute(
                    delete(FinancialPeriod).where(
                        FinancialPeriod.id == UUID(financial_period_id)
                    )
                )
            await db.commit()
