from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Optional
from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.identity.models import AuditLog, User

REDACTED_KEYS = {
    "password", "current_password", "new_password", "hashed_password", "token",
    "refresh_token", "secret", "mfa_secret", "totp_secret", "code", "recovery_codes",
}


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (Decimal, UUID, date, datetime)):
        return str(value)
    return value


def _sanitize(changes: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _jsonable(value)
        for key, value in changes.items()
        if key not in REDACTED_KEYS
    }


async def record_audit(
    db: AsyncSession,
    *,
    user: User | None,
    action: str,
    module: str,
    entity: str,
    entity_id: str | UUID | None = None,
    changes: Optional[dict[str, Any]] = None,
    request: Request | None = None,
    on_behalf_of: UUID | str | None = None,
    correlation_id: str | None = None,
) -> None:
    log = AuditLog(
        tenant_id=user.tenant_id if user else None,
        actor_id=user.id if user else None,
        actor_email=user.email if user else "system",
        action=action,
        module=module,
        entity=entity,
        entity_id=str(entity_id) if entity_id else None,
        changes=_sanitize(changes or {}),
        ip_address=(
            request.headers.get("x-forwarded-for", "").split(",")[0].strip()
            or (request.client.host if request.client else None)
        ) if request else None,
        user_agent=request.headers.get("user-agent") if request else None,
        on_behalf_of_id=UUID(str(on_behalf_of)) if on_behalf_of else None,
        correlation_id=correlation_id
        or (request.headers.get("x-correlation-id") if request else None),
    )
    db.add(log)
