from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.exceptions import ValidationError
from app.db.session import AsyncSessionLocal
from app.modules.identity.models import Permission, Role, User
from app.modules.settings.models import SettingChange
from app.modules.settings.registry import BY_KEY
from app.modules.settings.service import SettingsService, settings_service


async def _reporter(client, auth):
    marker = uuid4().hex
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"settings-reporter-{marker}@example.com",
            "password": "Quartz!Maple#R8v",
            "full_name": "Settings Reporter",
            "tenant_name": f"Settings Reporter {marker}",
        },
    )
    assert response.status_code == 201, response.text
    email = response.json()["email"] if "email" in response.json() else f"settings-reporter-{marker}@example.com"
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        reporter = await db.scalar(select(User).where(User.email == email))
        assert admin is not None and reporter is not None
        codes = ("settings.setting.read", "settings.setting.update", "system.settings.manage")
        permissions = list(
            (await db.scalars(select(Permission).where(Permission.code.in_(codes)))).all()
        )
        assert len(permissions) == len(codes)
        reporter.tenant_id = admin.tenant_id
        reporter.is_superuser = False
        reporter.roles.clear()
        role = Role(
            tenant_id=admin.tenant_id,
            name=f"Settings Reporter {marker}",
            slug=f"settings-reporter-{marker}",
            permissions=permissions,
        )
        reporter.roles.append(role)
        db.add(role)
        await db.commit()
    return {"Authorization": f"Bearer {response.json()['access_token']}"}, email


