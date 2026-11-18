from datetime import date
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_chart_of_accounts_enforces_unique_codes_and_valid_tree(client, auth):
    marker = uuid4().hex[:8].upper()
    root = await client.post(
        "/api/v1/finance/accounts",
        headers=auth,
        json={
            "code": f"test-{marker}",
            "name": f"Test root {marker}",
            "account_type": "asset",
        },
    )
    assert root.status_code == 201, root.text
    root_body = root.json()
    assert root_body["code"] == f"TEST-{marker}"
    assert root_body["name"] == f"Test root {marker}"

    duplicate = await client.post(
        "/api/v1/finance/accounts",
        headers=auth,
        json={
            "code": f" Test-{marker} ",
            "name": "Duplicate code",
            "account_type": "asset",
        },
    )
    assert duplicate.status_code == 409, duplicate.text

    wrong_type_parent = await client.post(
        "/api/v1/finance/accounts",
        headers=auth,
        json={
            "code": f"CHILD-{marker}",
            "name": "Invalid child",
            "account_type": "expense",
            "parent_id": root_body["id"],
        },
    )
    assert wrong_type_parent.status_code == 422, wrong_type_parent.text

    child = await client.post(
        "/api/v1/finance/accounts",
        headers=auth,
        json={
            "code": f"CHILD-{marker}",
            "name": "Valid child",
            "account_type": "asset",
            "parent_id": root_body["id"],
        },
    )
    assert child.status_code == 201, child.text

    self_parent = await client.patch(
        f"/api/v1/finance/accounts/{root_body['id']}",
        headers=auth,
        json={"parent_id": root_body["id"]},
    )
    assert self_parent.status_code == 422, self_parent.text

    cycle = await client.patch(
        f"/api/v1/finance/accounts/{root_body['id']}",
        headers=auth,
        json={"parent_id": child.json()["id"]},
    )
    assert cycle.status_code == 422, cycle.text

    deactivated_parent = await client.patch(
        f"/api/v1/finance/accounts/{root_body['id']}",
        headers=auth,
        json={"is_active": False},
    )
    assert deactivated_parent.status_code == 409, deactivated_parent.text


@pytest.mark.asyncio
async def test_posted_account_history_prevents_type_change_and_archive(
    client, auth, approver_auth
):
    marker = uuid4().hex[:8].upper()
    created = await client.post(
        "/api/v1/finance/accounts",
        headers=auth,
        json={
            "code": f"HIST-{marker}",
            "name": f"Historical account {marker}",
            "account_type": "asset",
        },
    )
    assert created.status_code == 201, created.text
    account = created.json()

    standard_accounts = await client.get("/api/v1/finance/accounts", headers=auth)
    codes = {row["code"]: row["id"] for row in standard_accounts.json()["items"]}
    entry = await client.post(
        "/api/v1/finance/journal-entries",
        headers=auth,
        json={
            "entry_date": date.today().isoformat(),
            "reference": f"COA-HISTORY:{marker}",
            "lines": [
                {"account_id": account["id"], "debit": "15.00", "credit": "0"},
                {"account_id": codes["4000"], "debit": "0", "credit": "15.00"},
            ],
        },
    )
    assert entry.status_code == 201, entry.text
    posted = await client.post(
        f"/api/v1/finance/journal-entries/{entry.json()['id']}/post",
        headers=auth,
    )
    assert posted.status_code == 200, posted.text
    approvals = await client.get("/api/v1/finance/approvals", headers=auth)
    approval = next(
        row for row in approvals.json()["items"] if row["entity_id"] == entry.json()["id"]
    )
    approved = await client.post(
        f"/api/v1/finance/approvals/{approval['id']}/approve",
        headers=approver_auth,
        json={"reason": "Ledger posting reviewed"},
    )
    assert approved.status_code == 200, approved.text

    type_change = await client.patch(
        f"/api/v1/finance/accounts/{account['id']}",
        headers=auth,
        json={"account_type": "expense"},
    )
    assert type_change.status_code == 409, type_change.text

    archive = await client.delete(
        f"/api/v1/finance/accounts/{account['id']}",
        headers=auth,
    )
    assert archive.status_code == 409, archive.text
