import json
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.db.session import AsyncSessionLocal
from app.modules.identity.models import AuditLog
from app.modules.procurement.models import VendorInvoice
from app.modules.procurement.ocr_models import OCRInvoiceDraft
from app.modules.procurement.ocr_service import (
    OCR_CREDENTIAL_SECRET_KEY,
    OCRExtraction,
    set_external_extractor,
)

BASE = "/api/v1/procurement/ocr"


def _json_document(marker: str, **overrides):
    document = {
        "vendor": f"OCR Vendor {marker}",
        "invoice_number": f"OCR-{marker}",
        "date": date.today().isoformat(),
        "amount": "1250.00",
        "tax_amount": "225.00",
        "gstin": "27AAPFU0939F1ZV",
    }
    document.update(overrides)
    return document


@pytest.mark.asyncio
async def test_submit_json_document_persists_ocr_draft(client, auth):
    marker = uuid4().hex[:10]
    response = await client.post(
        f"{BASE}/documents",
        headers=auth,
        json={
            "document": _json_document(marker),
            "filename": "invoice.json",
            "mime_type": "application/json",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["vendor_name"] == f"OCR Vendor {marker}"
    assert body["invoice_number"] == f"OCR-{marker}"
    assert body["invoice_date"] == date.today().isoformat()
    assert Decimal(body["amount"]) == Decimal("1250.00")
    assert Decimal(body["tax_amount"]) == Decimal("225.00")
    assert body["gstin"] == "27AAPFU0939F1ZV"
    assert Decimal(body["confidence"]) > Decimal("0.9")
    assert body["provider"] == "local_stub"
    assert body["credential_key"] is None
    assert body["status"] == "pending"
    assert body["source_type"] == "json"

    fetched = await client.get(f"{BASE}/drafts/{body['id']}", headers=auth)
    assert fetched.status_code == 200, fetched.text
    assert fetched.json()["id"] == body["id"]

    listed = await client.get(
        f"{BASE}/drafts", headers=auth, params={"status": "pending", "q": marker}
    )
    assert listed.status_code == 200, listed.text
    assert any(item["id"] == body["id"] for item in listed.json()["items"])


@pytest.mark.asyncio
async def test_upload_text_document_uses_deterministic_stub(client, auth):
    marker = uuid4().hex[:10]
    text = (
        f"Invoice No: UPLOAD-{marker}\n"
        f"Vendor: OCR Upload Vendor {marker}\n"
        f"Date: {date.today().isoformat()}\n"
        "GSTIN: 27AAPFU0939F1ZV\n"
        "Total: 999.00\n"
        "GST: 90.00\n"
    )
    response = await client.post(
        f"{BASE}/documents/upload",
        headers=auth,
        files={"file": ("invoice.txt", text.encode("utf-8"), "text/plain")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["invoice_number"] == f"UPLOAD-{marker}"
    assert body["vendor_name"] == f"OCR Upload Vendor {marker}"
    assert Decimal(body["amount"]) == Decimal("999.00")
    assert Decimal(body["tax_amount"]) == Decimal("90.00")
    assert body["gstin"] == "27AAPFU0939F1ZV"
    assert body["source_type"] == "text"
    assert body["filename"] == "invoice.txt"
    assert Decimal(body["confidence"]) > Decimal("0.8")


@pytest.mark.asyncio
async def test_confirm_creates_draft_vendor_invoice_without_posting(client, auth):
    marker = uuid4().hex[:10]
    vendor_name = f"OCR Confirm Vendor {marker}"
    vendor = await client.post(
        "/api/v1/procurement/vendors",
        headers=auth,
        json={
            "code": f"OCR-{marker}",
            "name": vendor_name,
            "gstin": "27AAPFU0939F1ZV",
        },
    )
    assert vendor.status_code == 201, vendor.text
    vendor_id = vendor.json()["id"]

    extracted = await client.post(
        f"{BASE}/documents",
        headers=auth,
        json={"document": _json_document(marker, vendor=vendor_name)},
    )
    assert extracted.status_code == 201, extracted.text
    draft = extracted.json()
    assert draft["vendor_id"] == vendor_id

    confirmed = await client.post(f"{BASE}/drafts/{draft['id']}/confirm", headers=auth, json={})
    assert confirmed.status_code == 200, confirmed.text
    invoice = confirmed.json()
    assert invoice["status"] == "draft"
    assert invoice["vendor_id"] == vendor_id
    assert invoice["invoice_number"] == f"OCR-{marker}"
    assert Decimal(invoice["amount"]) == Decimal("1250.00")
    assert Decimal(invoice["tax_amount"]) == Decimal("225.00")

    invoice_row = await client.get(
        f"/api/v1/procurement/vendor-invoices/{invoice['id']}", headers=auth
    )
    assert invoice_row.status_code == 200, invoice_row.text
    assert invoice_row.json()["status"] == "draft"

    entries = await client.get(
        "/api/v1/finance/journal-entries", headers=auth, params={"size": 200}
    )
    assert entries.status_code == 200, entries.text
    assert all(
        row["reference"] != f"VINV:{invoice['invoice_number']}" for row in entries.json()["items"]
    )

    async with AsyncSessionLocal() as db:
        audit_count = await db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "ocr.confirm", AuditLog.entity_id == str(invoice["id"]))
        )
        invoice_count = await db.scalar(
            select(func.count())
            .select_from(VendorInvoice)
            .where(VendorInvoice.invoice_number == invoice["invoice_number"])
        )
        updated_draft = await db.scalar(
            select(OCRInvoiceDraft).where(OCRInvoiceDraft.id == UUID(draft["id"]))
        )
    assert audit_count == 1
    assert invoice_count == 1
    assert updated_draft is not None
    assert updated_draft.status == "confirmed"
    assert str(updated_draft.confirmed_invoice_id) == invoice["id"]

    repeated = await client.post(f"{BASE}/drafts/{draft['id']}/confirm", headers=auth, json={})
    assert repeated.status_code == 200, repeated.text
    assert repeated.json()["id"] == invoice["id"]


@pytest.mark.asyncio
async def test_reject_and_delete_draft(client, auth):
    marker = uuid4().hex[:10]
    extracted = await client.post(
        f"{BASE}/documents", headers=auth, json={"document": _json_document(marker)}
    )
    assert extracted.status_code == 201, extracted.text
    draft_id = extracted.json()["id"]

    rejected = await client.post(
        f"{BASE}/drafts/{draft_id}/reject",
        headers=auth,
        json={"reason": "Blurry scan"},
    )
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "rejected"
    assert rejected.json()["rejection_reason"] == "Blurry scan"

    confirmed = await client.post(f"{BASE}/drafts/{draft_id}/confirm", headers=auth, json={})
    assert confirmed.status_code == 409, confirmed.text

    async with AsyncSessionLocal() as db:
        audit_count = await db.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.action == "ocr.reject", AuditLog.entity_id == draft_id)
        )
    assert audit_count == 1

    deleted = await client.delete(f"{BASE}/drafts/{draft_id}", headers=auth)
    assert deleted.status_code == 200, deleted.text
    fetched = await client.get(f"{BASE}/drafts/{draft_id}", headers=auth)
    assert fetched.status_code == 404, fetched.text
    listed = await client.get(f"{BASE}/drafts", headers=auth, params={"q": marker})
    assert listed.json()["total"] == 0


