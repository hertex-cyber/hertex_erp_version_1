import hashlib
import hmac
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.config import settings
from app.modules.integrations.adapters import MetaLeadAdapter


@pytest.mark.asyncio
async def test_lead_creation_records_explainable_score(client, auth):
    response = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={
            "name": f"Scored Lead {uuid4().hex[:8]}",
            "email": f"scored-{uuid4().hex[:8]}@example.com",
            "estimated_value": "250000",
            "whatsapp_opt_in": True,
        },
    )
    assert response.status_code == 201, response.text
    lead_id = response.json()["id"]

    explanation = await client.get(
        f"/api/v1/crm/leads/{lead_id}/score-explanation", headers=auth
    )
    assert explanation.status_code == 200, explanation.text
    body = explanation.json()
    assert body["lead_id"] == lead_id
    assert body["score"] >= 0
    assert body["model_version"] == "rule-v1"
    assert body["facts"]
    assert isinstance(body["top_features"], list)


@pytest.mark.asyncio
async def test_lead_conversion_and_deal_win_emit_facts(client, auth):
    lead = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={
            "name": f"Convert Me {uuid4().hex[:6]}",
            "company_name": f"Convert Co {uuid4().hex[:6]}",
            "email": f"convert-{uuid4().hex[:8]}@example.com",
            "estimated_value": "100000",
            "whatsapp_opt_in": True,
        },
    )
    assert lead.status_code == 201, lead.text
    lead_id = lead.json()["id"]

    converted = await client.post(
        f"/api/v1/crm/leads/{lead_id}/convert",
        headers=auth,
        json={"deal_name": "Converted opportunity", "stage": "negotiation"},
    )
    assert converted.status_code == 200, converted.text
    result = converted.json()
    assert result["lead_id"] == lead_id
    assert result["company_id"] and result["contact_id"]

    won = await client.post(
        f"/api/v1/crm/deals/{result['deal_id']}/win",
        headers=auth,
        json={},
    )
    assert won.status_code == 200, won.text
    deal = won.json()
    assert deal["probability"] == 100
    assert deal["won_at"] is not None
    assert deal["weighted_amount"] == "100000.00"

    refreshed = await client.get(f"/api/v1/crm/leads/{lead_id}", headers=auth)
    assert refreshed.json()["status"] == "won"


@pytest.mark.asyncio
async def test_consent_revoke_blocks_whatsapp_send(client, auth):
    marker = uuid4().hex[:8]
    phone = f"9196{marker}"
    lead = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={"name": f"Consent {marker}", "phone": phone, "whatsapp_opt_in": True},
    )
    assert lead.status_code == 201, lead.text

    state = await client.get(
        f"/api/v1/crm/consent/lead/{lead.json()['id']}",
        headers=auth,
        params={"channel": "whatsapp"},
    )
    assert state.status_code == 200, state.text
    assert state.json()["status"] == "opted_in"

    revoked = await client.post(
        f"/api/v1/crm/consent/{state.json()['record']['id']}/revoke",
        headers=auth,
    )
    assert revoked.status_code == 200, revoked.text

    blocked = await client.post(
        "/api/v1/integrations/send",
        headers=auth,
        json={"channel": "whatsapp", "to": phone, "body": "No thanks"},
    )
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_stale_consent_ledger_blocks_whatsapp_send(client, auth):
    marker = uuid4().hex[:8]
    phone = f"9195{marker}"
    lead = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={"name": f"Stale Consent {marker}", "phone": phone},
    )
    assert lead.status_code == 201, lead.text
    stale_at = datetime.now(timezone.utc) - timedelta(days=2)
    captured = await client.post(
        "/api/v1/crm/consent",
        headers=auth,
        json={
            "subject_type": "lead",
            "subject_id": lead.json()["id"],
            "channel": "whatsapp",
            "status": "opted_in",
            "source": "legacy.import",
            "captured_at": stale_at.isoformat(),
        },
    )
    assert captured.status_code == 201, captured.text

    blocked = await client.post(
        "/api/v1/integrations/send",
        headers=auth,
        json={"channel": "whatsapp", "to": phone, "body": "Still there?"},
    )
    assert blocked.status_code == 403


