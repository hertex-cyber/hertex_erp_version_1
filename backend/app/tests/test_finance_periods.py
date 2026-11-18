from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.modules.finance.models import FinancialPeriod

PERIOD_START = date(2098, 4, 1)
PERIOD_END = date(2099, 3, 31)


@pytest_asyncio.fixture
async def remove_test_periods():
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(FinancialPeriod).where(
                FinancialPeriod.name.like("FY period %")
                | FinancialPeriod.name.like("FY outside-window %")
            )
        )
        await db.commit()


@pytest.mark.asyncio
async def test_periods_lock_posting_and_can_be_reopened(
    client, auth, approver_auth, remove_test_periods
):
    marker = uuid4().hex[:8]
    created = await client.post(
        "/api/v1/finance/periods",
        headers=auth,
        json={
            "name": f"FY period {marker}",
            "start_date": PERIOD_START.isoformat(),
            "end_date": PERIOD_END.isoformat(),
        },
    )
    assert created.status_code == 201, created.text
    period_id = created.json()["id"]

    overlap = await client.post(
        "/api/v1/finance/periods",
        headers=auth,
        json={
            "name": f"Overlapping period {marker}",
            "start_date": date(2099, 1, 1).isoformat(),
            "end_date": date(2099, 12, 31).isoformat(),
        },
    )
    assert overlap.status_code == 409, overlap.text

    accounts_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in accounts_response.json()["items"]}
    journal_payload = {
        "entry_date": date(2098, 5, 1).isoformat(),
        "memo": f"Period lock test {marker}",
        "lines": [
            {"account_id": accounts["1010"], "debit": "25.00", "credit": "0"},
            {"account_id": accounts["4000"], "debit": "0", "credit": "25.00"},
        ],
    }
    draft = await client.post(
        "/api/v1/finance/journal-entries", headers=auth, json=journal_payload
    )
    assert draft.status_code == 201, draft.text

    invoice = await client.post(
        "/api/v1/finance/invoices",
        headers=auth,
        json={
            "issue_date": date(2098, 6, 1).isoformat(),
            "status": "draft",
            "subtotal": "100.00",
            "tax": "0.00",
            "total": "100.00",
            "currency": "INR",
        },
    )
    assert invoice.status_code == 201, invoice.text
    posted_invoice = await client.post(
        f"/api/v1/finance/invoices/{invoice.json()['id']}/post", headers=auth
    )
    assert posted_invoice.status_code == 200, posted_invoice.text

    blocked_close = await client.post(
        f"/api/v1/finance/periods/{period_id}/close", headers=auth
    )
    assert blocked_close.status_code == 409, blocked_close.text

    posted = await client.post(
        f"/api/v1/finance/journal-entries/{draft.json()['id']}/post", headers=auth
    )
    assert posted.status_code == 200, posted.text
    approvals = await client.get("/api/v1/finance/approvals", headers=auth)
    approval = next(
        row for row in approvals.json()["items"] if row["entity_id"] == draft.json()["id"]
    )
    approved = await client.post(
        f"/api/v1/finance/approvals/{approval['id']}/approve",
        headers=approver_auth,
        json={"reason": "Period journal reviewed"},
    )
    assert approved.status_code == 200, approved.text

    checklist = await client.get(
        f"/api/v1/finance/periods/{period_id}/close-checklist", headers=auth
    )
    assert checklist.status_code == 200, checklist.text
    assert checklist.json()["ready"] is True
    signoff = await client.post(
        f"/api/v1/finance/periods/{period_id}/sign-off",
        headers=auth,
        json={"reason": "Reviewed journals, balances and reconciliation exceptions"},
    )
    assert signoff.status_code == 200, signoff.text
    assert signoff.json()["close_signed_at"]

    closed = await client.post(
        f"/api/v1/finance/periods/{period_id}/close", headers=auth
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["closed_at"]

    blocked_journal = await client.post(
        "/api/v1/finance/journal-entries", headers=auth, json=journal_payload
    )
    assert blocked_journal.status_code == 422, blocked_journal.text

    blocked_payment = await client.post(
        f"/api/v1/finance/invoices/{invoice.json()['id']}/payments",
        headers={**auth, "Idempotency-Key": f"period-payment-{period_id}"},
        json={
            "invoice_id": invoice.json()["id"],
            "amount": "25.00",
            "method": "bank",
            "paid_on": date(2098, 6, 2).isoformat(),
        },
    )
    assert blocked_payment.status_code == 422, blocked_payment.text

    draft_invoice = await client.post(
        "/api/v1/finance/invoices",
        headers=auth,
        json={
            "issue_date": date(2098, 6, 1).isoformat(),
            "status": "draft",
            "subtotal": "100.00",
            "tax": "0.00",
            "total": "100.00",
            "currency": "INR",
        },
    )
    assert draft_invoice.status_code == 201, draft_invoice.text
    blocked_invoice = await client.post(
        f"/api/v1/finance/invoices/{draft_invoice.json()['id']}/post", headers=auth
    )
    assert blocked_invoice.status_code == 422, blocked_invoice.text

    reopened = await client.post(
        f"/api/v1/finance/periods/{period_id}/reopen", headers=auth
    )
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["status"] == "open"
    assert reopened.json()["closed_at"] is None
    assert reopened.json()["close_signed_at"] is None

    reopened_journal = await client.post(
        "/api/v1/finance/journal-entries", headers=auth, json=journal_payload
    )
    assert reopened_journal.status_code == 201, reopened_journal.text


@pytest.mark.asyncio
async def test_period_requires_a_matching_window_after_periods_are_configured(
    client, auth, remove_test_periods
):
    period = await client.post(
        "/api/v1/finance/periods",
        headers=auth,
        json={
            "name": f"FY outside-window {uuid4().hex[:8]}",
            "start_date": date(2095, 4, 1).isoformat(),
            "end_date": date(2096, 3, 31).isoformat(),
        },
    )
    assert period.status_code == 201, period.text

    accounts_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in accounts_response.json()["items"]}
    response = await client.post(
        "/api/v1/finance/journal-entries",
        headers=auth,
        json={
            "entry_date": date(2096, 4, 1).isoformat(),
            "lines": [
                {"account_id": accounts["1010"], "debit": "10.00", "credit": "0"},
                {"account_id": accounts["4000"], "debit": "0", "credit": "10.00"},
            ],
        },
    )
    assert response.status_code == 422, response.text
