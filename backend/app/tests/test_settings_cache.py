import pytest
from sqlalchemy import select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.modules.identity.models import User
from app.modules.settings.service import SettingsService


def test_cache_ttl_comes_from_config(monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_CACHE_TTL_SECONDS", 7)
    service = SettingsService()
    assert service._cache_ttl == 7.0


@pytest.mark.asyncio
async def test_cache_is_version_invalidated(client, auth):
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        assert user is not None
        tenant_id = user.tenant_id

    service = SettingsService()
    async with AsyncSessionLocal() as db:
        initial = await service.resolve_all(db, tenant_id=tenant_id)
        initial_value = initial["finance.invoice.due_days"]
        assert isinstance(initial_value, int)
        cache_keys = list(service._cache)
        assert len(cache_keys) == 1
        initial_version = service._cache[cache_keys[0]][0]

    new_value = initial_value + 10
    response = await client.put(
        "/api/v1/settings/values/finance.invoice.due_days",
        headers=auth,
        json={"value": new_value},
    )
    assert response.status_code == 200, response.text

    async with AsyncSessionLocal() as db:
        updated = await service.resolve_all(db, tenant_id=tenant_id)
        assert updated["finance.invoice.due_days"] == new_value
        assert service._cache[cache_keys[0]][0] == initial_version + 1
