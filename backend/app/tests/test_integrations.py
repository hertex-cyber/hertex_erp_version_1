import hashlib
import hmac
import json
from uuid import uuid4

import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_whatsapp_webhook_links_inbound_message_to_lead(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "META_APP_SECRET", "pytest-secret")
    phone = "919900001234"
    lead = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={
            "name": f"WhatsApp Lead {uuid4().hex[:6]}",
            "phone": phone,
            "whatsapp_opt_in": True,
        },
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]

    message_id = f"wamid.{uuid4().hex}"
    payload = {
        "entry": [
            {
                "changes": [
                    {
                        "value": {
                            "contacts": [{"profile": {"name": "WhatsApp Lead"}}],
                            "messages": [
                                {
                                    "id": message_id,
                                    "from": phone,
                                    "type": "text",
                                    "text": {"body": "Please send a quotation"},
                                }
                            ],
                        }
                    }
                ]
            }
        ]
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(
        b"pytest-secret", raw, hashlib.sha256
    ).hexdigest()

    rejected = await client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": "sha256=deadbeef", "Content-Type": "application/json"},
    )
    assert rejected.status_code == 403

    response = await client.post(
        "/api/v1/integrations/whatsapp/webhook",
        content=raw,
        headers={"X-Hub-Signature-256": signature, "Content-Type": "application/json"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["received"] == 1

    messages = await client.get(
        "/api/v1/integrations/messages",
        headers=auth,
        params={"channel": "whatsapp", "direction": "inbound", "size": 200},
    )
    assert messages.status_code == 200
    stored = next(
        row for row in messages.json()["items"] if row["external_id"] == message_id
    )
    assert stored["module"] == "crm"

    refreshed = await client.get(f"/api/v1/crm/leads/{lead_id}", headers=auth)
    assert refreshed.status_code == 200
    assert refreshed.json()["status"] == "contacted"


@pytest.mark.asyncio
async def test_whatsapp_send_enforces_opt_in(client, auth):
    marker = str(uuid4().int)[:8]
    blocked_phone = f"9198{marker}"
    allowed_phone = f"9197{marker}"
    opted_out = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={
            "name": f"Opted Out {marker}",
            "phone": blocked_phone,
            "whatsapp_opt_in": False,
        },
    )
    assert opted_out.status_code == 201, opted_out.text
    blocked = await client.post(
        "/api/v1/integrations/send",
        headers=auth,
        json={"channel": "whatsapp", "to": blocked_phone, "body": "Hello"},
    )
    assert blocked.status_code == 403

    opted_in = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={
            "name": f"Opted In {marker}",
            "phone": allowed_phone,
            "whatsapp_opt_in": True,
        },
    )
    assert opted_in.status_code == 201, opted_in.text
    sent = await client.post(
        "/api/v1/integrations/send",
        headers=auth,
        json={"channel": "whatsapp", "to": allowed_phone, "body": "Hello"},
    )
    assert sent.status_code == 200, sent.text
    body = sent.json()
    assert body["status"] == "simulated"
    assert "credentials" in body["detail"]
