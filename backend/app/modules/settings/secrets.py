"""Secret settings vault (module 15A, M5 / 15-SETTINGS SE-05).

* AES-256-GCM ciphertext, key version recorded per row.
* The plaintext is never returned by the API, never audited, never logged.
* Rotation keeps a *window*: during ``pending`` verification may read the
  previous value while outbound callers use the new active value. ``commit``
  promotes the new value and wipes the old one; ``rollback`` throws it away.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.crypto import SecretDecryptionError, decrypt, encrypt, mask, rewrap
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.identity.models import User
from app.modules.settings.models import SettingSecret

logger = logging.getLogger("hertex.settings.secrets")

ROTATION_WINDOW_HOURS = 72


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SecretsService:
    async def _get(self, db: AsyncSession, tenant_id: UUID | None, key: str) -> SettingSecret | None:
        stmt = select(SettingSecret).where(SettingSecret.key == key)
        if tenant_id is not None:
            stmt = stmt.where(SettingSecret.tenant_id == tenant_id)
        else:
            stmt = stmt.where(SettingSecret.tenant_id.is_(None))
        return await db.scalar(stmt)

    async def set_secret(
        self,
        db: AsyncSession,
        user: User,
        *,
        key: str,
        plaintext: str,
        reason: str = "",
        request_id: str | None = None,
    ) -> dict:
        if not plaintext:
            raise ValidationError("Secret value cannot be empty", code="settings.validation_failed")
        ciphertext, nonce, key_version = encrypt(plaintext)
        row = await self._get(db, user.tenant_id, key)
        if row is None:
            row = SettingSecret(
                tenant_id=user.tenant_id,
                key=key,
                ciphertext=ciphertext,
                nonce=nonce,
                key_version=key_version,
                status="active",
                mask=mask(plaintext),
                rotated_at=_now(),
                rotated_by_id=user.id,
            )
            db.add(row)
        else:
            row.ciphertext = ciphertext
            row.nonce = nonce
            row.key_version = key_version
            row.status = "active"
            row.mask = mask(plaintext)
            row.rotated_at = _now()
            row.rotated_by_id = user.id
            row.previous_ciphertext = None
            row.previous_nonce = None
            row.previous_key_version = None
            row.previous_expires_at = None
        await record_audit(
            db,
            user=user,
            action="settings.secret.write",
            module="settings",
            entity="SettingSecret",
            entity_id=row.id,
            changes={"key": key, "value": "__redacted__", "reason": reason},
            request=None,
            correlation_id=request_id,
        )
        await db.commit()
        return {"key": key, "configured": True, "mask": row.mask, "rotated_at": row.rotated_at}

    async def rotate(
        self,
        db: AsyncSession,
        user: User,
        *,
        key: str,
        plaintext: str,
        window_hours: int = ROTATION_WINDOW_HOURS,
    ) -> dict:
        row = await self._get(db, user.tenant_id, key)
        if row is None:
            raise NotFoundError(f"Secret '{key}' is not configured")
        ciphertext, nonce, key_version = encrypt(plaintext)
        row.previous_ciphertext = row.ciphertext
        row.previous_nonce = row.nonce
        row.previous_key_version = row.key_version
        row.previous_expires_at = _now() + timedelta(hours=window_hours)
        row.ciphertext = ciphertext
        row.nonce = nonce
        row.key_version = key_version
        row.status = "pending"
        row.mask = mask(plaintext)
        await record_audit(
            db,
            user=user,
            action="settings.secret.rotate",
            module="settings",
            entity="SettingSecret",
            entity_id=row.id,
            changes={"key": key, "value": "__redacted__", "window_hours": window_hours},
            request=None,
        )
        await db.commit()
        return {
            "key": key,
            "status": "pending",
            "window_ends_at": row.previous_expires_at,
            "previous_in_use": True,
        }

    async def commit(self, db: AsyncSession, user: User, *, key: str) -> dict:
        row = await self._get(db, user.tenant_id, key)
        if row is None:
            raise NotFoundError(f"Secret '{key}' is not configured")
        if row.status != "pending":
            raise ConflictError("Secret is not in a rotation window", code="settings.secret_not_pending")
        row.previous_ciphertext = None
        row.previous_nonce = None
        row.previous_key_version = None
        row.previous_expires_at = None
        row.status = "active"
        row.rotated_at = _now()
        row.rotated_by_id = user.id
        await record_audit(
            db,
            user=user,
            action="settings.secret.commit",
            module="settings",
            entity="SettingSecret",
            entity_id=row.id,
            changes={"key": key, "value": "__redacted__"},
            request=None,
        )
        await db.commit()
        return {"key": key, "status": "active"}

    async def rollback(self, db: AsyncSession, user: User, *, key: str) -> dict:
        row = await self._get(db, user.tenant_id, key)
        if row is None:
            raise NotFoundError(f"Secret '{key}' is not configured")
        if row.status != "pending" or row.previous_ciphertext is None:
            raise ConflictError("Nothing to roll back", code="settings.secret_not_pending")
        if row.previous_expires_at:
            expires_at = row.previous_expires_at
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < _now():
                raise ConflictError("Rotation window has expired", code="settings.secret_window_expired")
        row.ciphertext = row.previous_ciphertext
        row.nonce = row.previous_nonce or b""
        row.key_version = row.previous_key_version or row.key_version
        row.previous_ciphertext = None
        row.previous_nonce = None
        row.previous_key_version = None
        row.previous_expires_at = None
        row.status = "active"
        await record_audit(
            db,
            user=user,
            action="settings.secret.rollback",
            module="settings",
            entity="SettingSecret",
            entity_id=row.id,
            changes={"key": key, "value": "__redacted__"},
            request=None,
        )
        await db.commit()
        return {"key": key, "status": "active", "rolled_back": True}

    async def get_plaintext(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        key: str,
        intent: str = "outbound",
    ) -> str | None:
        """Consumer read path with verify/outbound semantics for rotation windows."""
        if intent not in {"outbound", "verify"}:
            raise ValidationError("Unknown secret read intent", code="settings.validation_failed")
        row = await self._get(db, tenant_id, key)
        if row is None:
            return None
        use_previous = (
            row.status == "pending"
            and row.previous_ciphertext is not None
            and intent == "verify"
        )
        try:
            if use_previous:
                value = decrypt(
                    row.previous_ciphertext,
                    row.previous_nonce or b"",
                    row.previous_key_version or row.key_version,
                )
            else:
                value = decrypt(row.ciphertext, row.nonce, row.key_version)
        except SecretDecryptionError:
            logger.error("settings.secret.decrypt_failed", extra={"key": key})
            return None
        row.last_used_at = _now()
        await db.flush()
        return value

    async def rewrap_secret(
        self, db: AsyncSession, user: User, *, key: str, key_version: int
    ) -> dict[str, Any]:
        row = await self._get(db, user.tenant_id, key)
        if row is None:
            raise NotFoundError(f"Secret '{key}' is not configured")
        ciphertext, nonce, new_version = rewrap(
            row.ciphertext, row.nonce, row.key_version, key_version
        )
        row.ciphertext = ciphertext
        row.nonce = nonce
        row.key_version = new_version
        await record_audit(
            db,
            user=user,
            action="settings.secret.rewrap",
            module="settings",
            entity="SettingSecret",
            entity_id=row.id,
            changes={"key": key, "value": "__redacted__", "key_version": new_version},
            request=None,
        )
        await db.commit()
        return self.masked_response(row)

    async def list_masked(self, db: AsyncSession, *, tenant_id: UUID | None) -> list[dict[str, Any]]:
        stmt = select(SettingSecret)
        if tenant_id is not None:
            stmt = stmt.where(SettingSecret.tenant_id == tenant_id)
        rows = (await db.scalars(stmt.order_by(SettingSecret.key))).all()
        return [
            {
                "key": row.key,
                "configured": True,
                "mask": row.mask or "••••",
                "status": row.status,
                "rotated_at": row.rotated_at,
                "rotation_ends_at": row.previous_expires_at,
                "last_used_at": row.last_used_at,
                "key_version": row.key_version,
                "algo": row.algo,
            }
            for row in rows
        ]

    async def delete(self, db: AsyncSession, user: User, *, key: str) -> None:
        row = await self._get(db, user.tenant_id, key)
        if row is None:
            raise NotFoundError(f"Secret '{key}' is not configured")
        await db.delete(row)
        await record_audit(
            db,
            user=user,
            action="settings.secret.delete",
            module="settings",
            entity="SettingSecret",
            entity_id=row.id,
            changes={"key": key, "value": "__redacted__"},
            request=None,
        )
        await db.commit()

    def masked_response(self, row: SettingSecret) -> dict[str, Any]:
        return {
            "key": row.key,
            "configured": True,
            "mask": row.mask,
            "status": row.status,
            "rotated_at": row.rotated_at,
        }


secrets_service = SecretsService()