@pytest.mark.asyncio
async def test_call_assessment_can_be_generated_and_approved(client, auth):
    marker = uuid4().hex[:6]
    lead = await client.post(
        "/api/v1/crm/leads",
        headers=auth,
        json={"name": f"Call Lead {marker}", "email": f"call-{marker}@example.com"},
    )
    assert lead.status_code == 201, lead.text
    call = await client.post(
        "/api/v1/crm/calls",
        headers=auth,
        json={
            "lead_id": lead.json()["id"],
            "provider": "manual",
            "direction": "inbound",
            "status": "completed",
        },
    )
    assert call.status_code == 201, call.text
    call_id = call.json()["id"]

    transcript = await client.post(
        f"/api/v1/crm/calls/{call_id}/transcript",
        headers=auth,
        json={
            "sequence": 0,
            "speaker": "rep",
            "text": "I can help with that. Let me schedule a demo and confirm the next step.",
        },
    )
    assert transcript.status_code == 201, transcript.text

    assessed = await client.post(
        f"/api/v1/crm/calls/{call_id}/assess", headers=auth
    )
    assert assessed.status_code == 201, assessed.text
    assessment_id = assessed.json()["id"]
    assert assessed.json()["status"] == "draft"

    approved = await client.post(
        f"/api/v1/crm/calls/{call_id}/assessment/{assessment_id}/approve",
        headers=auth,
        json={"status": "approved"},
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"


@pytest.mark.asyncio
async def test_social_post_requires_approval_before_publish(client, auth):
    account = await client.post(
        "/api/v1/crm/social/accounts",
        headers=auth,
        json={
            "channel": "instagram",
            "external_account_id": f"ig-{uuid4().hex[:10]}",
            "display_name": "Hertex Studio",
        },
    )
    assert account.status_code == 201, account.text
    account_id = account.json()["id"]

    post = await client.post(
        "/api/v1/crm/social/posts",
        headers=auth,
        json={"account_id": account_id, "body": "New festive collection is live."},
    )
    assert post.status_code == 201, post.text
    post_id = post.json()["id"]
    assert post.json()["status"] == "draft"

    published_too_early = await client.post(
        f"/api/v1/crm/social/posts/{post_id}/publish", headers=auth
    )
    assert published_too_early.status_code in {409, 422}

    approved = await client.post(
        f"/api/v1/crm/social/posts/{post_id}/approve", headers=auth
    )
    assert approved.status_code == 200, approved.text
    published = await client.post(
        f"/api/v1/crm/social/posts/{post_id}/publish", headers=auth
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"


@pytest.mark.asyncio
async def test_meta_lead_webhook_is_signed_deduplicated_and_scored(client, auth, monkeypatch):
    monkeypatch.setattr(settings, "META_APP_SECRET", "pytest-meta-secret")

    async def fake_fetch(self, leadgen_id):
        return {
            "field_data": [
                {"name": "full_name", "values": ["Meta Webhook Lead"]},
                {"name": "email", "values": [f"meta-{leadgen_id}@example.com"]},
                {"name": "phone_number", "values": ["919900009999"]},
            ]
        }

    monkeypatch.setattr(MetaLeadAdapter, "fetch", fake_fetch)
    leadgen_id = f"leadgen-{uuid4().hex}"
    payload = {
        "entry": [
            {
                "id": "meta-page-1",
                "changes": [
                    {
                        "field": "leadgen",
                        "value": {
                            "leadgen_id": leadgen_id,
                            "form_id": "form-1",
                            "ad_id": "ad-1",
                        },
                    }
                ],
            }
        ]
    }
    raw = json.dumps(payload).encode()
    signature = "sha256=" + hmac.new(
        b"pytest-meta-secret", raw, hashlib.sha256
    ).hexdigest()
    headers = {"X-Hub-Signature-256": signature, "Content-Type": "application/json"}

    first = await client.post("/api/v1/integrations/whatsapp/webhook", content=raw, headers=headers)
    assert first.status_code == 200, first.text
    assert first.json()["received"] == 1

    second = await client.post("/api/v1/integrations/whatsapp/webhook", content=raw, headers=headers)
    assert second.status_code == 200, second.text
    assert second.json()["received"] == 0
    assert second.json()["duplicates"] == 1

    events = await client.get(
        "/api/v1/integrations/webhook-events",
        headers=auth,
        params={"provider": "meta", "size": 200},
    )
    assert events.status_code == 200, events.text
    stored = next(
        item for item in events.json()["items"] if item["external_event_id"] == leadgen_id
    )
    assert stored["status"] == "processed"
    assert stored["signature_valid"] is True
