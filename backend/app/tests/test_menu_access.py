from uuid import uuid4

import pytest

MENU_KEYS = {
    "dashboard",
    "assistant",
    "crm",
    "sales",
    "pos",
    "inventory",
    "warehouse",
    "procurement",
    "finance",
    "hr",
    "projects",
    "support",
    "marketing",
    "settings",
}


@pytest.mark.asyncio
async def test_menu_catalog_and_feature_flags_are_exposed(client, auth):
    catalog = await client.get("/api/v1/roles/menu/catalog", headers=auth)
    assert catalog.status_code == 200
    assert {item["key"] for item in catalog.json()} == MENU_KEYS

    response = await client.get("/api/v1/auth/permissions", headers=auth)
    assert response.status_code == 200
    body = response.json()
    assert body["menus"] == ["*"]
    for key in (
        "features.module.projects.enabled",
        "features.module.pos.enabled",
        "features.module.marketing.enabled",
        "features.module.support.enabled",
    ):
        assert key in body["feature_flags"]
        assert isinstance(body["feature_flags"][key], bool)


@pytest.mark.asyncio
async def test_builtin_roles_have_menu_templates(client, auth):
    response = await client.get("/api/v1/roles", headers=auth)
    assert response.status_code == 200
    roles = {role["slug"]: role for role in response.json()}
    assert set(roles["sales"]["menu_keys"]) == {"dashboard", "assistant", "crm", "sales"}
    assert set(roles["team_member"]["menu_keys"]) == {"dashboard", "assistant", "projects"}
    assert roles["superadmin"]["menu_keys"] == ["*"]


@pytest.mark.asyncio
async def test_custom_role_menu_keys_drive_effective_menus(client, auth):
    marker = uuid4().hex
    catalog = await client.get("/api/v1/roles/permissions/catalog", headers=auth)
    permission = next(item for item in catalog.json() if item["code"] == "crm.company.read")

    created = await client.post(
        "/api/v1/roles",
        headers=auth,
        json={
            "name": f"CRM only {marker[:6]}",
            "slug": f"crm-only-{marker[:8]}",
            "menu_keys": ["crm"],
            "permission_ids": [permission["id"]],
        },
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["menu_keys"] == ["crm"]

    email = f"crm-only-{marker}@example.com"
    password = "Quartz!Maple#R8v"
    user = await client.post(
        "/api/v1/users",
        headers=auth,
        json={
            "email": email,
            "password": password,
            "full_name": "CRM Only User",
            "role_ids": [role["id"]],
        },
    )
    assert user.status_code == 201, user.text

    login = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = await client.get("/api/v1/auth/permissions", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["menus"] == ["crm"]
    assert "crm.company.read" in body["permissions"]
    assert "finance.report.read" not in body["permissions"]


@pytest.mark.asyncio
async def test_unknown_menu_keys_are_rejected(client, auth):
    response = await client.post(
        "/api/v1/roles",
        headers=auth,
        json={
            "name": "Bad menus",
            "slug": f"bad-menus-{uuid4().hex[:8]}",
            "menu_keys": ["not-a-menu"],
        },
    )
    assert response.status_code == 422
