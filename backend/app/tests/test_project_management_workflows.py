from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

BASE = "/api/v1/projects"
PASSWORD = "Quartz!Maple#R8v"


async def _create_project(client, auth, **overrides):
    marker = uuid4().hex[:10]
    payload = {
        "name": f"PM Workflow {marker}",
        "code": f"PMW-{marker}",
        "billing_type": "time_and_material",
        "currency": "INR",
        "budget": "10000.00",
        "budget_cost": "5000.00",
        "budget_revenue": "12000.00",
        "contract_value": "12000.00",
        "start_date": date.today().isoformat(),
        "end_date": (date.today() + timedelta(days=30)).isoformat(),
    }
    payload.update(overrides)
    response = await client.post(BASE, headers=auth, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _activate_project(client, auth, **overrides):
    project = await _create_project(client, auth, **overrides)
    for event in ("submit", "approve", "activate"):
        response = await client.post(
            f"{BASE}/projects/{project['id']}/{event}", headers=auth, json={"event": event}
        )
        assert response.status_code == 200, response.text
        project = response.json()
    return project


async def _transition(client, auth, path, event):
    response = await client.post(path, headers=auth, json={"event": event})
    assert response.status_code == 200, response.text
    return response.json()


async def _create_work_item(client, auth, project_id, title, **overrides):
    payload = {
        "project_id": project_id,
        "title": title,
        "status": "backlog",
        "estimated_hours": "8.00",
        "story_points": "5",
        "billable": True,
        "billable_rate": "100.00",
    }
    payload.update(overrides)
    response = await client.post(f"{BASE}/work-items", headers=auth, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


async def _to_done(client, auth, item_id):
    for event in ("refine", "start", "submit_review", "approve"):
        await _transition(client, auth, f"{BASE}/work-items/{item_id}/transition", event)
    response = await client.get(f"{BASE}/work-items/{item_id}", headers=auth)
    return response.json()


async def _role_id(client, auth, slug):
    response = await client.get("/api/v1/roles", headers=auth)
    assert response.status_code == 200, response.text
    return next(row["id"] for row in response.json() if row["slug"] == slug)


async def _create_viewer(client, auth):
    marker = uuid4().hex[:10]
    email = f"pmw-viewer-{marker}@hertex.example.com"
    created = await client.post(
        "/api/v1/users",
        headers=auth,
        json={
            "email": email,
            "password": PASSWORD,
            "full_name": f"Viewer {marker}",
            "role_ids": [await _role_id(client, auth, "viewer")],
        },
    )
    assert created.status_code == 201, created.text
    token = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    )
    assert token.status_code == 200, token.text
    return {
        "id": created.json()["id"],
        "headers": {"Authorization": f"Bearer {token.json()['access_token']}"},
    }


async def _create_time_entry(client, auth, work_item_id, **overrides):
    payload = {
        "work_item_id": work_item_id,
        "entry_date": date.today().isoformat(),
        "hours": "2.00",
        "description": "Workflow work",
        "billable": True,
        "billable_rate": "100.00",
    }
    payload.update(overrides)
    response = await client.post(f"{BASE}/time-entries", headers=auth, json=payload)
    assert response.status_code == 201, response.text
    entry = response.json()
    await _transition(client, auth, f"{BASE}/time-entries/{entry['id']}/submit", "submit")
    approved = await client.post(
        f"{BASE}/time-entries/{entry['id']}/approve", headers=auth, json={"comment": "ok"}
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


@pytest.mark.asyncio
async def test_hold_cancel_health_comments_links_and_backlog(client, auth):
    project = await _activate_project(client, auth)
    held = await _transition(client, auth, f"{BASE}/projects/{project['id']}/hold", "hold")
    assert held["status"] == "on_hold"
    health = await client.patch(
        f"{BASE}/projects/{project['id']}/health",
        headers=auth,
        json={"health": "amber", "health_reason": "waiting"},
    )
    assert health.status_code == 200, health.text
    assert health.json()["health"] == "amber"

    cancel_denied = await client.post(
        f"{BASE}/projects/{project['id']}/cancel", headers=auth, json={"event": "cancel"}
    )
    assert cancel_denied.status_code == 409, cancel_denied.text
    approval = await client.post(
        f"{BASE}/approvals",
        headers=auth,
        json={
            "entity_type": "project",
            "entity_id": project["id"],
            "approval_type": "cancellation",
            "status": "approved",
        },
    )
    assert approval.status_code == 201, approval.text
    cancelled = await _transition(client, auth, f"{BASE}/projects/{project['id']}/cancel", "cancel")
    assert cancelled["status"] == "cancelled"

    board_project = await _activate_project(client, auth)
    first = await _create_work_item(client, auth, board_project["id"], "Board first")
    second = await _create_work_item(client, auth, board_project["id"], "Board second")
    link = await client.post(
        f"{BASE}/work-items/{first['id']}/links",
        headers=auth,
        json={"linked_work_item_id": second["id"], "link_type": "relates_to"},
    )
    assert link.status_code == 201, link.text
    comment = await client.post(
        f"{BASE}/work-items/{first['id']}/comments",
        headers=auth,
        json={"body": "Please review", "mentions": ["@admin"]},
    )
    assert comment.status_code == 201, comment.text
    updated_comment = await client.patch(
        f"{BASE}/comments/{comment.json()['id']}", headers=auth, json={"body": "Reviewed"}
    )
    assert updated_comment.status_code == 200, updated_comment.text
    reordered = await client.patch(
        f"{BASE}/projects/{board_project['id']}/backlog",
        headers=auth,
        json={"moves": [{"work_item_id": second["id"], "rank": 1}]},
    )
    assert reordered.status_code == 200, reordered.text
    assert [row["id"] for row in reordered.json()][0] == second["id"]
    search = await client.get(
        f"{BASE}/work-items/search", headers=auth, params={"filter": "status = backlog"}
    )
    assert search.status_code == 200, search.text


@pytest.mark.asyncio
async def test_sprint_start_complete_metrics_and_carryover(client, auth):
    project = await _activate_project(client, auth)
    first_sprint = await client.post(
        f"{BASE}/sprints",
        headers=auth,
        json={
            "project_id": project["id"],
            "name": "Sprint 1",
            "start_date": (date.today() - timedelta(days=7)).isoformat(),
            "end_date": date.today().isoformat(),
        },
    )
    assert first_sprint.status_code == 201, first_sprint.text
    second_sprint = await client.post(
        f"{BASE}/sprints",
        headers=auth,
        json={
            "project_id": project["id"],
            "name": "Sprint 2",
            "start_date": date.today().isoformat(),
            "end_date": (date.today() + timedelta(days=7)).isoformat(),
        },
    )
    assert second_sprint.status_code == 201, second_sprint.text
    sprint_id = first_sprint.json()["id"]
    completed_item = await _create_work_item(
        client, auth, project["id"], "Sprint done", sprint_id=sprint_id
    )
    carried_item = await _create_work_item(
        client, auth, project["id"], "Sprint carryover", sprint_id=sprint_id
    )
    await _to_done(client, auth, completed_item["id"])
    started = await _transition(client, auth, f"{BASE}/sprints/{sprint_id}/start", "start")
    assert started["status"] == "active"
    metrics = await client.post(
        f"{BASE}/sprints/{sprint_id}/complete",
        headers=auth,
        json={"move_to_sprint_id": second_sprint.json()["id"], "comment": "wrap up"},
    )
    assert metrics.status_code == 200, metrics.text
    assert metrics.json()["throughput"] == 1
    assert metrics.json()["carryover"] == 1
    assert Decimal(metrics.json()["velocity"]) == Decimal("5")

    moved = await client.get(f"{BASE}/work-items/{carried_item['id']}", headers=auth)
    assert moved.json()["sprint_id"] == second_sprint.json()["id"]
    immutable = await client.post(
        f"{BASE}/sprints/{sprint_id}/complete", headers=auth, json={}
    )
    assert immutable.status_code == 409, immutable.text


@pytest.mark.asyncio
async def test_gantt_dependencies_cycle_critical_path_and_baseline(client, auth):
    start = date(2026, 11, 16)
    project = await _create_project(
        client,
        auth,
        start_date=start.isoformat(),
        end_date=(start + timedelta(days=30)).isoformat(),
    )
    first = await _create_work_item(
        client,
        auth,
        project["id"],
        "Design",
        start_date=start.isoformat(),
        due_date=(start + timedelta(days=2)).isoformat(),
    )
    second = await _create_work_item(
        client,
        auth,
        project["id"],
        "Build",
        start_date=start.isoformat(),
        due_date=(start + timedelta(days=2)).isoformat(),
    )
    dependency = await client.post(
        f"{BASE}/dependencies",
        headers=auth,
        json={
            "project_id": project["id"],
            "predecessor_id": first["id"],
            "successor_id": second["id"],
            "type": "FS",
            "lag_days": 2,
        },
    )
    assert dependency.status_code == 201, dependency.text
    confirmed = await _transition(
        client, auth, f"{BASE}/dependencies/{dependency.json()['id']}/transition", "confirm"
    )
    assert confirmed["status"] == "active"
    cycle = await client.post(
        f"{BASE}/dependencies",
        headers=auth,
        json={
            "project_id": project["id"],
            "predecessor_id": second["id"],
            "successor_id": first["id"],
            "type": "SS",
        },
    )
    assert cycle.status_code == 409, cycle.text

    gantt = await client.get(f"{BASE}/projects/{project['id']}/gantt", headers=auth)
    assert gantt.status_code == 200, gantt.text
    rows = {row["title"]: row for row in gantt.json()["tasks"]}
    assert rows["Build"]["scheduled_start"] == (start + timedelta(days=5)).isoformat()
    assert rows["Build"]["critical"] is True
    critical = await client.get(f"{BASE}/projects/{project['id']}/critical-path", headers=auth)
    assert critical.status_code == 200, critical.text

    baseline = await client.post(
        f"{BASE}/projects/{project['id']}/baselines",
        headers=auth,
        json={"name": f"Approved baseline {uuid4().hex[:8]}"},
    )
    assert baseline.status_code == 201, baseline.text
    assert baseline.json()["status"] == "approved"
    variance = await client.get(
        f"{BASE}/projects/{project['id']}/schedule-variance", headers=auth
    )
    assert variance.status_code == 200, variance.text
    assert any(row["entity_type"] == "work_item" for row in variance.json())


@pytest.mark.asyncio
async def test_billing_review_configured_tax_and_profitability(client, auth):
    project = await _activate_project(client, auth)
    work_item = await _create_work_item(client, auth, project["id"], "Billable work")
    await _create_time_entry(client, auth, work_item["id"])
    cost = await client.post(
        f"{BASE}/cost-entries",
        headers=auth,
        json={
            "project_id": project["id"],
            "cost_type": "labour",
            "amount": "50.00",
            "posted_at": date.today().isoformat(),
        },
    )
    assert cost.status_code == 201, cost.text
    preview = await client.get(
        f"{BASE}/billing/preview", headers=auth, params={"project_id": project["id"]}
    )
    assert preview.status_code == 200, preview.text
    assert Decimal(preview.json()["gross_amount"]) == Decimal("200")

    run = await client.post(
        f"{BASE}/billing-runs",
        headers=auth,
        json={
            "project_id": project["id"],
            "period": "2026-11",
            "billing_type": "time_and_material",
            "idempotency_key": uuid4().hex,
        },
    )
    assert run.status_code == 201, run.text
    run_id = run.json()["id"]
    missing_tax = await client.post(
        f"{BASE}/billing-runs/{run_id}/review",
        headers=auth,
        json={"tax_code": f"MISSING-{uuid4().hex[:6].upper()}"},
    )
    assert missing_tax.status_code == 422, missing_tax.text

    marker = uuid4().hex[:6].upper()
    tax_code = f"IGST-{marker}"
    account_ids = {}
    for component, account_type in (
        ("OUT-CGST", "liability"),
        ("OUT-SGST", "liability"),
        ("OUT-IGST", "liability"),
        ("IN-CGST", "asset"),
        ("IN-SGST", "asset"),
        ("IN-IGST", "asset"),
    ):
        account = await client.post(
            "/api/v1/finance/accounts",
            headers=auth,
            json={
                "code": f"PM-GST-{marker}-{component}",
                "name": f"PM GST {component} {marker}",
                "account_type": account_type,
            },
        )
        assert account.status_code == 201, account.text
        account_ids[component] = account.json()["id"]
    configured_tax = await client.post(
        "/api/v1/finance/tax/codes",
        headers=auth,
        json={
            "code": tax_code,
            "description": f"Integrated GST 18% {tax_code}",
            "cgst_rate": "9",
            "sgst_rate": "9",
            "igst_rate": "18",
            "can_claim_itc": True,
            "output_cgst_account_id": account_ids["OUT-CGST"],
            "output_sgst_account_id": account_ids["OUT-SGST"],
            "output_igst_account_id": account_ids["OUT-IGST"],
            "input_cgst_account_id": account_ids["IN-CGST"],
            "input_sgst_account_id": account_ids["IN-SGST"],
            "input_igst_account_id": account_ids["IN-IGST"],
        },
    )
    assert configured_tax.status_code == 201, configured_tax.text
    reviewed = await client.post(
        f"{BASE}/billing-runs/{run_id}/review", headers=auth, json={"tax_code": tax_code}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert Decimal(reviewed.json()["tax_amount"]) == Decimal("36.00")
    await _transition(client, auth, f"{BASE}/billing-runs/{run_id}/transition", "generate")
    await _transition(client, auth, f"{BASE}/billing-runs/{run_id}/transition", "approve")
    posted = await client.post(
        f"{BASE}/billing-runs/{run_id}/post", headers=auth, json={"tax_amount": "36.00"}
    )
    assert posted.status_code == 200, posted.text

    profitability = await client.get(
        f"{BASE}/projects/{project['id']}/profitability", headers=auth
    )
    assert profitability.status_code == 200, profitability.text
    summary = profitability.json()[0]
    assert Decimal(summary["billed"]) == Decimal("236")
    unbilled = await client.get(f"{BASE}/projects/{project['id']}/unbilled", headers=auth)
    assert unbilled.status_code == 200, unbilled.text
    assert unbilled.json()["lines"] == []
    costs = await client.get(f"{BASE}/projects/{project['id']}/costs", headers=auth)
    assert any(row["amount"] == "50.00" for row in costs.json())

    fixed = await _activate_project(client, auth, billing_type="fixed", contract_value="7500.00")
    fixed_preview = await client.get(
        f"{BASE}/billing/preview", headers=auth, params={"project_id": fixed["id"]}
    )
    assert fixed_preview.status_code == 200, fixed_preview.text
    assert fixed_preview.json()["lines"][0]["source_type"] == "fixed_fee"


@pytest.mark.asyncio
async def test_governance_and_status_update_reporting(client, auth):
    project = await _activate_project(client, auth)
    for endpoint, title in (
        ("risks", "Delivery risk"),
        ("issues", "Vendor issue"),
        ("change-requests", "Scope change"),
    ):
        created = await client.post(
            f"{BASE}/{endpoint}",
            headers=auth,
            json={"project_id": project["id"], "title": title, "status": "open"},
        )
        assert created.status_code == 201, created.text
    status_update = await client.post(
        f"{BASE}/status-updates",
        headers=auth,
        json={"project_id": project["id"], "period": "2026-W47", "status": "published"},
    )
    assert status_update.status_code == 201, status_update.text
    approval = await client.post(
        f"{BASE}/approvals",
        headers=auth,
        json={
            "entity_type": "project",
            "entity_id": project["id"],
            "approval_type": "intake",
            "status": "pending",
        },
    )
    assert approval.status_code == 201, approval.text

    governance = await client.get(
        f"{BASE}/reports/governance", headers=auth, params={"project_id": project["id"]}
    )
    assert governance.status_code == 200, governance.text
    assert governance.json()["open_risks"] == 1
    assert governance.json()["open_issues"] == 1
    assert governance.json()["status_updates"] == 1
    assert governance.json()["pending_approvals"] == 1


@pytest.mark.asyncio
async def test_automation_success_pause_unknown_action_and_idempotency(client, auth):
    project = await _activate_project(client, auth)
    me = await client.get("/api/v1/auth/me", headers=auth)
    admin_id = me.json()["id"]
    viewer = await _create_viewer(client, auth)
    rule = await client.post(
        f"{BASE}/automation-rules",
        headers=auth,
        json={
            "project_id": project["id"],
            "name": f"On done {uuid4().hex[:6]}",
            "trigger_json": {"event": "work_item.done"},
            "conditions_json": [{"field": "status", "op": "eq", "value": "done"}],
            "actions_json": [
                {"type": "set_health", "health": "amber"},
                {"type": "record_activity", "action": "automation.custom", "message": "done"},
                {"type": "create_comment", "body": "Automated comment"},
            ],
            "owner_id": admin_id,
            "status": "active",
        },
    )
    assert rule.status_code == 201, rule.text
    item = await _create_work_item(client, auth, project["id"], "Automated done")
    await _to_done(client, auth, item["id"])
    runs = await client.get(
        f"{BASE}/automation-runs", headers=auth, params={"trigger_id": item["id"]}
    )
    assert runs.status_code == 200, runs.text
    assert any(row["status"] == "success" for row in runs.json()["items"]), runs.json()
    refreshed = await client.get(f"{BASE}/{project['id']}", headers=auth)
    assert refreshed.json()["health"] == "amber"
    activities = await client.get(
        f"{BASE}/activities",
        headers=auth,
        params={"entity_type": "work_item", "entity_id": item["id"], "action": "automation.rule_executed"},
    )
    assert activities.json()["items"]

    paused_rule = await client.post(
        f"{BASE}/automation-rules",
        headers=auth,
        json={
            "name": f"Paused {uuid4().hex[:6]}",
            "trigger_json": {"event": "work_item.done"},
            "actions_json": [{"type": "set_health", "health": "red"}],
            "owner_id": viewer["id"],
            "status": "active",
        },
    )
    assert paused_rule.status_code == 201, paused_rule.text
    failed_rule = await client.post(
        f"{BASE}/automation-rules",
        headers=auth,
        json={
            "name": f"Failed {uuid4().hex[:6]}",
            "trigger_json": {"event": "work_item.done"},
            "actions_json": [{"type": "delete_project"}],
            "owner_id": admin_id,
            "status": "active",
        },
    )
    assert failed_rule.status_code == 201, failed_rule.text
    second_item = await _create_work_item(client, auth, project["id"], "Automated fail")
    manual_runs = await client.post(
        f"{BASE}/automation/runs",
        headers={**auth, "Idempotency-Key": uuid4().hex},
        json={"trigger_entity": "work_item.done", "trigger_id": second_item["id"]},
    )
    assert manual_runs.status_code == 201, manual_runs.text
    statuses = {row["status"] for row in manual_runs.json()}
    assert "paused" in statuses
    assert "failed" in statuses


@pytest.mark.asyncio
async def test_ai_signals_refresh_review_and_report_queue(client, auth):
    project = await _create_project(client, auth)
    await _create_work_item(
        client,
        auth,
        project["id"],
        "Overdue work",
        due_date=(date.today() - timedelta(days=3)).isoformat(),
    )
    refreshed = await client.post(
        f"{BASE}/ai/signals/refresh", headers=auth, params={"project_id": project["id"]}
    )
    assert refreshed.status_code == 200, refreshed.text
    delay = next(row for row in refreshed.json() if row["signal_type"] == "delay_risk")
    assert delay["features_json"]["overdue_tasks"] == 1
    reviewed = await client.post(
        f"{BASE}/ai/signals/{delay['id']}/review", headers=auth, json={"comment": "seen"}
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["review_status"] == "reviewed"

    queue = await client.get(
        f"{BASE}/reports/ai-review-queue", headers=auth, params={"project_id": project["id"]}
    )
    assert queue.status_code == 200, queue.text
    assert any(row["id"] == delay["id"] for row in queue.json()["rows"])


@pytest.mark.asyncio
async def test_import_stage_approve_commit_rollback_and_notifications(client, auth):
    project = await _activate_project(client, auth)
    marker = uuid4().hex[:8]
    staged = await client.post(
        f"{BASE}/imports",
        headers=auth,
        json={
            "provider": "csv",
            "mapping": {"title": "summary", "project_id": "proj"},
            "rows": [
                {"external_id": f"valid-{marker}", "summary": "Imported work", "proj": project["id"]},
                {"external_id": f"invalid-{marker}", "summary": ""},
            ],
        },
    )
    assert staged.status_code == 201, staged.text
    batch_id = staged.json()["id"]
    approved = await client.post(
        f"{BASE}/imports/{batch_id}/approve",
        headers=auth,
        json={
            "mapping": {"title": "summary", "project_id": "proj"},
            "comment": "looks good",
        },
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["rows_imported"] == 1
    assert approved.json()["rows_failed"] == 1
    committed = await client.post(f"{BASE}/imports/{batch_id}/commit", headers=auth, json={})
    assert committed.status_code == 200, committed.text
    imported = await client.get(
        f"{BASE}/work-items", headers=auth, params={"project_id": project["id"], "q": "Imported work"}
    )
    assert imported.status_code == 200, imported.text
    assert any(row["title"] == "Imported work" for row in imported.json()["items"])
    rolled_back = await client.post(f"{BASE}/imports/{batch_id}/rollback", headers=auth, json={})
    assert rolled_back.status_code == 200, rolled_back.text

    notification = await client.post(
        f"{BASE}/notifications",
        headers=auth,
        json={
            "channel": "whatsapp",
            "to": "+911234567890",
            "template": "status_update",
            "body": "Status published",
            "entity_type": "project",
            "entity_id": project["id"],
            "consent_reference": f"consent-{marker}",
        },
    )
    assert notification.status_code == 201, notification.text

    intake = await client.post(
        f"{BASE}/intake",
        headers=auth,
        json={
            "title": f"New intake {marker}",
            "objective": "Evaluate a new customer request",
            "sponsor": "Customer",
            "budget_range": "5000.00",
        },
    )
    assert intake.status_code == 201, intake.text
    decided = await client.post(
        f"{BASE}/intake/{intake.json()['id']}/decide",
        headers=auth,
        json={"decision": "approve", "comment": "approved"},
    )
    assert decided.status_code == 200, decided.text
    assert decided.json()["name"] == f"New intake {marker}"