@pytest.mark.asyncio
async def test_external_credential_hook_never_stores_plaintext(client, auth):
    marker = uuid4().hex[:10]
    plaintext = f"sk-ocr-{marker}"
    secret_write = await client.put(
        f"/api/v1/settings/secrets/{OCR_CREDENTIAL_SECRET_KEY}",
        headers=auth,
        json={"value": plaintext, "reason": "OCR test"},
    )
    assert secret_write.status_code == 200, secret_write.text

    seen = {}

    def fake_extractor(*, document, credential):
        seen["credential"] = credential
        return OCRExtraction(
            vendor_name=f"External Vendor {marker}",
            invoice_number=f"EXT-{marker}",
            invoice_date=date.today(),
            amount=Decimal("500.00"),
            tax_amount=Decimal("50.00"),
            gstin="27AAPFU0939F1ZV",
            confidence=Decimal("0.9100"),
        )

    set_external_extractor(fake_extractor)
    try:
        response = await client.post(
            f"{BASE}/documents",
            headers=auth,
            json={"text": f"external raw document {marker}", "provider": "external"},
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["provider"] == "external"
        assert body["credential_key"] == OCR_CREDENTIAL_SECRET_KEY
        assert body["invoice_number"] == f"EXT-{marker}"
        assert seen["credential"] == plaintext
        assert plaintext not in response.text

        async with AsyncSessionLocal() as db:
            draft = await db.scalar(
                select(OCRInvoiceDraft).where(OCRInvoiceDraft.id == UUID(body["id"]))
            )
        assert draft is not None
        stored = json.dumps(draft.__dict__, default=str)
        assert plaintext not in stored
        assert "ciphertext" not in stored
    finally:
        set_external_extractor(None)
        cleanup = await client.delete(
            f"/api/v1/settings/secrets/{OCR_CREDENTIAL_SECRET_KEY}", headers=auth
        )
        assert cleanup.status_code == 200, cleanup.text
