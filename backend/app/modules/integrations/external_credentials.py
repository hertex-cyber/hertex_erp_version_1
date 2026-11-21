from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from pydantic import Field, SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import NotFoundError, ValidationError
from app.core.schemas import ORMModel
from app.modules.identity.models import User
from app.modules.integrations.external_adapters import ConnectionResult, build_adapter
from app.modules.settings.secrets import secrets_service

PROVIDER_GST_PORTAL = "gst_portal"
PROVIDER_E_INVOICE_PORTAL = "e_invoice_portal"
PROVIDER_BANK_FEED = "bank_feed"
PROVIDER_PAYMENT_GATEWAY = "payment_gateway"
PROVIDER_OCR = "ocr"

PROVIDER_KEYS: tuple[str, ...] = (
    PROVIDER_GST_PORTAL,
    PROVIDER_E_INVOICE_PORTAL,
    PROVIDER_BANK_FEED,
    PROVIDER_PAYMENT_GATEWAY,
    PROVIDER_OCR,
)

SECRET_KEY_PREFIX = "integrations.external"

FIELD_CLIENT_ID = "client_id"
FIELD_CLIENT_SECRET = "client_secret"
FIELD_API_KEY = "api_key"
FIELD_API_SECRET = "api_secret"
FIELD_WEBHOOK_SECRET = "webhook_secret"

MAX_CREDENTIAL_LENGTH = 4096
MAX_REASON_LENGTH = 500


@dataclass(frozen=True, slots=True)
class ExternalProviderDescriptor:
    key: str
    label: str
    fields: tuple[str, ...]


PROVIDERS: dict[str, ExternalProviderDescriptor] = {
    PROVIDER_GST_PORTAL: ExternalProviderDescriptor(
        key=PROVIDER_GST_PORTAL,
        label="GST portal",
        fields=(FIELD_CLIENT_ID, FIELD_CLIENT_SECRET),
    ),
    PROVIDER_E_INVOICE_PORTAL: ExternalProviderDescriptor(
        key=PROVIDER_E_INVOICE_PORTAL,
        label="E-invoice portal",
        fields=(FIELD_CLIENT_ID, FIELD_CLIENT_SECRET),
    ),
    PROVIDER_BANK_FEED: ExternalProviderDescriptor(
        key=PROVIDER_BANK_FEED,
        label="Bank feed",
        fields=(FIELD_API_KEY, FIELD_API_SECRET),
    ),
    PROVIDER_PAYMENT_GATEWAY: ExternalProviderDescriptor(
        key=PROVIDER_PAYMENT_GATEWAY,
        label="Payment gateway",
        fields=(FIELD_API_KEY, FIELD_WEBHOOK_SECRET),
    ),
    PROVIDER_OCR: ExternalProviderDescriptor(
        key=PROVIDER_OCR,
        label="OCR service",
        fields=(FIELD_API_KEY,),
    ),
}


class ExternalCredentialWrite(ORMModel):
    credentials: dict[str, SecretStr]
    reason: str | None = None


class ExternalCredentialRotate(ORMModel):
    value: SecretStr
    window_hours: int = Field(default=72, ge=1, le=720)


class CredentialMaskRead(ORMModel):
    field: str
    key: str
    configured: bool
    mask: str
    status: str
    rotated_at: datetime | None = None
    rotation_ends_at: datetime | None = None
    last_used_at: datetime | None = None
    key_version: int = 1
    algo: str = "AES-256-GCM"


class CredentialMutationRead(CredentialMaskRead):
    rolled_back: bool = False


class ExternalProviderRead(ORMModel):
    provider: str
    label: str
    is_configured: bool
    required_fields: list[str]
    configured_fields: list[str]
    missing_fields: list[str]
    credentials: list[CredentialMaskRead]
    adapter_mode: str = "simulated"
    live_calls_enabled: bool = False


class ExternalConnectionRead(ORMModel):
    provider: str
    status: str
    is_configured: bool
    detail: str
    checked_fields: list[str]
    live_calls_enabled: bool = False


def validate_provider(provider: str) -> ExternalProviderDescriptor:
    descriptor = PROVIDERS.get(provider)
    if descriptor is None:
        raise ValidationError(
            f"Unknown external provider '{provider}'",
            code="integrations.external.unknown_provider",
        )
    return descriptor


