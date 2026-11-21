from uuid import uuid4

import pytest

MENU_ACCESS_PASSWORD = "Quartz!Maple#R8v"


@pytest.mark.asyncio
async def test_superadmin_user_list_defaults_to_current_workspace(client, auth):
    marker = uuid4().hex[:8]
    email = f"tenant-scope-{marker}@example.com"
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": MENU_ACCESS_PASSWORD,
            "full_name": "Tenant Scope User",
            "tenant_name": f"Tenant Scope {marker}",
        },
    )
    assert registered.status_code == 201, registered.text
    other_tenant_id = registered.json()["user"]["tenant_id"]

    scoped = await client.get("/api/v1/users", headers=auth, params={"q": email})
    assert scoped.status_code == 200, scoped.text
    assert scoped.json()["total"] == 0

    selected = await client.get(
        "/api/v1/users",
        headers=auth,
        params={"tenant_id": other_tenant_id, "q": email},
    )
    assert selected.status_code == 200, selected.text
    assert selected.json()["total"] == 1
    assert selected.json()["items"][0]["tenant_name"] == f"Tenant Scope {marker}"

    all_tenants = await client.get(
        "/api/v1/users",
        headers=auth,
        params={"tenant_scope": "all", "q": email},
    )
    assert all_tenants.status_code == 200, all_tenants.text
    assert all_tenants.json()["total"] == 1


@pytest.mark.asyncio
async def test_tenant_admin_cannot_spoof_another_workspace(client):
    marker = uuid4().hex[:8]
    email = f"spoof-{marker}@example.com"
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": MENU_ACCESS_PASSWORD,
            "full_name": "Tenant Admin",
            "tenant_name": f"Spoof Tenant {marker}",
        },
    )
    assert registered.status_code == 201, registered.text
    headers = {
        "Authorization": f"Bearer {registered.json()['access_token']}",
    }
    other = await client.get(
        "/api/v1/users",
        headers=headers,
        params={"tenant_id": "00000000-0000-0000-0000-000000000000", "q": "admin@hertex.dev"},
    )
    assert other.status_code == 200, other.text
    assert other.json()["total"] == 0


@pytest.mark.asyncio
async def test_superadmin_can_create_user_in_selected_workspace(client, auth):
    marker = uuid4().hex[:8]
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"owner-{marker}@example.com",
            "password": MENU_ACCESS_PASSWORD,
            "full_name": "Workspace Owner",
            "tenant_name": f"Create Target {marker}",
        },
    )
    assert registered.status_code == 201, registered.text
    target_tenant_id = registered.json()["user"]["tenant_id"]

    created = await client.post(
        "/api/v1/users",
        headers=auth,
        json={
            "email": f"created-{marker}@example.com",
            "password": MENU_ACCESS_PASSWORD,
            "full_name": "Created Team Member",
            "tenant_id": target_tenant_id,
            "is_active": True,
        },
    )
    assert created.status_code == 201, created.text
    assert created.json()["tenant_id"] == target_tenant_id


@pytest.mark.asyncio
async def test_tenant_admin_cannot_create_user_in_another_workspace(client):
    marker = uuid4().hex[:8]
    registered = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"creator-{marker}@example.com",
            "password": MENU_ACCESS_PASSWORD,
            "full_name": "Workspace Creator",
            "tenant_name": f"Create Source {marker}",
        },
    )
    assert registered.status_code == 201, registered.text
    headers = {"Authorization": f"Bearer {registered.json()['access_token']}"}

    denied = await client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "email": f"denied-{marker}@example.com",
            "password": MENU_ACCESS_PASSWORD,
            "full_name": "Denied Team Member",
            "tenant_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert denied.status_code == 403, denied.text
