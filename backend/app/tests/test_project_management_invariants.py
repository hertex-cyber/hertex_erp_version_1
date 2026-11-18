from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

BASE = "/api/v1/projects"
PASSWORD = "Quartz!Maple#R8v"


async def _create_project(client, auth, **overrides):
    marker = uuid4().hex[:10]
    payload = {
        "name": f"PM Invariant {marker}",
        "code": f"PMI-{marker}",
        "billing_type": "time_and_material",
        "currency": "INR",
        "budget": "10000.00",
        "budget_cost": "5000.00",
        "budget_revenue": "12000.00",
        "contract_value": "12000.00",
    }
    payload.update(overrides)
    response = await client.post(BASE, headers=auth, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _create_work_item(client, auth, project_id, title, **overrides):
    payload = {
        "project_id": project_id,
        "title": title,
        "status": "backlog",
        "estimated_hours": "8.00",
        "billable": True,
        "billable_rate": "100.00",
    }
    payload.update(overrides)
    response = await client.post(f"{BASE}/work-items", headers=auth, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _transition(client, auth, path, event, **payload):
    body = {"event": event, **payload}
    response = await client.post(path, headers=auth, json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _activate_project(client, auth, **overrides):
    project = await _create_project(client, auth, **overrides)
    project_id = project["id"]
    await _transition(client, auth, f"{BASE}/projects/{project_id}/submit", "submit")
    await _transition(client, auth, f"{BASE}/projects/{project_id}/approve", "approve")
    return await _transition(client, auth, f"{BASE}/projects/{project_id}/activate", "activate")


async def _to_in_review(client, auth, item_id):
    for event in ("refine", "start", "submit_review"):
        item = await _transition(client, auth, f"{BASE}/work-items/{item_id}/transition", event)
    return item


async def _to_done(client, auth, item_id):
    await _to_in_review(client, auth, item_id)
    return await _transition(client, auth, f"{BASE}/work-items/{item_id}/transition", "approve")


async def _role_id(client, auth, slug):
    response = await client.get("/api/v1/roles", headers=auth)
    assert response.status_code == 200, response.text
    role = next(row for row in response.json() if row["slug"] == slug)
    return role["id"]


async def _create_role_user(client, auth, role_slug, *, employee=False):
    marker = uuid4().hex[:10]
    email = f"pm-{role_slug}-{marker}@hertex.example.com"
    employee_id = None
    if employee:
        created_employee = await client.post(
            "/api/v1/hr/employees",
            headers=auth,
            json={
                "employee_code": f"EMP-{marker}",
                "first_name": "PM",
                "last_name": "Approver",
                "email": email,
                "employment_type": "full_time",
                "status": "active",
            },
        )
        assert created_employee.status_code == 201, created_employee.text
        employee_id = created_employee.json()["id"]
    role_id = await _role_id(client, auth, role_slug)
    created_user = await client.post(
        "/api/v1/users",
        headers=auth,
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": f"{role_slug.title()} {marker}",
            "role_ids": [role_id],
        },
    )
    assert created_user.status_code == 201, created_user.text
    token = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert token.status_code == 200, token.text
    headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    return {
        "employee_id": employee_id,
        "headers": headers,
        "user_id": created_user.json()["id"],
        "email": email,
    }


async def _create_time_entry(client, auth, work_item_id, employee_id, **overrides):
    payload = {
        "work_item_id": work_item_id,
        "employee_id": employee_id,
        "entry_date": date.today().isoformat(),
        "hours": "2.00",
        "description": "Implementation",
        "billable": True,
        "billable_rate": "100.00",
    }
    payload.update(overrides)
    response = await client.post(f"{BASE}/time-entries", headers=auth, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_illegal_transitions_and_workflow_configuration(client, auth):
    project = await _create_project(client, auth)
    illegal = await client.post(
        f"{BASE}/projects/{project['id']}/activate", headers=auth, json={"event": "activate"}
    )
    assert illegal.status_code == 409, illegal.text

    marker = uuid4().hex[:8]
    scheme = await client.post(
        f"{BASE}/workflows",
        headers=auth,
        json={
            "name": f"Scheme {marker}",
            "entity_type": "work_item",
            "statuses_json": ["todo", "in_progress", "done"],
            "status_categories_json": {"todo": "todo", "in_progress": "in_progress", "done": "done"},
        },
    )
    assert scheme.status_code == 201, scheme.text
    scheme_id = scheme.json()["id"]
    transition = await client.post(
        f"{BASE}/transitions",
        headers=auth,
        json={
            "scheme_id": scheme_id,
            "from_status": "todo",
            "event": "start",
            "to_status": "in_progress",
            "guard_code": "guard_assignee",
            "required_role": "manager",
            "required_fields_json": ["estimated_hours"],
        },
    )
    assert transition.status_code == 201, transition.text
    assert transition.json()["required_fields_json"] == ["estimated_hours"]


@pytest.mark.asyncio
async def test_time_entry_duplicate_date_window_and_derived_fields(client, auth):
    today = date.today()
    project = await _activate_project(
        client,
        auth,
        start_date=(today - timedelta(days=10)).isoformat(),
        end_date=(today + timedelta(days=10)).isoformat(),
    )
    work_item = await _create_work_item(client, auth, project["id"], "Time tracked work")
    marker = uuid4().hex[:10]
    entry_payload = {
        "work_item_id": work_item["id"],
        "employee_id": None,
        "entry_date": today.isoformat(),
        "hours": "2.00",
        "source": "jira",
        "external_id": marker,
        "billable": True,
        "billable_rate": "100.00",
    }
    first = await client.post(f"{BASE}/time-entries", headers=auth, json=entry_payload)
    assert first.status_code == 201, first.text
    duplicate = await client.post(f"{BASE}/time-entries", headers=auth, json=entry_payload)
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["id"] == first.json()["id"]

    outside = await client.post(
        f"{BASE}/time-entries",
        headers=auth,
        json={
            **entry_payload,
            "external_id": f"outside-{marker}",
            "entry_date": (today + timedelta(days=30)).isoformat(),
        },
    )
    assert outside.status_code == 422, outside.text

    entry = first.json()
    await _transition(client, auth, f"{BASE}/time-entries/{entry['id']}/submit", "submit")
    approved = await client.post(
        f"{BASE}/time-entries/{entry['id']}/approve", headers=auth, json={"comment": "ok"}
    )
    assert approved.status_code == 200, approved.text

    item_after = await client.get(f"{BASE}/work-items/{work_item['id']}", headers=auth)
    assert Decimal(item_after.json()["actual_hours"]) == Decimal("2")
    direct_edit = await client.patch(
        f"{BASE}/work-items/{work_item['id']}", headers=auth, json={"actual_hours": "99.00"}
    )
    assert direct_edit.status_code == 403, direct_edit.text
    locked_entry = await client.patch(
        f"{BASE}/time-entries/{entry['id']}", headers=auth, json={"description": "changed"}
    )
    assert locked_entry.status_code == 403, locked_entry.text


@pytest.mark.asyncio
async def test_self_approval_and_reviewer_rules_with_delegation(client, auth):
    manager = await _create_role_user(client, auth, "manager", employee=True)
    project = await _activate_project(client, auth)
    work_item = await _create_work_item(
        client, auth, project["id"], "Owned work", employee_id=manager["employee_id"]
    )
    entry = await _create_time_entry(client, auth, work_item["id"], manager["employee_id"])
    await _transition(client, auth, f"{BASE}/time-entries/{entry['id']}/submit", "submit")
    denied = await client.post(
        f"{BASE}/time-entries/{entry['id']}/approve",
        headers=manager["headers"],
        json={"comment": "self"},
    )
    assert denied.status_code == 409, denied.text

    delegation = await client.post(
        f"{BASE}/approvals",
        headers=auth,
        json={
            "entity_type": "time_entry",
            "entity_id": entry["id"],
            "approval_type": "delegation",
            "approver_employee_id": manager["employee_id"],
            "status": "approved",
        },
    )
    assert delegation.status_code == 201, delegation.text
    allowed = await client.post(
        f"{BASE}/time-entries/{entry['id']}/approve",
        headers=manager["headers"],
        json={"comment": "delegated"},
    )
    assert allowed.status_code == 200, allowed.text

    reviewed_item = await _create_work_item(
        client, auth, project["id"], "Owned review", employee_id=manager["employee_id"]
    )
    await _to_in_review(client, auth, reviewed_item["id"])
    reviewer_denied = await client.post(
        f"{BASE}/work-items/{reviewed_item['id']}/transition",
        headers=manager["headers"],
        json={"event": "approve"},
    )
    assert reviewer_denied.status_code == 409, reviewer_denied.text
    work_item_delegation = await client.post(
        f"{BASE}/approvals",
        headers=auth,
        json={
            "entity_type": "work_item",
            "entity_id": reviewed_item["id"],
            "approval_type": "delegation",
            "approver_employee_id": manager["employee_id"],
            "status": "approved",
        },
    )
    assert work_item_delegation.status_code == 201, work_item_delegation.text
    reviewer_allowed = await client.post(
        f"{BASE}/work-items/{reviewed_item['id']}/transition",
        headers=manager["headers"],
        json={"event": "approve"},
    )
    assert reviewer_allowed.status_code == 200, reviewer_allowed.text


@pytest.mark.asyncio
async def test_hierarchy_subtask_and_wip_limits(client, auth):
    project = await _activate_project(client, auth)
    parent = await _create_work_item(client, auth, project["id"], "Parent")
    child = await _create_work_item(
        client, auth, project["id"], "Child", parent_work_item_id=parent["id"]
    )
    other = await _create_work_item(client, auth, project["id"], "Other")
    cycle = await client.patch(
        f"{BASE}/work-items/{parent['id']}",
        headers=auth,
        json={"parent_work_item_id": child["id"]},
    )
    assert cycle.status_code == 409, cycle.text
    parent_with_children = await client.patch(
        f"{BASE}/work-items/{parent['id']}",
        headers=auth,
        json={"parent_work_item_id": other["id"]},
    )
    assert parent_with_children.status_code == 409, parent_with_children.text

    await _to_in_review(client, auth, parent["id"])
    blocked_parent = await client.post(
        f"{BASE}/work-items/{parent['id']}/transition", headers=auth, json={"event": "approve"}
    )
    assert blocked_parent.status_code == 409, blocked_parent.text
    await _to_done(client, auth, child["id"])
    finished_parent = await _transition(
        client, auth, f"{BASE}/work-items/{parent['id']}/transition", "approve"
    )
    assert finished_parent["status"] == "done"

    wip_project = await _activate_project(client, auth)
    boards = await client.get(
        f"{BASE}/boards", headers=auth, params={"project_id": wip_project["id"]}
    )
    board = boards.json()["items"][0]
    columns = await client.get(
        f"{BASE}/board-columns", headers=auth, params={"board_id": board["id"]}
    )
    done_column = next(row for row in columns.json()["items"] if row["name"] == "Done")
    updated = await client.patch(
        f"{BASE}/board-columns/{done_column['id']}",
        headers=auth,
        json={"wip_limit": 1, "wip_enforced": False},
    )
    assert updated.status_code == 200, updated.text
    first = await _create_work_item(
        client, auth, wip_project["id"], "WIP one", board_id=board["id"]
    )
    second = await _create_work_item(
        client, auth, wip_project["id"], "WIP two", board_id=board["id"]
    )
    await _to_done(client, auth, first["id"])
    await _to_in_review(client, auth, second["id"])
    advisory = await client.post(
        f"{BASE}/work-items/{second['id']}/transition", headers=auth, json={"event": "approve"}
    )
    assert advisory.status_code == 200, advisory.text
    activities = await client.get(
        f"{BASE}/activities",
        headers=auth,
        params={"entity_type": "board_column", "entity_id": done_column["id"], "action": "wip.limit.exceeded"},
    )
    assert activities.json()["items"]

    enforced = await client.patch(
        f"{BASE}/board-columns/{done_column['id']}", headers=auth, json={"wip_enforced": True}
    )
    assert enforced.status_code == 200, enforced.text
    third = await _create_work_item(
        client, auth, wip_project["id"], "WIP three", board_id=board["id"]
    )
    await _to_in_review(client, auth, third["id"])
    rejected = await client.post(
        f"{BASE}/work-items/{third['id']}/transition", headers=auth, json={"event": "approve"}
    )
    assert rejected.status_code == 409, rejected.text


@pytest.mark.asyncio
async def test_project_completion_waiver_with_approved_approval(client, auth):
    project = await _activate_project(client, auth)
    await _create_work_item(
        client, auth, project["id"], "Open blocker", priority="critical"
    )
    blocked = await client.post(
        f"{BASE}/projects/{project['id']}/complete", headers=auth, json={"event": "complete"}
    )
    assert blocked.status_code == 409, blocked.text
    assert "open blocking work items" in blocked.json()["errors"]["violations"]

    waiver_code = f"WAIVE-{uuid4().hex[:8]}"
    approval = await client.post(
        f"{BASE}/approvals",
        headers=auth,
        json={
            "entity_type": "project",
            "entity_id": project["id"],
            "approval_type": "completion_waiver",
            "status": "approved",
            "decision": "approved",
            "comments": f"Approved completion waiver {waiver_code}",
        },
    )
    assert approval.status_code == 201, approval.text

    completed = await _transition(
        client,
        auth,
        f"{BASE}/projects/{project['id']}/complete",
        "complete",
        waiver_code=waiver_code,
        waiver_approval_id=approval.json()["id"],
    )
    assert completed["status"] == "completed"
    activities = await client.get(
        f"{BASE}/activities",
        headers=auth,
        params={"entity_type": "project", "entity_id": project["id"], "action": "project.completion_waived"},
    )
    assert activities.status_code == 200, activities.text
    assert activities.json()["items"]


@pytest.mark.asyncio
async def test_project_completion_guards_and_baseline_immutability(client, auth):
    project = await _activate_project(client, auth)
    blocker = await _create_work_item(
        client, auth, project["id"], "High priority blocker", priority="high"
    )
    blocked = await client.post(
        f"{BASE}/projects/{project['id']}/complete", headers=auth, json={"event": "complete"}
    )
    assert blocked.status_code == 409, blocked.text
    cancelled = await client.post(
        f"{BASE}/work-items/{blocker['id']}/transition", headers=auth, json={"event": "cancel"}
    )
    assert cancelled.status_code == 200, cancelled.text

    completed = await _transition(
        client, auth, f"{BASE}/projects/{project['id']}/complete", "complete"
    )
    assert completed["status"] == "completed"
    illegal = await client.post(
        f"{BASE}/projects/{project['id']}/complete", headers=auth, json={"event": "complete"}
    )
    assert illegal.status_code == 409, illegal.text

    baseline = await client.post(
        f"{BASE}/projects/{project['id']}/baselines",
        headers=auth,
        json={"name": f"Baseline {uuid4().hex[:8]}"},
    )
    assert baseline.status_code == 201, baseline.text
    baseline_id = baseline.json()["id"]
    baseline_edit = await client.patch(
        f"{BASE}/baselines/{baseline_id}", headers=auth, json={"name": "Changed"}
    )
    assert baseline_edit.status_code == 403, baseline_edit.text
    snapshots = await client.get(
        f"{BASE}/baseline-snapshots", headers=auth, params={"baseline_id": baseline_id}
    )
    assert snapshots.json()["items"]
    snapshot_edit = await client.patch(
        f"{BASE}/baseline-snapshots/{snapshots.json()['items'][0]['id']}",
        headers=auth,
        json={"status": "changed"},
    )
    assert snapshot_edit.status_code == 403, snapshot_edit.text


@pytest.mark.asyncio
async def test_no_double_billing_after_finance_post(client, auth):
    project = await _activate_project(client, auth)
    work_item = await _create_work_item(client, auth, project["id"], "Billable")
    entry = await _create_time_entry(client, auth, work_item["id"], None)
    await _transition(client, auth, f"{BASE}/time-entries/{entry['id']}/submit", "submit")
    approved = await client.post(
        f"{BASE}/time-entries/{entry['id']}/approve", headers=auth, json={"comment": "ok"}
    )
    assert approved.status_code == 200, approved.text

    async def _run():
        response = await client.post(
            f"{BASE}/billing-runs",
            headers=auth,
            json={
                "project_id": project["id"],
                "period": "2026-11",
                "billing_type": "time_and_material",
                "idempotency_key": uuid4().hex,
            },
        )
        assert response.status_code == 201, response.text
        return response.json()

    first_run = await _run()
    second_run = await _run()
    await _transition(
        client, auth, f"{BASE}/billing-runs/{first_run['id']}/transition", "generate"
    )
    await _transition(
        client, auth, f"{BASE}/billing-runs/{first_run['id']}/transition", "approve"
    )
    await _transition(
        client, auth, f"{BASE}/billing-runs/{second_run['id']}/transition", "generate"
    )
    posted = await client.post(
        f"{BASE}/billing-runs/{first_run['id']}/post",
        headers=auth,
        json={"tax_amount": "0.00"},
    )
    assert posted.status_code == 200, posted.text

    double_billed = await client.post(
        f"{BASE}/billing-runs/{second_run['id']}/transition",
        headers=auth,
        json={"event": "approve"},
    )
    assert double_billed.status_code == 409, double_billed.text
    assert "already been billed" in double_billed.json()["detail"]


@pytest.mark.asyncio
async def test_ai_prohibited_action_and_financial_masking(client, auth):
    project = await _create_project(client, auth)
    prohibited = await client.post(
        f"{BASE}/ai/actions",
        headers=auth,
        json={
            "action_type": "approve_timesheet",
            "entity_type": "project",
            "entity_id": project["id"],
            "proposed_json": {},
        },
    )
    assert prohibited.status_code == 403, prohibited.text

    viewer = await _create_role_user(client, auth, "viewer")
    masked_project = await client.get(
        f"{BASE}/{project['id']}", headers=viewer["headers"]
    )
    assert masked_project.status_code == 200, masked_project.text
    assert masked_project.json()["budget"] is None
    assert masked_project.json()["total_billed"] is None

    masked_report = await client.get(
        f"{BASE}/reports/profitability",
        headers=viewer["headers"],
        params={"project_id": project["id"]},
    )
    assert masked_report.status_code == 200, masked_report.text
    assert all(row["margin_amount"] == "0" for row in masked_report.json())

    unmasked = await client.get(f"{BASE}/{project['id']}", headers=auth)
    assert Decimal(unmasked.json()["budget"]) == Decimal("10000.00")


@pytest.mark.asyncio
async def test_status_update_dedicated_approval_transition(client, auth):
    project = await _activate_project(client, auth)
    status_update = await client.post(
        f"{BASE}/status-updates",
        headers=auth,
        json={
            "project_id": project["id"],
            "period": "2026-W47",
            "health": "green",
            "summary": "On track",
            "status": "draft",
        },
    )
    assert status_update.status_code == 201, status_update.text
    status_id = status_update.json()["id"]

    direct_edit = await client.patch(
        f"{BASE}/status-updates/{status_id}", headers=auth, json={"status": "approved"}
    )
    assert direct_edit.status_code == 403, direct_edit.text
    premature = await client.post(
        f"{BASE}/status-updates/{status_id}/transition", headers=auth, json={"event": "approve"}
    )
    assert premature.status_code == 409, premature.text

    submitted = await _transition(
        client, auth, f"{BASE}/status-updates/{status_id}/transition", "submit"
    )
    assert submitted["status"] == "submitted"
    approved = await _transition(
        client, auth, f"{BASE}/status-updates/{status_id}/transition", "approve"
    )
    assert approved["status"] == "approved"
    published = await _transition(
        client, auth, f"{BASE}/status-updates/{status_id}/transition", "publish"
    )
    assert published["status"] == "published"