def validate_field(provider: str, field: str) -> str:
    descriptor = validate_provider(provider)
    if field not in descriptor.fields:
        raise ValidationError(
            f"Unknown credential field '{field}' for provider '{provider}'",
            code="integrations.external.unknown_field",
        )
    return field


def secret_key(provider: str, field: str) -> str:
    validate_field(provider, field)
    return f"{SECRET_KEY_PREFIX}.{provider}.{field}"


def parse_secret_key(key: str) -> tuple[str, str] | None:
    prefix = f"{SECRET_KEY_PREFIX}."
    if not key.startswith(prefix):
        return None
    parts = key[len(prefix) :].split(".")
    if len(parts) != 2:
        return None
    provider, field = parts
    descriptor = PROVIDERS.get(provider)
    if descriptor is None or field not in descriptor.fields:
        return None
    return provider, field


def _plaintext(value: SecretStr, *, field: str) -> str:
    raw = value.get_secret_value()
    if not raw or len(raw) > MAX_CREDENTIAL_LENGTH:
        raise ValidationError(
            f"Credential '{field}' must be between 1 and {MAX_CREDENTIAL_LENGTH} characters",
            code="integrations.external.invalid_credential",
        )
    return raw


def _reason(reason: str | None) -> str:
    if reason is not None and len(reason) > MAX_REASON_LENGTH:
        raise ValidationError(
            f"Reason must be at most {MAX_REASON_LENGTH} characters",
            code="integrations.external.invalid_reason",
        )
    return reason or ""


def validate_credentials(
    provider: str, credentials: Mapping[str, SecretStr]
) -> dict[str, str]:
    descriptor = validate_provider(provider)
    if not credentials:
        raise ValidationError(
            "At least one credential is required",
            code="integrations.external.invalid_credential",
        )
    unknown = sorted(set(credentials) - set(descriptor.fields))
    if unknown:
        raise ValidationError(
            "Unknown credential field(s): " + ", ".join(unknown),
            code="integrations.external.unknown_field",
        )
    return {
        field: _plaintext(value, field=field) for field, value in credentials.items()
    }