@pytest.mark.asyncio
async def test_critical_set_requires_reason(client, auth):
    no_reason = await client.put(
        "/api/v1/settings/values/finance.invoice.rounding",
        headers=auth,
        json={"value": "line", "reason": "   "},
    )
    assert no_reason.status_code == 422
    assert no_reason.json()["code"] == "settings.reason_required"

    accepted = await client.put(
        "/api/v1/settings/values/finance.invoice.rounding",
        headers=auth,
        json={"value": "line", "reason": "GST rounding review"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["applied"] is True


@pytest.mark.asyncio
async def test_critical_unset_requires_reason_and_approval(client, auth, approver_auth):
    reporter, _ = await _reporter(client, auth)
    seeded = await client.put(
        "/api/v1/settings/values/finance.tax.override_allowed",
        headers=auth,
        json={"value": True, "reason": "Enable controlled override"},
    )
    assert seeded.status_code == 200, seeded.text

    no_reason = await client.delete(
        "/api/v1/settings/values/finance.tax.override_allowed", headers=reporter
    )
    assert no_reason.status_code == 422

    pending = await client.delete(
        "/api/v1/settings/values/finance.tax.override_allowed",
        headers=reporter,
        params={"reason": "Remove temporary override"},
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()["approval_state"] == "pending"

    still_set = await client.get(
        "/api/v1/settings/values/finance.tax.override_allowed", headers=auth
    )
    assert still_set.json()["value"] is True

    approved = await client.post(
        f"/api/v1/settings/changes/{pending.json()['id']}/approve", headers=approver_auth
    )
    assert approved.status_code == 200, approved.text

    reverted = await client.get(
        "/api/v1/settings/values/finance.tax.override_allowed", headers=auth
    )
    assert reverted.json()["value"] is False


@pytest.mark.asyncio
async def test_self_approval_is_blocked_for_non_superuser(client, auth, approver_auth):
    reporter, _ = await _reporter(client, auth)
    pending = await client.put(
        "/api/v1/settings/values/finance.journal.manual_allowed",
        headers=reporter,
        json={"value": False, "reason": "Restrict manual journals"},
    )
    assert pending.status_code == 200, pending.text
    assert pending.json()["approval_state"] == "pending"

    self_approve = await client.post(
        f"/api/v1/settings/changes/{pending.json()['id']}/approve", headers=reporter
    )
    assert self_approve.status_code == 403

    approved = await client.post(
        f"/api/v1/settings/changes/{pending.json()['id']}/approve", headers=approver_auth
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["approval_state"] == "approved"


@pytest.mark.asyncio
async def test_approve_revalidates_change_before_applying(client, auth):
    _, reporter_email = await _reporter(client, auth)
    cases = (
        ("finance.invoice.due_days", 999, "tenant", "reasonable"),
        ("security.session.timeout_minutes", 30, "tenant", "reasonable"),
        ("finance.invoice.due_days", 30, "user", "reasonable"),
        ("finance.invoice.rounding", "line", "tenant", "  "),
    )
    for key, new_value, scope, reason in cases:
        async with AsyncSessionLocal() as db:
            admin = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
            reporter = await db.scalar(select(User).where(User.email == reporter_email))
            assert admin is not None and reporter is not None
            change = SettingChange(
                tenant_id=admin.tenant_id,
                key=key,
                scope_type=scope,
                old_value=None,
                new_value=new_value,
                change_type="set",
                reason=reason,
                actor_id=reporter.id,
                actor_email=reporter.email,
                approval_state="pending",
            )
            db.add(change)
            await db.flush()
            with pytest.raises(ValidationError):
                await settings_service.approve(db, admin, change.id, accept=True)
            await db.rollback()


@pytest.mark.asyncio
async def test_deploy_only_keys_cannot_be_written(client, auth):
    response = await client.put(
        "/api/v1/settings/values/security.session.timeout_minutes",
        headers=auth,
        json={"value": 30, "reason": "platform owns this key"},
    )
    assert response.status_code == 422
    assert response.json()["code"] == "settings.deploy_only"


@pytest.mark.asyncio
async def test_env_precedence_and_declared_scope_precedence(client, auth, monkeypatch):
    from app.modules.settings.registry import get_descriptor

    seeded = await client.put(
        "/api/v1/settings/values/finance.invoice.due_days",
        headers=auth,
        json={"value": 30},
    )
    assert seeded.status_code == 200, seeded.text

    descriptor = get_descriptor("finance.invoice.due_days")
    assert descriptor is not None
    monkeypatch.setitem(
        BY_KEY, "finance.invoice.due_days", replace(descriptor, env_var="HERTEX_TEST_DUE_DAYS")
    )
    monkeypatch.setenv("HERTEX_TEST_DUE_DAYS", "45")

    async with AsyncSessionLocal() as db:
        admin = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        assert admin is not None
        tenant_id = admin.tenant_id
        service = SettingsService()
        effective = await service.resolve_all(db, tenant_id=tenant_id)
        provenance = await service.provenance(
            db, tenant_id=tenant_id, keys=["finance.invoice.due_days"]
        )
    assert effective["finance.invoice.due_days"] == 45
    assert provenance[0]["effective_source"] == "env"

    timezone_descriptor = get_descriptor("company.locale.timezone")
    assert timezone_descriptor is not None
    monkeypatch.setitem(
        BY_KEY,
        "company.locale.timezone",
        replace(timezone_descriptor, scopes=("tenant", "branch", "user")),
    )
    branch_id = uuid4()
    for scope, scope_id, value in (
        ("tenant", None, "Asia/Kolkata"),
        ("branch", branch_id, "Asia/Dubai"),
        ("user", admin.id, "Asia/Tokyo"),
    ):
        written = await client.put(
            "/api/v1/settings/values/company.locale.timezone",
            headers=auth,
            json={"value": value, "scope": scope, "scope_id": str(scope_id) if scope_id else None},
        )
        assert written.status_code == 200, written.text

    async with AsyncSessionLocal() as db:
        service = SettingsService()
        effective = await service.resolve_all(
            db, tenant_id=tenant_id, branch_id=branch_id, user_id=admin.id
        )
    assert effective["company.locale.timezone"] == "Asia/Kolkata"

    monkeypatch.setitem(
        BY_KEY,
        "company.locale.timezone",
        replace(timezone_descriptor, scopes=("user", "branch", "tenant")),
    )
    async with AsyncSessionLocal() as db:
        service = SettingsService()
        effective = await service.resolve_all(
            db, tenant_id=tenant_id, branch_id=branch_id, user_id=admin.id
        )
    assert effective["company.locale.timezone"] == "Asia/Tokyo"
