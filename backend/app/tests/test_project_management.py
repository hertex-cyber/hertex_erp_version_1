from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

BASE = "/api/v1/projects"


async def _create_project(client, auth, **overrides):
    marker = uuid4().hex[:8]
    payload = {
        "name": f"PM Project {marker}",
        "code": f"PM-{marker}",
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
    body = {"event": event}
    body.update(payload)
    response = await client.post(path, headers=auth, json=body)
    assert response.status_code == 200, response.text
    return response.json()


async def _first_employee_id(client, auth):
    response = await client.get(
        "/api/v1/hr/employees", headers=auth, params={"size": 1}
    )
    assert response.status_code == 200, response.text
    employees = response.json()["items"]
    assert employees
    return employees[0]["id"]


@pytest.mark.asyncio
async def test_project_work_item_sprint_dependency_and_reports(client, auth):
    project = await _create_project(client, auth)
    project_id = project["id"]
    assert project["number"].startswith("PRJ-")
    assert project["status"] == "draft"
    assert project["tasks"] == []

    result = await _transition(
        client, auth, f"{BASE}/projects/{project_id}/submit", "submit"
    )
    assert result["status"] == "approval_pending"
    result = await _transition(
        client, auth, f"{BASE}/projects/{project_id}/approve", "approve"
    )
    assert result["status"] == "approved"
    result = await _transition(
        client, auth, f"{BASE}/projects/{project_id}/activate", "activate"
    )
    assert result["status"] == "active"

    work_item = await _create_work_item(client, auth, project_id, "Build API")
    work_item_id = work_item["id"]
    assert work_item["number"].startswith("PRJ-T-")
    assert work_item["board_id"]
    assert work_item["board_column_id"]

    for event, expected in [
        ("refine", "todo"),
        ("start", "in_progress"),
        ("block", "blocked"),
        ("unblock", "in_progress"),
        ("submit_review", "in_review"),
        ("approve", "done"),
        ("accept", "accepted"),
    ]:
        work_item = await _transition(
            client,
            auth,
            f"{BASE}/work-items/{work_item_id}/transition",
            event,
        )
        assert work_item["status"] == expected

    ranked = await client.patch(
        f"{BASE}/work-items/{work_item_id}/rank",
        headers=auth,
        params={"rank": "10.5000"},
    )
    assert ranked.status_code == 200, ranked.text
    assert Decimal(ranked.json()["rank"]) == Decimal("10.5")

    today = date.today()
    sprint_response = await client.post(
        f"{BASE}/sprints",
        headers=auth,
        json={
            "project_id": project_id,
            "name": "Sprint 1",
            "start_date": today.isoformat(),
            "end_date": (today + timedelta(days=14)).isoformat(),
        },
    )
    assert sprint_response.status_code == 201, sprint_response.text
    sprint = sprint_response.json()
    assert sprint["number"].startswith("SPR-")
    sprint = await _transition(
        client, auth, f"{BASE}/sprints/{sprint['id']}/transition", "start"
    )
    assert sprint["status"] == "active"

    successor = await _create_work_item(
        client, auth, project_id, "Deploy API", estimated_hours="4.00"
    )
    dependency_response = await client.post(
        f"{BASE}/dependencies",
        headers=auth,
        json={
            "predecessor_id": work_item_id,
            "successor_id": successor["id"],
            "type": "FS",
            "lag_days": 1,
        },
    )
    assert dependency_response.status_code == 201, dependency_response.text
    dependency = dependency_response.json()
    assert dependency["status"] == "proposed"
    dependency = await _transition(
        client, auth, f"{BASE}/dependencies/{dependency['id']}/transition", "confirm"
    )
    assert dependency["status"] == "active"

    cycle_response = await client.post(
        f"{BASE}/dependencies",
        headers=auth,
        json={
            "predecessor_id": successor["id"],
            "successor_id": work_item_id,
            "type": "FS",
        },
    )
    assert cycle_response.status_code == 409, cycle_response.text

    critical_path = await client.get(
        f"{BASE}/projects/{project_id}/critical-path", headers=auth
    )
    assert critical_path.status_code == 200, critical_path.text
    assert critical_path.json()["project_id"] == project_id
    assert critical_path.json()["steps"]

    summary = await client.get(f"{BASE}/projects/{project_id}/summary", headers=auth)
    assert summary.status_code == 200, summary.text
    summary_body = summary.json()
    assert summary_body["total_tasks"] == 2
    assert summary_body["done_tasks"] == 1
    assert summary_body["open_tasks"] == 1
    assert Decimal(summary_body["estimated_hours"]) == Decimal("12")

    governance = await client.get(
        f"{BASE}/reports/governance", headers=auth, params={"project_id": project_id}
    )
    assert governance.status_code == 200, governance.text
    assert governance.json()["project_id"] == project_id


@pytest.mark.asyncio
async def test_time_approval_billing_posting_and_finance_invoice(client, auth):
    project = await _create_project(client, auth)
    project_id = project["id"]
    employee_id = await _first_employee_id(client, auth)
    work_item = await _create_work_item(
        client, auth, project_id, "Billable build", employee_id=employee_id
    )

    entry_date = date.today()
    entry_response = await client.post(
        f"{BASE}/time-entries",
        headers=auth,
        json={
            "work_item_id": work_item["id"],
            "employee_id": employee_id,
            "entry_date": entry_date.isoformat(),
            "hours": "2.00",
            "description": "Implementation work",
            "billable": True,
            "billable_rate": "100.00",
        },
    )
    assert entry_response.status_code == 201, entry_response.text
    entry = entry_response.json()
    assert entry["status"] == "draft"

    entry = await _transition(
        client, auth, f"{BASE}/time-entries/{entry['id']}/submit", "submit"
    )
    assert entry["status"] == "submitted"
    approved_response = await client.post(
        f"{BASE}/time-entries/{entry['id']}/approve",
        headers=auth,
        json={"comment": "approved"},
    )
    assert approved_response.status_code == 200, approved_response.text
    assert approved_response.json()["status"] == "approved"

    updated_item = await client.get(
        f"{BASE}/work-items/{work_item['id']}", headers=auth
    )
    assert updated_item.status_code == 200, updated_item.text
    assert Decimal(updated_item.json()["actual_hours"]) == Decimal("2")

    week_start = entry_date - timedelta(days=entry_date.weekday())
    timesheets = await client.get(
        f"{BASE}/timesheets",
        headers=auth,
        params={"employee_id": employee_id, "week_start": week_start.isoformat()},
    )
    assert timesheets.status_code == 200, timesheets.text
    timesheet_items = timesheets.json()["items"]
    assert timesheet_items
    timesheet_id = timesheet_items[0]["id"]

    submitted = await client.patch(
        f"{BASE}/timesheets/{timesheet_id}",
        headers=auth,
        json={"status": "submitted"},
    )
    assert submitted.status_code == 200, submitted.text
    approved_timesheet = await client.post(
        f"{BASE}/timesheets/{timesheet_id}/approve",
        headers=auth,
        json={"comment": "approved"},
    )
    assert approved_timesheet.status_code == 200, approved_timesheet.text
    assert approved_timesheet.json()["status"] == "approved"

    preview = await client.get(
        f"{BASE}/billing/preview", headers=auth, params={"project_id": project_id}
    )
    assert preview.status_code == 200, preview.text
    preview_body = preview.json()
    assert len(preview_body["lines"]) == 1
    assert preview_body["lines"][0]["source_type"] == "time"
    assert Decimal(preview_body["gross_amount"]) == Decimal("200.00")

    idempotency_key = uuid4().hex
    run_response = await client.post(
        f"{BASE}/billing-runs",
        headers=auth,
        json={
            "project_id": project_id,
            "period": "2026-11",
            "billing_type": "time_and_material",
            "idempotency_key": idempotency_key,
        },
    )
    assert run_response.status_code == 201, run_response.text
    run = run_response.json()
    assert run["status"] == "draft"

    duplicate = await client.post(
        f"{BASE}/billing-runs",
        headers=auth,
        json={
            "project_id": project_id,
            "period": "2026-11",
            "billing_type": "time_and_material",
            "idempotency_key": idempotency_key,
        },
    )
    assert duplicate.status_code == 201, duplicate.text
    assert duplicate.json()["id"] == run["id"]

    run = await _transition(
        client, auth, f"{BASE}/billing-runs/{run['id']}/transition", "generate"
    )
    assert run["status"] == "review"
    run = await _transition(
        client, auth, f"{BASE}/billing-runs/{run['id']}/transition", "approve"
    )
    assert run["status"] == "approved"

    posted = await client.post(
        f"{BASE}/billing-runs/{run['id']}/post",
        headers=auth,
        json={"tax_amount": "18.00", "notes": "PM test invoice"},
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "invoiced"

    invoice_links = await client.get(
        f"{BASE}/invoice-links", headers=auth, params={"billing_run_id": run["id"]}
    )
    assert invoice_links.status_code == 200, invoice_links.text
    links = invoice_links.json()["items"]
    assert len(links) == 1
    assert links[0]["finance_invoice_id"]
    assert Decimal(links[0]["amount"]) == Decimal("218.00")

    updated_project = await client.get(f"{BASE}/{project_id}", headers=auth)
    assert updated_project.status_code == 200, updated_project.text
    assert Decimal(updated_project.json()["total_billed"]) == Decimal("218.00")

    journal_entries = await client.get(
        "/api/v1/finance/journal-entries",
        headers=auth,
        params={"q": idempotency_key, "size": 50},
    )
    assert journal_entries.status_code == 200, journal_entries.text


@pytest.mark.asyncio
async def test_ai_action_requires_approval_and_reverse(client, auth):
    project = await _create_project(client, auth)
    response = await client.post(
        f"{BASE}/ai/actions",
        headers=auth,
        json={
            "action_type": "draft_risk",
            "entity_type": "project",
            "entity_id": project["id"],
            "proposed_json": {
                "title": "AI-suggested risk",
                "description": "Delivery may slip",
                "probability": 3,
                "impact": 4,
                "score": 12,
            },
            "explanation": "Overdue work items indicate delivery risk",
        },
    )
    assert response.status_code == 201, response.text
    action = response.json()
    assert action["status"] == "proposed"

    premature = await client.post(
        f"{BASE}/ai/actions/{action['id']}/execute", headers=auth, json={}
    )
    assert premature.status_code == 409, premature.text

    reviewed = await client.post(
        f"{BASE}/ai/actions/{action['id']}/review",
        headers=auth,
        json={"comment": "human approved"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["status"] == "approved"

    executed = await client.post(
        f"{BASE}/ai/actions/{action['id']}/execute", headers=auth, json={}
    )
    assert executed.status_code == 200, executed.text
    assert executed.json()["status"] == "executed"

    risks = await client.get(
        f"{BASE}/risks", headers=auth, params={"project_id": project["id"]}
    )
    assert risks.status_code == 200, risks.text
    assert any(
        risk["title"] == "AI-suggested risk" for risk in risks.json()["items"]
    )

    reversed_action = await client.post(
        f"{BASE}/ai/actions/{action['id']}/reverse",
        headers=auth,
        json={"reversal_reference": "test-reverse"},
    )
    assert reversed_action.status_code == 200, reversed_action.text
    assert reversed_action.json()["status"] == "reversed"
    assert reversed_action.json()["reversal_reference"] == "test-reverse"


@pytest.mark.asyncio
async def test_resource_governance_and_outbox_flows(client, auth):
    project = await _create_project(client, auth)
    project_id = project["id"]
    employee_id = await _first_employee_id(client, auth)
    today = date.today()
    start_date = today - timedelta(days=1)
    end_date = today + timedelta(days=7)

    capacity = await client.get(
        f"{BASE}/resources/capacity",
        headers=auth,
        params={"employee_id": employee_id},
    )
    assert capacity.status_code == 200, capacity.text
    refreshed = await client.post(
        f"{BASE}/resources/capacity/refresh",
        headers=auth,
        params={"employee_id": employee_id},
    )
    assert refreshed.status_code == 200, refreshed.text
    workload = await client.get(f"{BASE}/resources/workload", headers=auth)
    assert workload.status_code == 200, workload.text

    booking_response = await client.post(
        f"{BASE}/bookings",
        headers=auth,
        json={
            "project_id": project_id,
            "employee_id": employee_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "hours_per_day": "4.00",
            "allocation_percent": "50.00",
        },
    )
    assert booking_response.status_code == 201, booking_response.text
    booking = booking_response.json()
    assert booking["status"] == "requested"
    booking = await _transition(
        client, auth, f"{BASE}/resource-bookings/{booking['id']}/approve", "approve"
    )
    assert booking["status"] == "confirmed"

    risk_response = await client.post(
        f"{BASE}/risks",
        headers=auth,
        json={"project_id": project_id, "title": "Vendor delay"},
    )
    assert risk_response.status_code == 201, risk_response.text
    risk = risk_response.json()
    risk = await _transition(
        client, auth, f"{BASE}/risks/{risk['id']}/transition", "assess"
    )
    assert risk["status"] == "analysing"
    risk = await _transition(
        client, auth, f"{BASE}/risks/{risk['id']}/transition", "escalate"
    )
    assert risk["status"] == "escalated"

    issue_response = await client.post(
        f"{BASE}/issues",
        headers=auth,
        json={"project_id": project_id, "title": "Build failure", "severity": "high"},
    )
    assert issue_response.status_code == 201, issue_response.text
    issue = issue_response.json()
    issue = await _transition(
        client, auth, f"{BASE}/issues/{issue['id']}/transition", "triage"
    )
    assert issue["status"] == "triaged"

    change_response = await client.post(
        f"{BASE}/change-requests",
        headers=auth,
        json={"project_id": project_id, "title": "Extend scope"},
    )
    assert change_response.status_code == 201, change_response.text
    change_request = change_response.json()
    change_request = await _transition(
        client,
        auth,
        f"{BASE}/change-requests/{change_request['id']}/transition",
        "submit",
    )
    assert change_request["status"] == "submitted"
    change_request = await _transition(
        client,
        auth,
        f"{BASE}/change-requests/{change_request['id']}/transition",
        "approve",
    )
    assert change_request["status"] == "approved"

    stats = await client.get(f"{BASE}/outbox/stats", headers=auth)
    assert stats.status_code == 200, stats.text
    assert {"pending", "published", "failed"} <= set(stats.json())

    dispatch = await client.post(f"{BASE}/outbox/dispatch", headers=auth)
    assert dispatch.status_code == 200, dispatch.text
    assert {"published", "failed"} <= set(dispatch.json())