class ExternalCredentialsService:
    async def _masked_by_key(
        self, db: AsyncSession, tenant_id: Any
    ) -> dict[str, dict[str, Any]]:
        rows = await secrets_service.list_masked(db, tenant_id=tenant_id)
        return {row["key"]: row for row in rows}

    def _provider_read(
        self,
        descriptor: ExternalProviderDescriptor,
        masked: Mapping[str, dict[str, Any]],
    ) -> ExternalProviderRead:
        credentials: list[CredentialMaskRead] = []
        for name in descriptor.fields:
            key = secret_key(descriptor.key, name)
            row = masked.get(key)
            if row is None:
                credentials.append(
                    CredentialMaskRead(
                        field=name,
                        key=key,
                        configured=False,
                        mask="",
                        status="missing",
                    )
                )
            else:
                credentials.append(
                    CredentialMaskRead(
                        field=name,
                        key=row["key"],
                        configured=bool(row["configured"]),
                        mask=row["mask"],
                        status=row["status"],
                        rotated_at=row["rotated_at"],
                        rotation_ends_at=row["rotation_ends_at"],
                        last_used_at=row["last_used_at"],
                        key_version=row["key_version"],
                        algo=row["algo"],
                    )
                )
        configured = [item.field for item in credentials if item.configured]
        missing = [name for name in descriptor.fields if name not in configured]
        return ExternalProviderRead(
            provider=descriptor.key,
            label=descriptor.label,
            is_configured=not missing,
            required_fields=list(descriptor.fields),
            configured_fields=configured,
            missing_fields=missing,
            credentials=credentials,
        )

    async def list_providers(
        self, db: AsyncSession, tenant_id: Any
    ) -> list[ExternalProviderRead]:
        masked = await self._masked_by_key(db, tenant_id)
        return [self._provider_read(descriptor, masked) for descriptor in PROVIDERS.values()]

    async def get_provider(
        self, db: AsyncSession, tenant_id: Any, provider: str
    ) -> ExternalProviderRead:
        descriptor = validate_provider(provider)
        masked = await self._masked_by_key(db, tenant_id)
        return self._provider_read(descriptor, masked)

    async def set_credentials(
        self,
        db: AsyncSession,
        user: User,
        *,
        provider: str,
        credentials: Mapping[str, SecretStr],
        reason: str | None = None,
    ) -> ExternalProviderRead:
        validate_provider(provider)
        plaintext = validate_credentials(provider, credentials)
        audit_reason = _reason(reason)
        for name, value in plaintext.items():
            await secrets_service.set_secret(
                db,
                user,
                key=secret_key(provider, name),
                plaintext=value,
                reason=audit_reason,
            )
        return await self.get_provider(db, user.tenant_id, provider)

    async def _credential_read(
        self, db: AsyncSession, tenant_id: Any, provider: str, field: str
    ) -> CredentialMaskRead:
        key = secret_key(provider, field)
        masked = await self._masked_by_key(db, tenant_id)
        row = masked.get(key)
        if row is None:
            raise NotFoundError(f"External credential '{key}' is not configured")
        return CredentialMaskRead(
            field=field,
            key=row["key"],
            configured=bool(row["configured"]),
            mask=row["mask"],
            status=row["status"],
            rotated_at=row["rotated_at"],
            rotation_ends_at=row["rotation_ends_at"],
            last_used_at=row["last_used_at"],
            key_version=row["key_version"],
            algo=row["algo"],
        )

    async def _mutation_read(
        self,
        db: AsyncSession,
        tenant_id: Any,
        provider: str,
        field: str,
        *,
        status: str,
        rotation_ends_at: datetime | None = None,
        rolled_back: bool = False,
    ) -> CredentialMutationRead:
        base = await self._credential_read(db, tenant_id, provider, field)
        data = base.model_dump()
        data["status"] = status
        if rotation_ends_at is not None:
            data["rotation_ends_at"] = rotation_ends_at
        data["rolled_back"] = rolled_back
        return CredentialMutationRead(**data)

    async def rotate(
        self,
        db: AsyncSession,
        user: User,
        *,
        provider: str,
        field: str,
        value: SecretStr,
        window_hours: int = 72,
    ) -> CredentialMutationRead:
        key = secret_key(provider, field)
        raw = _plaintext(value, field=field)
        result = await secrets_service.rotate(
            db, user, key=key, plaintext=raw, window_hours=window_hours
        )
        return await self._mutation_read(
            db,
            user.tenant_id,
            provider,
            field,
            status=result["status"],
            rotation_ends_at=result["window_ends_at"],
        )

    async def commit(
        self, db: AsyncSession, user: User, *, provider: str, field: str
    ) -> CredentialMutationRead:
        key = secret_key(provider, field)
        result = await secrets_service.commit(db, user, key=key)
        return await self._mutation_read(
            db, user.tenant_id, provider, field, status=result["status"]
        )

    async def rollback(
        self, db: AsyncSession, user: User, *, provider: str, field: str
    ) -> CredentialMutationRead:
        key = secret_key(provider, field)
        result = await secrets_service.rollback(db, user, key=key)
        return await self._mutation_read(
            db,
            user.tenant_id,
            provider,
            field,
            status=result["status"],
            rolled_back=bool(result["rolled_back"]),
        )

    async def test_connection(
        self, db: AsyncSession, user: User, *, provider: str
    ) -> ExternalConnectionRead:
        descriptor = validate_provider(provider)
        credentials: dict[str, str] = {}
        for name in descriptor.fields:
            raw = await secrets_service.get_plaintext(
                db, tenant_id=user.tenant_id, key=secret_key(descriptor.key, name)
            )
            if raw:
                credentials[name] = raw
        adapter = build_adapter(
            provider=descriptor.key,
            required_fields=descriptor.fields,
            credentials=credentials,
        )
        result: ConnectionResult = await adapter.test_connection()
        await record_audit(
            db,
            user=user,
            action="integrations.external.test_connection",
            module="integrations",
            entity="ExternalProvider",
            entity_id=descriptor.key,
            changes={
                "provider": descriptor.key,
                "status": result.status,
                "is_configured": result.is_configured,
                "checked_fields": result.checked_fields,
            },
            request=None,
        )
        await db.commit()
        return ExternalConnectionRead(
            provider=result.provider,
            status=result.status,
            is_configured=result.is_configured,
            detail=result.detail,
            checked_fields=result.checked_fields,
        )


external_credentials_service = ExternalCredentialsService()
