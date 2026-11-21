import pytest


@pytest.mark.asyncio
async def test_secret_is_masked_and_rotation_has_window(client, auth):
    key = "ocr.api_key"
    write = await client.put(
        f"/api/v1/settings/secrets/{key}",
        headers=auth,
        json={"value": "sk_live_abcdefghijkl", "reason": "test secret"},
    )
    assert write.status_code == 200, write.text
    assert "abcdefghijkl" not in write.text

    listed = await client.get("/api/v1/settings/secrets", headers=auth)
    assert listed.status_code == 200
    row = next(item for item in listed.json() if item["key"] == key)
    assert "ciphertext" not in row
    assert "sk_live" not in row["mask"]

    rotated = await client.post(
        f"/api/v1/settings/secrets/{key}/rotate",
        headers=auth,
        json={"value": "sk_live_zyxwvutsrqpo", "window_hours": 24},
    )
    assert rotated.status_code == 200

    rollback = await client.post(f"/api/v1/settings/secrets/{key}/rollback", headers=auth)
    assert rollback.status_code == 200


@pytest.mark.asyncio
async def test_unregistered_secret_key_is_rejected(client, auth):
    response = await client.put(
        "/api/v1/settings/secrets/not.registered.api_key",
        headers=auth,
        json={"value": "anything", "reason": "test"},
    )
    assert response.status_code == 422


def test_key_ring_decrypts_prior_version_and_rewraps(monkeypatch):
    from app.core.config import settings
    from app.core.crypto import decrypt, encrypt, rewrap

    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY", "22" * 32)
    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY_VERSION", 2)
    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY_PREVIOUS", "11" * 32)
    monkeypatch.setattr(settings, "SETTINGS_ENCRYPTION_KEY_VERSION_PREVIOUS", 1)

    ciphertext, nonce, version = encrypt("legacy-value", key_version=1)
    assert version == 1
    assert decrypt(ciphertext, nonce, version) == "legacy-value"

    new_ciphertext, new_nonce, new_version = rewrap(ciphertext, nonce, 1, 2)
    assert new_version == 2
    assert decrypt(new_ciphertext, new_nonce, new_version) == "legacy-value"


@pytest.mark.asyncio
async def test_rotation_verify_outbound_and_service_rewrap(client, auth):
    from sqlalchemy import select

    from app.core.config import settings
    from app.db.session import AsyncSessionLocal
    from app.modules.identity.models import User
    from app.modules.settings.secrets import secrets_service

    key = "gst_portal.client_secret"
    old_value = "old-credential-value"
    new_value = "new-credential-value"
    written = await client.put(
        f"/api/v1/settings/secrets/{key}",
        headers=auth,
        json={"value": old_value, "reason": "initial setup"},
    )
    assert written.status_code == 200, written.text
    rotated = await client.post(
        f"/api/v1/settings/secrets/{key}/rotate",
        headers=auth,
        json={"value": new_value, "window_hours": 24},
    )
    assert rotated.status_code == 200, rotated.text

    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        assert user is not None
        assert await secrets_service.get_plaintext(
            db, tenant_id=user.tenant_id, key=key, intent="verify"
        ) == old_value
        assert await secrets_service.get_plaintext(
            db, tenant_id=user.tenant_id, key=key, intent="outbound"
        ) == new_value
        result = await secrets_service.rewrap_secret(
            db, user, key=key, key_version=settings.SETTINGS_ENCRYPTION_KEY_VERSION
        )
        assert result["key"] == key
        assert result["mask"]
        assert await secrets_service.get_plaintext(
            db, tenant_id=user.tenant_id, key=key, intent="outbound"
        ) == new_value
