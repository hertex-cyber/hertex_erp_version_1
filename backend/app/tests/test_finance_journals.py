from datetime import date
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete

from app.db.session import AsyncSessionLocal
from app.modules.finance.models import FinancialPeriod

TEST_START = date(2090, 4, 1)
TEST_END = date(2091, 3, 31)


@pytest_asyncio.fixture
async def remove_test_periods():
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(FinancialPeriod).where(FinancialPeriod.name.like("FY reversal test %"))
        )
        await db.commit()


@pytest.mark.asyncio
async def test_posted_journal_is_corrected_by_idempotent_linked_reversal(
    client, auth, approver_auth, remove_test_periods
):
    marker = uuid4().hex[:8]
    period = await client.post(
        "/api/v1/finance/periods",
        headers=auth,
        json={
            "name": f"FY reversal test {marker}",
            "start_date": TEST_START.isoformat(),
            "end_date": TEST_END.isoformat(),
        },
    )
    assert period.status_code == 201, period.text

    account_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in account_response.json()["items"]}
    original_response = await client.post(
        "/api/v1/finance/journal-entries",
        headers=auth,
        json={
            "entry_date": date(2090, 5, 15).isoformat(),
            "reference": f"REV-TEST:{marker}",
            "memo": "Original adjustment",
            "lines": [
                {"account_id": accounts["1010"], "debit": "125.50", "credit": "0"},
                {"account_id": accounts["4000"], "debit": "0", "credit": "125.50"},
            ],
        },
    )
    assert original_response.status_code == 201, original_response.text
    original = original_response.json()

    posted_response = await client.post(
        f"/api/v1/finance/journal-entries/{original['id']}/post", headers=auth
    )
    assert posted_response.status_code == 200, posted_response.text
    assert posted_response.json()["status"] == "draft"
    assert posted_response.json()["approval_status"] == "pending"
    approvals = await client.get("/api/v1/finance/approvals", headers=auth)
    approval = next(
        row for row in approvals.json()["items"] if row["entity_id"] == original["id"]
    )
    self_approval = await client.post(
        f"/api/v1/finance/approvals/{approval['id']}/approve",
        headers=auth,
        json={"reason": "Self approval is not permitted"},
    )
    assert self_approval.status_code == 422, self_approval.text
    approved = await client.post(
        f"/api/v1/finance/approvals/{approval['id']}/approve",
        headers=approver_auth,
        json={"reason": "Reviewed supporting documents"},
    )
    assert approved.status_code == 200, approved.text
    journals = await client.get("/api/v1/finance/journal-entries", headers=auth)
    original = next(row for row in journals.json()["items"] if row["id"] == original["id"])
    assert original["status"] == "posted"

    reversal_payload = {
        "reversal_date": date(2090, 6, 1).isoformat(),
        "reason": "Correct the original account allocation",
    }
    reversal_response = await client.post(
        f"/api/v1/finance/journal-entries/{original['id']}/reverse",
        headers=auth,
        json=reversal_payload,
    )
    assert reversal_response.status_code == 200, reversal_response.text
    reversal = reversal_response.json()
    assert reversal["status"] == "posted"
    assert reversal["reversal_of_id"] == original["id"]
    assert reversal["memo"].endswith(reversal_payload["reason"])
    assert [
        (line["account_id"], line["debit"], line["credit"])
        for line in reversal["lines"]
    ] == [
        (line["account_id"], line["credit"], line["debit"])
        for line in original["lines"]
    ]

    repeated = await client.post(
        f"/api/v1/finance/journal-entries/{original['id']}/reverse",
        headers=auth,
        json={**reversal_payload, "reason": "Retry of the same reversal"},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == reversal["id"]

    reversal_of_reversal = await client.post(
        f"/api/v1/finance/journal-entries/{reversal['id']}/reverse",
        headers=auth,
        json=reversal_payload,
    )
    assert reversal_of_reversal.status_code == 409, reversal_of_reversal.text

    journals = await client.get(
        "/api/v1/finance/journal-entries",
        headers=auth,
        params={"size": 200},
    )
    assert journals.status_code == 200, journals.text
    original_from_list = next(
        entry for entry in journals.json()["items"] if entry["id"] == original["id"]
    )
    assert original_from_list["reversed_by_entry_id"] == reversal["id"]


@pytest.mark.asyncio
async def test_draft_journal_cannot_be_reversed(client, auth, remove_test_periods):
    marker = uuid4().hex[:8]
    account_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in account_response.json()["items"]}
    draft = await client.post(
        "/api/v1/finance/journal-entries",
        headers=auth,
        json={
            "entry_date": date.today().isoformat(),
            "reference": f"DRAFT-REV-TEST:{marker}",
            "lines": [
                {"account_id": accounts["1010"], "debit": "10.00", "credit": "0"},
                {"account_id": accounts["4000"], "debit": "0", "credit": "10.00"},
            ],
        },
    )
    assert draft.status_code == 201, draft.text

    response = await client.post(
        f"/api/v1/finance/journal-entries/{draft.json()['id']}/reverse",
        headers=auth,
        json={"reversal_date": date.today().isoformat(), "reason": "Draft test"},
    )
    assert response.status_code == 422, response.text
