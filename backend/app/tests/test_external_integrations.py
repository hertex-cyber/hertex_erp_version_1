from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.exceptions import register_exception_handlers
from app.db.session import AsyncSessionLocal
from app.modules.identity.models import AuditLog
from app.modules.integrations.external_credentials import PROVIDER_KEYS, secret_key
from app.modules.integrations.external_router import router as external_router


@pytest_asyncio.fixture
async def external_client(auth):
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(external_router, prefix="/api/v1")
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://hertex.test"
    ) as async_client:
        yield async_client, auth


@pytest.mark.asyncio
async def test_provider_list_is_masked_and_unconfigured_adapters_degrade(external_client):
    client, auth = external_client

    response = await client.get("/api/v1/integrations/external/providers", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert {item["provider"] for item in body} == set(PROVIDER_KEYS)
    assert all(item["is_configured"] is False for item in body)
    assert all(item["live_calls_enabled"] is False for item in body)
    assert all("ciphertext" not in item for item in body)

    gst = next(item for item in body if item["provider"] == "gst_portal")
    assert {credential["field"] for credential in gst["credentials"]} == {
        "client_id",
        "client_secret",
    }
    assert all(credential["mask"] == "" for credential in gst["credentials"])

    check = await client.post(
        "/api/v1/integrations/external/providers/gst_portal/test-connection",
        headers=auth,
    )
    assert check.status_code == 200, check.text
    payload = check.json()
    assert payload["status"] == "degraded_simulated"
    assert payload["is_configured"] is False
    assert payload["checked_fields"] == ["client_id", "client_secret"]
    assert "client_id" in payload["detail"]


@pytest.mark.asyncio
async def test_credentials_replace_rotate_commit_rollback_never_expose_plaintext(external_client):
    client, auth = external_client
    marker = uuid4().hex[:10]
    old_client_id = f"oldid-{marker}"
    new_client_id = f"newid-{marker}"
    client_secret = f"secret-{marker}"
    rotated_secret = f"rotated-{marker}"
    rollback_secret = f"rollback-{marker}"

    write = await client.put(
        "/api/v1/integrations/external/providers/e_invoice_portal/credentials",
        headers=auth,
        json={
            "credentials": {
                "client_id": old_client_id,
                "client_secret": client_secret,
            },
            "reason": "initial setup",
        },
    )
    assert write.status_code == 200, write.text
    assert old_client_id not in write.text
    assert client_secret not in write.text
    written = write.json()
    assert written["is_configured"] is True
    assert {
        credential["field"] for credential in written["credentials"] if credential["configured"]
    } == {"client_id", "client_secret"}

    replace = await client.put(
        "/api/v1/integrations/external/providers/e_invoice_portal/credentials",
        headers=auth,
        json={"credentials": {"client_id": new_client_id}, "reason": "replace"},
    )
    assert replace.status_code == 200, replace.text
    assert old_client_id not in replace.text
    assert new_client_id not in replace.text
    assert replace.json()["is_configured"] is True

    rotate = await client.post(
        "/api/v1/integrations/external/providers/e_invoice_portal/credentials/client_secret/rotate",
        headers=auth,
        json={"value": rotated_secret, "window_hours": 24},
    )
    assert rotate.status_code == 200, rotate.text
    assert rotated_secret not in rotate.text
    assert rotate.json()["status"] == "pending"
    assert rotate.json()["rotation_ends_at"] is not None

    commit = await client.post(
        "/api/v1/integrations/external/providers/e_invoice_portal/credentials/client_secret/commit",
        headers=auth,
    )
    assert commit.status_code == 200, commit.text
    assert commit.json()["status"] == "active"
    assert commit.json()["rolled_back"] is False

    second_rotate = await client.post(
        "/api/v1/integrations/external/providers/e_invoice_portal/credentials/client_secret/rotate",
        headers=auth,
        json={"value": rollback_secret, "window_hours": 24},
    )
    assert second_rotate.status_code == 200, second_rotate.text
    assert rollback_secret not in second_rotate.text

    rollback = await client.post(
        "/api/v1/integrations/external/providers/e_invoice_portal/credentials/client_secret/rollback",
        headers=auth,
    )
    assert rollback.status_code == 200, rollback.text
    assert rollback.json()["status"] == "active"
    assert rollback.json()["rolled_back"] is True

    check = await client.post(
        "/api/v1/integrations/external/providers/e_invoice_portal/test-connection",
        headers=auth,
    )
    assert check.status_code == 200, check.text
    payload = check.json()
    assert payload["status"] == "simulated"
    assert payload["is_configured"] is True
    assert client_secret not in check.text
    assert rotated_secret not in check.text
    assert rollback_secret not in check.text

    listed = await client.get(
        "/api/v1/integrations/external/providers/e_invoice_portal", headers=auth
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["is_configured"] is True
    assert client_secret not in listed.text
    assert rotated_secret not in listed.text

    async with AsyncSessionLocal() as db:
        log = await db.scalar(
            select(AuditLog)
            .where(AuditLog.action == "integrations.external.test_connection")
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
    assert log is not None
    assert client_secret not in str(log.changes)
    assert rotated_secret not in str(log.changes)


@pytest.mark.asyncio
async def test_unknown_provider_field_and_invalid_value_are_rejected(external_client):
    client, auth = external_client
    assert secret_key("ocr", "api_key") == "integrations.external.ocr.api_key"

    unknown = await client.get(
        "/api/v1/integrations/external/providers/not_a_provider", headers=auth
    )
    assert unknown.status_code == 422
    assert unknown.json()["code"] == "integrations.external.unknown_provider"

    unknown_field = await client.put(
        "/api/v1/integrations/external/providers/gst_portal/credentials",
        headers=auth,
        json={"credentials": {"bogus": "value"}},
    )
    assert unknown_field.status_code == 422
    assert unknown_field.json()["code"] == "integrations.external.unknown_field"

    empty = await client.put(
        "/api/v1/integrations/external/providers/ocr/credentials",
        headers=auth,
        json={"credentials": {"api_key": ""}},
    )
    assert empty.status_code == 422
    assert empty.json()["code"] == "integrations.external.invalid_credential"

    too_long = "x" * 5000
    oversized = await client.put(
        "/api/v1/integrations/external/providers/ocr/credentials",
        headers=auth,
        json={"credentials": {"api_key": too_long}},
    )
    assert oversized.status_code == 422
    assert oversized.json()["code"] == "integrations.external.invalid_credential"
    assert too_long not in oversized.text
