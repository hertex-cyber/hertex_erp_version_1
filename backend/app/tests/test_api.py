import time
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.security import totp_code


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"


@pytest.mark.asyncio
async def test_login_returns_tokens_and_identity(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hertex.dev", "password": "Admin@12345"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["token_type"] == "bearer"
    assert body["user"]["email"] == "admin@hertex.dev"


@pytest.mark.asyncio
async def test_login_rejects_bad_password(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hertex.dev", "password": "wrong-password"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_analytics_requires_authentication(client):
    response = await client.get("/api/v1/analytics/dashboard")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_returns_operating_snapshot(client, auth):
    response = await client.get("/api/v1/analytics/dashboard", headers=auth)
    assert response.status_code == 200
    body = response.json()
    kpis = body["kpis"]
    for key in ("revenue", "cash_collected", "receivables", "stock_value", "lead_count"):
        assert key in kpis
    assert isinstance(body["revenue_trend"], list)
    assert isinstance(body["recent_activity"], list)


@pytest.mark.asyncio
async def test_stock_levels_are_valued(client, auth):
    response = await client.get("/api/v1/inventory/stock-levels", headers=auth)
    assert response.status_code == 200
    rows = response.json()
    assert rows
    row = rows[0]
    for key in ("sku", "name", "on_hand", "stock_value", "below_reorder"):
        assert key in row


@pytest.mark.asyncio
async def test_create_and_search_lead(client, auth):
    created = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={"name": "Pytest Prospect", "email": "prospect@example.com", "source": "web"},
    )
    assert created.status_code == 201, created.text
    lead = created.json()
    assert lead["name"] == "Pytest Prospect"

    found = await client.get("/api/v1/crm/leads", headers=auth, params={"q": "Pytest Prospect"})
    assert found.status_code == 200
    assert any(row["id"] == lead["id"] for row in found.json()["items"])


@pytest.mark.asyncio
async def test_pos_checkout_creates_sale(client, auth):
    products = await client.get("/api/v1/inventory/products", headers=auth, params={"size": 1})
    assert products.status_code == 200
    product = products.json()["items"][0]

    session = await client.post(
        "/api/v1/pos/sessions",
        headers=auth,
        json={"terminal_name": "Pytest counter", "opening_cash": 250},
    )
    assert session.status_code == 201, session.text

    checkout = await client.post(
        "/api/v1/pos/checkout",
        headers=auth,
        json={
            "session_id": session.json()["id"],
            "payment_method": "cash",
            "lines": [{"product_id": product["id"], "quantity": 1}],
        },
    )
    assert checkout.status_code == 201, checkout.text
    sale = checkout.json()
    assert sale["status"] == "completed"
    assert float(sale["total"]) > 0

    closed = await client.post(
        f"/api/v1/pos/sessions/{session.json()['id']}/close",
        headers=auth,
        params={"closing_cash": 1000},
    )
    assert closed.status_code == 200


@pytest.mark.asyncio
async def test_assistant_answers_revenue_question(client, auth):
    response = await client.post(
        "/api/v1/ai/ask",
        headers=auth,
        json={"question": "How is revenue trending?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["intent"] == "revenue"
    assert body["answer"]
    assert body["suggestions"]


async def _create_auth_user(client, auth, label):
    email = f"{label}-{uuid4().hex[:8]}@example.com"
    password = "Str0ng!Pass-2026"
    created = await client.post(
        "/api/v1/users",
        headers=auth,
        json={"email": email, "password": password, "full_name": "Auth Test User"},
    )
    assert created.status_code == 201, created.text
    return email, password, created.json()["id"]


@pytest.mark.asyncio
async def test_weak_passwords_are_rejected(client):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "tenant_name": "Weak Pass Co",
            "full_name": "Weak User",
            "email": f"weak-{uuid4().hex[:8]}@example.com",
            "password": "short1!",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_sets_refresh_cookie_and_csrf(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hertex.dev", "password": "Admin@12345"},
    )
    assert response.status_code == 200
    assert client.cookies.get("hertex_refresh")
    assert client.cookies.get("hertex_csrf")


@pytest.mark.asyncio
async def test_cookie_refresh_requires_csrf_header(client):
    await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hertex.dev", "password": "Admin@12345"},
    )
    rejected = await client.post("/api/v1/auth/refresh", json={})
    assert rejected.status_code == 401

    csrf = client.cookies.get("hertex_csrf")
    accepted = await client.post(
        "/api/v1/auth/refresh", json={}, headers={"x-csrf-token": csrf}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["access_token"]


@pytest.mark.asyncio
async def test_failed_logins_lock_account(client, auth):
    email, password, _ = await _create_auth_user(client, auth, "lockout")
    for _ in range(settings.MAX_FAILED_LOGINS):
        rejected = await client.post(
            "/api/v1/auth/login", json={"email": email, "password": "wrong-password"}
        )
        assert rejected.status_code == 401

    locked = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert locked.status_code == 401
    assert "locked" in locked.json()["detail"].lower()


@pytest.mark.asyncio
async def test_mfa_challenge_and_recovery_code(client, auth):
    email, password, _ = await _create_auth_user(client, auth, "mfa")
    login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    setup = await client.post("/api/v1/auth/mfa/setup", headers=headers)
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    recovery_codes = setup.json()["recovery_codes"]

    enabled = await client.post(
        "/api/v1/auth/mfa/enable",
        headers=headers,
        json={"code": totp_code(secret), "recovery_codes": recovery_codes},
    )
    assert enabled.status_code == 200, enabled.text

    challenged = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert challenged.status_code == 200
    challenge_token = challenged.json()["challenge_token"]
    verified = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"challenge_token": challenge_token, "code": totp_code(secret, int(time.time()) // 30 + 1)},
    )
    assert verified.status_code == 200, verified.text

    challenged = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert challenged.status_code == 200
    recovered = await client.post(
        "/api/v1/auth/mfa/verify",
        json={"challenge_token": challenged.json()["challenge_token"], "recovery_code": recovery_codes[0]},
    )
    assert recovered.status_code == 200, recovered.text


@pytest.mark.asyncio
async def test_revoking_session_invalidates_access_token(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"email": "admin@hertex.dev", "password": "Admin@12345"},
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    sessions = await client.get("/api/v1/auth/sessions", headers=headers)
    assert sessions.status_code == 200
    current = next(row for row in sessions.json() if row["current"])

    revoked = await client.delete(f"/api/v1/auth/sessions/{current['id']}", headers=headers)
    assert revoked.status_code == 200
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.status_code == 401


@pytest.mark.asyncio
async def test_password_reset_flow(client, auth):
    email, password, _ = await _create_auth_user(client, auth, "reset")
    requested = await client.post("/api/v1/auth/forgot-password", json={"email": email})
    assert requested.status_code == 200
    token = requested.json()["dev_token"]
    assert token

    new_password = "N3w!Secure-Pass-2026"
    reset = await client.post(
        "/api/v1/auth/reset-password", json={"token": token, "new_password": new_password}
    )
    assert reset.status_code == 200, reset.text

    old_login = await client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert old_login.status_code == 401
    new_login = await client.post("/api/v1/auth/login", json={"email": email, "password": new_password})
    assert new_login.status_code == 200


@pytest.mark.asyncio
async def test_security_overview(client, auth):
    response = await client.get("/api/v1/auth/security", headers=auth)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["password_policy"]["min_length"] >= 12
    assert "mfa" in body
    assert any(session["current"] for session in body["sessions"])
