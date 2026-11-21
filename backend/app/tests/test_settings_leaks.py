import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.core.audit import REDACTED, record_audit
from app.db.session import AsyncSessionLocal
from app.modules.identity.models import AuditLog, User


@pytest.fixture(scope="module")
def leak_scanner():
    path = Path(__file__).resolve().parents[2] / "scripts" / "scan_settings_leaks.py"
    spec = importlib.util.spec_from_file_location("scan_settings_leaks", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_audit_redacts_nested_secrets():
    from app.core.audit import redact_value

    sanitized = redact_value(
        {
            "nested": {
                "gst_portal.client_secret": "very-secret-value",
                "items": [{"webhook_secret": "hook-secret-value", "name": "safe"}],
            }
        }
    )
    serialized = json.dumps(sanitized)
    assert "very-secret-value" not in serialized
    assert "hook-secret-value" not in serialized
    assert sanitized["nested"]["gst_portal.client_secret"] == REDACTED
    assert sanitized["nested"]["items"][0]["name"] == "safe"


@pytest.mark.asyncio
async def test_record_audit_persists_redacted_changes():
    action = f"test.settings.leak.{uuid4().hex}"
    plaintext = "plaintext-credential-12345"
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        assert user is not None
        await record_audit(
            db,
            user=user,
            action=action,
            module="settings",
            entity="leak-test",
            changes={"outer": {"gst_portal.client_secret": plaintext}},
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        log = await db.scalar(select(AuditLog).where(AuditLog.action == action))
        assert log is not None
        assert plaintext not in json.dumps(log.changes)
        assert log.changes["outer"]["gst_portal.client_secret"] == REDACTED


def test_leak_scanner_flags_value_bearing_secret_key(leak_scanner):
    findings = leak_scanner.scan_text(
        "changes = {'gst_portal.client_secret': 'abcdefghijklmnop'}\n",
        "example.py",
    )
    assert findings


def test_leak_scanner_accepts_registry_reference(leak_scanner):
    findings = leak_scanner.scan_text(
        'OCR_CREDENTIAL_SECRET_KEY = "integrations.ocr.api_key"\n',
        "ocr_service.py",
    )
    assert findings == []
