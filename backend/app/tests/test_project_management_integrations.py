import asyncio
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

from app.core.events import publish

BASE = "/api/v1/projects"
PASSWORD = "Quartz!Maple#R8v"


async def _create_project(client, auth, **overrides):
    marker = uuid4().hex[:10]
    payload = {
        "name": f"PM Integration {marker}",
        "code": f"PMI-{marker}",
        "billing_type": "time_and_material",
        "currency": "INR",
        "budget": "10000.00",
        "budget_cost": "5000.00",
        "budget_revenue": "12000.00",
        "contract_value": "12000.00",
        "start_date": (date.today() - timedelta(days=7)).isoformat(),
        "end_date": (date.today() + timedelta(days=30)).isoformat(),
    }
    payload.update(overrides)
    response = await client.post(BASE, headers=auth, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _transition(client, auth, path, event, **extra_headers):
    response = await client.post(
        path, headers={**auth, **extra_headers}, json={"event": event}
    )
    assert response.status_code == 200, response.text
    return response.json()


async def _activate_project(client, auth):
    project = await _create_project(client, auth)
    for event in ("submit", "approve"):
        project = await _transition(
            client, auth, f"{BASE}/projects/{project['id']}/{event}", event
        )
    return project


async def _create_employee(client, auth):
    marker = uuid4().hex[:10]
    response = await client.post(
        "/api/v1/hr/employees",
        headers=auth,
        json={
            "employee_code": f"EMP-{marker}",
            "first_name": "Integration",
            "last_name": "Employee",
            "email": f"pmi-{marker}@hertex.example.com",
            "employment_type": "full_time",
            "status": "active",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _create_work_item(client, auth, project_id, title):
    response = await client.post(
        f"{BASE}/work-items",
        headers=auth,
        json={"project_id": project_id, "title": title, "estimated_hours": "8.00"},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _wait_for_activity(client, auth, params):
    for _ in range(30):
        response = await client.get(f"{BASE}/activities", headers=auth, params=params)
        assert response.status_code == 200, response.text
        if response.json()["items"]:
            return response.json()["items"]
        await asyncio.sleep(0.05)
    return []


@pytest.mark.asyncio
async def test_activation_outbox_correlation_idempotency_and_audit(client, auth):
    project = await _create_project(client, auth)
    project_id = project["id"]
    await _transition(client, auth, f"{BASE}/projects/{project_id}/submit", "submit")
    await _transition(client, auth, f"{BASE}/projects/{project_id}/approve", "approve")
    correlation_id = uuid4().hex
    idempotency_key = uuid4().hex
    activated = await _transition(
        client,
        auth,
        f"{BASE}/projects/{project_id}/activate",
        "activate",
        **{
            "x-correlation-id": correlation_id,
            "Idempotency-Key": idempotency_key,
        },
    )
    assert activated["status"] == "active"
    repeated = await client.post(
        f"{BASE}/projects/{project_id}/activate",
        headers={**auth, "Idempotency-Key": idempotency_key},
        json={"event": "activate"},
    )
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == project_id

    outbox = await client.get(
        f"{BASE}/outbox",
        headers=auth,
        params={"event_name": "project.started", "size": 50},
    )
    assert outbox.status_code == 200, outbox.text
    event = next(
        row
        for row in outbox.json()["items"]
        if (row.get("payload") or {}).get("project_id") == project_id
    )
    assert event["correlation_id"] == correlation_id

    dispatched = await client.post(f"{BASE}/outbox/dispatch", headers=auth, json={})
    assert dispatched.status_code == 200, dispatched.text
    activities = await _wait_for_activity(
        client,
        auth,
        {
            "entity_type": "project",
            "entity_id": project_id,
            "action": "project.started.integration",
        },
    )
    assert activities
    assert activities[0]["correlation_id"] == correlation_id

    audit = await client.get(
        "/api/v1/system/audit-logs",
        headers=auth,
        params={"module": "projects", "action": "project.activate", "size": 50},
    )
    assert audit.status_code == 200, audit.text
    assert any(row.get("entity_id") == project_id for row in audit.json()["items"])


@pytest.mark.asyncio
async def test_leave_approval_updates_capacity_and_workload(client, auth):
    employee = await _create_employee(client, auth)
    project = await _activate_project(client, auth)
    monday = date.today() - timedelta(days=date.today().weekday())
    friday = monday + timedelta(days=4)
    booking = await client.post(
        f"{BASE}/bookings",
        headers=auth,
        json={
            "project_id": project["id"],
            "employee_id": employee["id"],
            "start_date": monday.isoformat(),
            "end_date": friday.isoformat(),
            "hours_per_day": "4.00",
            "allocation_percent": "50.00",
        },
    )
    assert booking.status_code == 201, booking.text
    confirmed = await _transition(
        client,
        auth,
        f"{BASE}/resource-bookings/{booking.json()['id']}/approve",
        "approve",
    )
    assert confirmed["status"] == "confirmed"

    refreshed = await client.post(
        f"{BASE}/resources/capacity/refresh",
        headers=auth,
        params={"employee_id": employee["id"], "start_date": monday.isoformat(), "end_date": friday.isoformat()},
    )
    assert refreshed.status_code == 200, refreshed.text
    before = next(row for row in refreshed.json() if row["week_start"] == monday.isoformat())
    assert Decimal(before["available_hours"]) == Decimal("20")

    leave = await client.post(
        "/api/v1/hr/leave-requests",
        headers=auth,
        json={
            "employee_id": employee["id"],
            "leave_type": "casual",
            "start_date": monday.isoformat(),
            "end_date": (monday + timedelta(days=1)).isoformat(),
            "days": "2.0",
            "status": "pending",
        },
    )
    assert leave.status_code == 201, leave.text
    approved = await client.post(
        f"/api/v1/hr/leave-requests/{leave.json()['id']}/approve", headers=auth, json={}
    )
    assert approved.status_code == 200, approved.text

    capacity = await client.get(
        f"{BASE}/capacity-calendars",
        headers=auth,
        params={"employee_id": employee["id"], "week_start": monday.isoformat()},
    )
    assert capacity.status_code == 200, capacity.text
    assert Decimal(capacity.json()["items"][0]["planned_leave_hours"]) == Decimal("16")

    workload = await client.get(
        f"{BASE}/workload-snapshots",
        headers=auth,
        params={"employee_id": employee["id"], "week_start": monday.isoformat()},
    )
    assert workload.status_code == 200, workload.text
    row = workload.json()["items"][0]
    assert Decimal(row["available_hours"]) == Decimal("4")
    assert row["overallocated"] is False


@pytest.mark.asyncio
async def test_employee_lifecycle_events_update_project_capacity(client, auth):
    onboarded = await _create_employee(client, auth)
    monday = date.today() - timedelta(days=date.today().weekday())
    calendars = await client.get(
        f"{BASE}/capacity-calendars",
        headers=auth,
        params={"employee_id": onboarded["id"], "week_start": monday.isoformat()},
    )
    assert calendars.status_code == 200, calendars.text
    assert calendars.json()["items"]

    exited = await _create_employee(client, auth)
    project = await _activate_project(client, auth)
    booking = await client.post(
        f"{BASE}/bookings",
        headers=auth,
        json={
            "project_id": project["id"],
            "employee_id": exited["id"],
            "start_date": (date.today() + timedelta(days=1)).isoformat(),
            "end_date": (date.today() + timedelta(days=5)).isoformat(),
            "hours_per_day": "4.00",
        },
    )
    assert booking.status_code == 201, booking.text
    confirmed = await _transition(
        client,
        auth,
        f"{BASE}/resource-bookings/{booking.json()['id']}/approve",
        "approve",
    )
    assert confirmed["status"] == "confirmed"
    exit_response = await client.post(
        f"/api/v1/hr/employees/{exited['id']}/exit",
        headers=auth,
        json={"date_of_exit": date.today().isoformat()},
    )
    assert exit_response.status_code == 200, exit_response.text
    all_bookings = await client.get(
        f"{BASE}/bookings",
        headers=auth,
        params={"employee_id": exited["id"], "include_inactive": "true"},
    )
    assert all_bookings.status_code == 200, all_bookings.text
    disabled = next(
        row for row in all_bookings.json()["items"] if row["id"] == booking.json()["id"]
    )
    assert disabled["is_active"] is False


@pytest.mark.asyncio
async def test_support_ticket_project_work_is_linked_and_completion_notified(client, auth):
    marker = uuid4().hex[:10]
    created = await client.post(
        "/api/v1/support/tickets",
        headers=auth,
        json={
            "subject": f"Customer escalation {marker}",
            "description": f"Urgent issue {marker} requiring delivery work",
            "requester_name": "Escalation Desk",
            "requester_email": f"escalation-{marker}@hertex.example.com",
            "priority": "high",
            "channel": "email",
            "needs_project_work": True,
        },
    )
    assert created.status_code == 201, created.text
    ticket = created.json()
    assert ticket["needs_project_work"] is True
    assert ticket["project_work_item_id"]

    work_item_id = ticket["project_work_item_id"]
    for event in ("start", "submit_review", "approve"):
        response = await client.post(
            f"{BASE}/work-items/{work_item_id}/transition",
            headers=auth,
            json={"event": event},
        )
        assert response.status_code == 200, response.text
    dispatched = await client.post(f"{BASE}/outbox/dispatch", headers=auth, json={})
    assert dispatched.status_code == 200, dispatched.text

    refreshed = await client.get(
        f"/api/v1/support/tickets/{ticket['id']}", headers=auth
    )
    assert refreshed.status_code == 200, refreshed.text
    messages = refreshed.json()["messages"]
    assert any(
        message["is_internal"] and f"Linked project work item {work_item_id}" in message["body"]
        for message in messages
    )


@pytest.mark.asyncio
async def test_invoice_paid_event_updates_invoice_link(client, auth):
    me = await client.get("/api/v1/auth/me", headers=auth)
    tenant_id = me.json()["tenant_id"]
    project = await _activate_project(client, auth)
    work_item = await _create_work_item(client, auth, project["id"], "Paid work")
    entry = await client.post(
        f"{BASE}/time-entries",
        headers=auth,
        json={
            "work_item_id": work_item["id"],
            "entry_date": date.today().isoformat(),
            "hours": "2.00",
            "billable": True,
            "billable_rate": "100.00",
        },
    )
    assert entry.status_code == 201, entry.text
    await _transition(client, auth, f"{BASE}/time-entries/{entry.json()['id']}/submit", "submit")
    await client.post(
        f"{BASE}/time-entries/{entry.json()['id']}/approve", headers=auth, json={}
    )
    idempotency_key = uuid4().hex
    run = await client.post(
        f"{BASE}/billing-runs",
        headers=auth,
        json={
            "project_id": project["id"],
            "period": "2026-11",
            "billing_type": "time_and_material",
            "idempotency_key": idempotency_key,
        },
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    await _transition(client, auth, f"{BASE}/billing-runs/{run_id}/transition", "generate")
    await _transition(client, auth, f"{BASE}/billing-runs/{run_id}/transition", "approve")
    posted = await client.post(
        f"{BASE}/billing-runs/{run_id}/post", headers=auth, json={"tax_amount": "0.00"}
    )
    assert posted.status_code == 200, posted.text
    links = await client.get(
        f"{BASE}/invoice-links", headers=auth, params={"billing_run_id": run_id}
    )
    assert links.status_code == 200, links.text
    link = links.json()["items"][0]

    await publish(
        "invoice.paid",
        {
            "tenant_id": tenant_id,
            "invoice_id": link["finance_invoice_id"],
            "amount": link["amount"],
            "invoice_status": "paid",
            "paid_at": date.today().isoformat(),
        },
    )
    updated_links = await client.get(
        f"{BASE}/invoice-links", headers=auth, params={"billing_run_id": run_id}
    )
    assert updated_links.status_code == 200, updated_links.text
    assert updated_links.json()["items"][0]["status"] == "paid"


@pytest.mark.asyncio
async def test_cross_tenant_project_data_is_invisible(client):
    admin_login = await client.post(
        "/api/v1/auth/login", json={"email": "admin@hertex.dev", "password": "Admin@12345"}
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_auth = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}
    project = await _activate_project(client, admin_auth)
    project_id = project["id"]
    work_item = await _create_work_item(client, admin_auth, project_id, "Secret work")

    marker = uuid4().hex[:10]
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": f"Other Tenant {marker}",
            "full_name": "Other Admin",
            "email": f"other-{marker}@example.com",
            "password": PASSWORD,
        },
    )
    assert registered.status_code == 201, registered.text
    other_login = await client.post(
        "/api/v1/auth/login",
        json={"email": f"other-{marker}@example.com", "password": PASSWORD},
    )
    assert other_login.status_code == 200, other_login.text
    other_auth = {"Authorization": f"Bearer {other_login.json()['access_token']}"}

    for path in (
        f"{BASE}/{project_id}",
        f"{BASE}/work-items/{work_item['id']}",
        f"{BASE}/projects/{project_id}/summary",
    ):
        response = await client.get(path, headers=other_auth)
        assert response.status_code == 404, response.text
    outbox = await client.get(
        f"{BASE}/outbox", headers=other_auth, params={"event_name": "project.started"}
    )
    assert outbox.status_code == 200, outbox.text
    assert outbox.json()["items"] == []
    denied = await client.patch(
        f"{BASE}/projects/{project_id}/health",
        headers=other_auth,
        json={"health": "red"},
    )
    assert denied.status_code == 404, denied.text
