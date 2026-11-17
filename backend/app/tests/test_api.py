import pytest


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
