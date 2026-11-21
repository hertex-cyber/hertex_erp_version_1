"""Read/write service for governed settings (module 15A, M4).

Rules enforced here (see 15A-SETTINGS-IMPLEMENTATION-PLAN.md §4 / §7):

* S-REG-1 — only registry keys are writable (422 ``settings.unknown_key``).
* S-REG-2 — reads fail closed: an invalid stored value resolves to the registry
  default and logs a warning, so a tax posting never fails on a bad setting.
* layered resolution — precedence is the descriptor's declared scope order
  (code default -> env/deploy -> tenant -> branch -> user -> company).
* critical settings need a reason + an approver different from the actor.
* ``deploy_only`` keys are readable but not API-writable.
* ``immutable_after`` keys reject changes once a milestone is reached.
* every change is recorded in ``setting_changes`` and the audit trail, and bumps
  ``Tenant.settings_version`` so config caches invalidate.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings as app_settings
from app.core.events import publish
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.modules.identity.models import Tenant, User
from app.modules.settings.models import AppSetting, SettingChange, SettingSecret
from app.modules.settings.registry import SettingDescriptor, get_descriptor, is_secret_key

logger = logging.getLogger("hertex.settings")

_WARNED: dict[str, float] = {}
_UNSET = object()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def checksum(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _coerce_int(value: Any, descriptor: SettingDescriptor) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(
            f"{descriptor.key} must be an integer", code="settings.type_mismatch"
        ) from exc
    if isinstance(parsed, bool):
        raise ValidationError(f"{descriptor.key} must be an integer", code="settings.type_mismatch")
    return parsed


def _coerce_decimal(value: Any) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError("Value must be a decimal", code="settings.type_mismatch") from exc
    if not parsed.is_finite():
        raise ValidationError("Value must be finite", code="settings.type_mismatch")
    return parsed


def _validate_schema_node(value: Any, schema: dict[str, Any], key: str) -> None:
    expected = schema.get("type")
    if expected == "object" and not isinstance(value, dict):
        raise ValidationError(f"{key} must be an object", code="settings.validation_failed")
    if expected == "array" and not isinstance(value, list):
        raise ValidationError(f"{key} must be an array", code="settings.validation_failed")
    if isinstance(value, dict):
        for required in schema.get("required", []):
            if required not in value:
                raise ValidationError(
                    f"{key} is missing {required}", code="settings.validation_failed"
                )
        for name, child_schema in (schema.get("properties") or {}).items():
            if name in value:
                _validate_schema_node(value[name], child_schema, f"{key}.{name}")
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_schema_node(item, schema["items"], f"{key}[{index}]")
    if isinstance(value, str) and schema.get("pattern"):
        if not re.fullmatch(schema["pattern"], value):
            raise ValidationError(
                f"{key} has an invalid format", code="settings.validation_failed"
            )
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        if schema.get("minimum") is not None and value < schema["minimum"]:
            raise ValidationError(f"{key} is too small", code="settings.validation_failed")
        if schema.get("maximum") is not None and value > schema["maximum"]:
            raise ValidationError(f"{key} is too large", code="settings.validation_failed")


def validate_value(descriptor: SettingDescriptor, value: Any) -> Any:
    """Coerce + validate a raw value against the descriptor. Raises 422 on failure."""
    vtype = descriptor.type
    if vtype == "int":
        value = _coerce_int(value, descriptor)
    elif vtype == "decimal":
        value = _coerce_decimal(value)
    elif vtype == "duration":
        value = _coerce_int(value, descriptor)
    elif vtype == "bool":
        if isinstance(value, bool):
            pass
        elif isinstance(value, str) and value.lower() in {"true", "1", "yes", "on"}:
            value = True
        elif isinstance(value, str) and value.lower() in {"false", "0", "no", "off"}:
            value = False
        elif isinstance(value, int) and value in (0, 1):
            value = bool(value)
        else:
            raise ValidationError(
                f"{descriptor.key} must be a boolean", code="settings.type_mismatch"
            )
    elif vtype == "enum":
        if descriptor.choices and value not in descriptor.choices:
            raise ValidationError(
                f"{descriptor.key} must be one of {', '.join(descriptor.choices)}",
                code="settings.validation_failed",
            )
    elif vtype == "date":
        if not isinstance(value, str):
            raise ValidationError(f"{descriptor.key} must be an ISO date", code="settings.type_mismatch")
        try:
            datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValidationError(
                f"{descriptor.key} must be an ISO date", code="settings.type_mismatch"
            ) from exc
    elif vtype == "currency":
        if not isinstance(value, str) or not re.fullmatch(r"[A-Z]{3}", value):
            raise ValidationError(
                f"{descriptor.key} must be a 3-letter currency code", code="settings.type_mismatch"
            )
        value = value.upper()
    elif vtype in {"string", "secret"}:
        if not isinstance(value, str):
            raise ValidationError(f"{descriptor.key} must be a string", code="settings.type_mismatch")
    elif vtype == "json":
        if not isinstance(value, (dict, list)):
            raise ValidationError(
                f"{descriptor.key} must be a JSON object or array", code="settings.type_mismatch"
            )
        if descriptor.json_schema:
            _validate_schema_node(value, descriptor.json_schema, descriptor.key)
    else:
        raise ValidationError(f"Unknown value type {vtype}", code="settings.type_mismatch")

    if value is None:
        return None
    if descriptor.min is not None and _numeric(value) < Decimal(str(descriptor.min)):
        raise ValidationError(
            f"{descriptor.key} must be at least {descriptor.min}", code="settings.validation_failed"
        )
    if descriptor.max is not None and _numeric(value) > Decimal(str(descriptor.max)):
        raise ValidationError(
            f"{descriptor.key} must be at most {descriptor.max}", code="settings.validation_failed"
        )
    if descriptor.regex and isinstance(value, str) and not re.fullmatch(descriptor.regex, value):
        raise ValidationError(
            f"{descriptor.key} does not match the required format", code="settings.validation_failed"
        )
    return value


def _numeric(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, bool):
        return Decimal(int(value))
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _redacted_value(value: Any) -> dict[str, str]:
    return {"__redacted__": f"sha256:{checksum(value)}"}


def _safe_value(descriptor: SettingDescriptor | None, value: Any) -> Any:
    if descriptor is not None and descriptor.is_secret and value not in (None, ""):
        return _redacted_value(value)
    return value


def _reason_text(reason: str | None) -> str:
    return (reason or "").strip()


class SettingsService:
    """Stateless resolver + writer. Caches effective config per scope in-process."""

    def __init__(self) -> None:
        self._cache: dict[tuple[str, ...], tuple[int, float, dict[str, Any]]] = {}
        self._cache_ttl = float(app_settings.SETTINGS_CACHE_TTL_SECONDS)

    # ---------------------------------------------------------------- reads
    async def _tenant_version(self, db: AsyncSession, tenant_id: UUID | None) -> int:
        if tenant_id is None:
            return 1
        version = await db.scalar(
            select(Tenant.settings_version).where(Tenant.id == tenant_id)
        )
        return int(version or 1)

    def _scopes(
        self,
        tenant_id: UUID | None,
        branch_id: UUID | None,
        user_id: UUID | None,
        company_id: UUID | None,
    ) -> list[tuple[str, UUID | None]]:
        scopes: list[tuple[str, UUID | None]] = []
        if tenant_id is not None:
            scopes.append(("tenant", None))
        if branch_id is not None:
            scopes.append(("branch", branch_id))
        if user_id is not None:
            scopes.append(("user", user_id))
        if company_id is not None:
            scopes.append(("company", company_id))
        return scopes

    async def _load_rows(
        self, db: AsyncSession, tenant_id: UUID | None, scopes: list[tuple[str, UUID | None]]
    ) -> dict[str, dict[str, tuple[Any, str, str, int]]]:
        result: dict[str, dict[str, tuple[Any, str, str, int]]] = {}
        if not scopes:
            return result
        wanted = {scope_type: scope_id for scope_type, scope_id in scopes}
        stmt = select(AppSetting)
        if tenant_id is not None:
            stmt = stmt.where(AppSetting.tenant_id == tenant_id)
        else:
            stmt = stmt.where(AppSetting.tenant_id.is_(None))
        for row in (await db.scalars(stmt)).all():
            if row.scope_type not in wanted:
                continue
            if (row.scope_id or None) != (wanted[row.scope_type] or None):
                continue
            scope_rows = result.setdefault(row.key, {})
            if row.scope_type not in scope_rows:
                scope_rows[row.scope_type] = (
                    row.value,
                    row.scope_type,
                    str(row.scope_id or ""),
                    row.version,
                )
        return result

    def _env_snapshot(self, descriptors: list[SettingDescriptor]) -> dict[str, tuple[bool, Any]]:
        snapshot: dict[str, tuple[bool, Any]] = {}
        for descriptor in descriptors:
            env_var = descriptor.env_var
            if not env_var or env_var in snapshot:
                continue
            raw = os.environ.get(env_var)
            if raw is None:
                snapshot[env_var] = (False, None)
                continue
            try:
                candidate: Any = raw
                if descriptor.type == "json":
                    candidate = json.loads(raw)
                snapshot[env_var] = (True, validate_value(descriptor, candidate))
            except (ValidationError, ValueError, TypeError):
                self._warn_once(descriptor.key, raw)
                snapshot[env_var] = (True, descriptor.default)
        return snapshot

    def _resolve_one(
        self,
        descriptor: SettingDescriptor,
        rows: dict[str, tuple[Any, str, str, int]],
        env: dict[str, tuple[bool, Any]],
    ) -> tuple[Any, str, int]:
        if descriptor.env_var and descriptor.env_var in env:
            found, env_value = env[descriptor.env_var]
            if found:
                try:
                    value = validate_value(descriptor, env_value)
                except ValidationError:
                    self._warn_once(descriptor.key, env_value)
                    value = descriptor.default
                if descriptor.is_secret:
                    return None, "env", 0
                return value, "env", 0

        for scope in descriptor.scopes:
            row = rows.get(scope)
            if row is None:
                continue
            raw, scope_type, scope_id, stored_version = row
            try:
                value = validate_value(descriptor, raw)
            except ValidationError:
                self._warn_once(descriptor.key, raw)
                value = descriptor.default
            source = scope_type
            if scope_id and scope_type != "tenant":
                source = f"{scope_type}:{scope_id}"
            if descriptor.is_secret:
                return None, source, stored_version
            return value, source, stored_version

        if descriptor.is_secret:
            return None, "default", 0
        return descriptor.default, "default", 0

    async def resolve_all(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        branch_id: UUID | None = None,
        user_id: UUID | None = None,
        company_id: UUID | None = None,
    ) -> dict[str, Any]:
        """Effective configuration for a scope tuple: default -> env -> declared scopes."""
        from app.modules.settings.registry import BY_KEY

        version = await self._tenant_version(db, tenant_id)
        cache_key = (
            str(tenant_id),
            str(branch_id or ""),
            str(user_id or ""),
            str(company_id or ""),
        )
        cached = self._cache.get(cache_key)
        now = time.monotonic()
        if cached is not None and cached[0] == version and now - cached[1] < self._cache_ttl:
            return cached[2]

        rows = await self._load_rows(
            db, tenant_id, self._scopes(tenant_id, branch_id, user_id, company_id)
        )
        env = self._env_snapshot(list(BY_KEY.values()))
        resolved: dict[str, Any] = {}
        for descriptor in BY_KEY.values():
            value, _, _ = self._resolve_one(descriptor, rows.get(descriptor.key, {}), env)
            resolved[descriptor.key] = value
        self._cache[cache_key] = (version, now, resolved)
        return resolved

    async def get(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        key: str,
        branch_id: UUID | None = None,
        user_id: UUID | None = None,
        company_id: UUID | None = None,
        default: Any = None,
    ) -> Any:
        descriptor = get_descriptor(key)
        if descriptor is None:
            return default
        effective = await self.resolve_all(
            db,
            tenant_id=tenant_id,
            branch_id=branch_id,
            user_id=user_id,
            company_id=company_id,
        )
        return effective.get(descriptor.key, default)

    async def resolve(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        key: str,
        branch_id: UUID | None = None,
        user_id: UUID | None = None,
        company_id: UUID | None = None,
        default: Any = None,
    ) -> Any:
        return await self.get(
            db,
            tenant_id=tenant_id,
            key=key,
            branch_id=branch_id,
            user_id=user_id,
            company_id=company_id,
            default=default,
        )

    async def provenance(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        keys: list[str] | None = None,
        branch_id: UUID | None = None,
        user_id: UUID | None = None,
        company_id: UUID | None = None,
    ) -> list[dict]:
        """Per-key effective value + where it came from (for the settings screen)."""
        from app.modules.settings.registry import BY_KEY

        version = await self._tenant_version(db, tenant_id)
        rows = await self._load_rows(
            db, tenant_id, self._scopes(tenant_id, branch_id, user_id, company_id)
        )
        env = self._env_snapshot(list(BY_KEY.values()))
        effective = await self.resolve_all(
            db,
            tenant_id=tenant_id,
            branch_id=branch_id,
            user_id=user_id,
            company_id=company_id,
        )
        out: list[dict] = []
        for descriptor in BY_KEY.values():
            if keys and not any(key in (descriptor.key, *descriptor.aliases) for key in keys):
                continue
            value, source, stored_version = self._resolve_one(
                descriptor, rows.get(descriptor.key, {}), env
            )
            out.append(
                {
                    "key": descriptor.key,
                    "type": descriptor.type,
                    "module": descriptor.module,
                    "label": descriptor.label,
                    "help": descriptor.help,
                    "choices": descriptor.choices,
                    "min": descriptor.min,
                    "max": descriptor.max,
                    "regex": descriptor.regex,
                    "critical": descriptor.critical,
                    "deploy_only": descriptor.deploy_only,
                    "immutable_after": descriptor.immutable_after,
                    "scopes": list(descriptor.scopes),
                    "default": _safe_value(descriptor, descriptor.default),
                    "value": effective.get(descriptor.key, value),
                    "effective_source": source,
                    "stored_version": stored_version,
                    "config_version": version,
                    "data_impact": descriptor.data_impact or "none",
                    "is_secret": descriptor.is_secret,
                    "env_var": descriptor.env_var,
                    "json_schema": descriptor.json_schema,
                }
            )
        return out

    # --------------------------------------------------------------- writes
    async def set(
        self,
        db: AsyncSession,
        user: User,
        *,
        key: str,
        value: Any,
        scope: str = "tenant",
        scope_id: UUID | None = None,
        reason: str | None = None,
        version: int | None = None,
        source: str = "admin",
        request_id: str | None = None,
    ) -> dict:
        """Validate, apply (or stage for approval), audit, bump config version."""
        descriptor = get_descriptor(key)
        if descriptor is None:
            raise ValidationError(
                f"Unknown setting key '{key}'", code="settings.unknown_key"
            )
        if descriptor.deploy_only:
            raise ValidationError(
                f"'{descriptor.key}' is managed by the platform (deploy-only)",
                code="settings.deploy_only",
            )
        if scope not in descriptor.scopes:
            raise ValidationError(
                f"'{descriptor.key}' is not configurable at scope '{scope}'",
                code="settings.scope_forbidden",
            )
        reason = _reason_text(reason)
        if descriptor.critical and not reason:
            raise ValidationError(
                f"'{descriptor.key}' requires a reason", code="settings.reason_required"
            )

        if descriptor.is_secret:
            from app.modules.settings.secrets import secrets_service

            rendered = await secrets_service.set_secret(
                db, user, key=key, plaintext=str(value), reason=reason,
                request_id=request_id,
            )
            await self._publish_changed(user.tenant_id, key, request_id)
            self._invalidate(user.tenant_id)
            return rendered

        if value is None:
            value = descriptor.default
        value = validate_value(descriptor, value)

        if descriptor.immutable_after and await self._milestone_reached(
            db, user.tenant_id, descriptor.immutable_after
        ):
            raise ConflictError(
                f"'{descriptor.key}' cannot change after {descriptor.immutable_after.replace('_', ' ')}",
                code="settings.immutable",
            )

        existing = await self._find_row(db, user.tenant_id, descriptor.key, scope, scope_id)
        if version is not None and existing is not None and existing.version != version:
            raise ConflictError(
                f"'{descriptor.key}' was changed by someone else; reload and retry",
                code="settings.conflict",
            )

        critical_needs_approval = descriptor.critical and not self._is_approver(user)
        if critical_needs_approval:
            change = SettingChange(
                tenant_id=user.tenant_id,
                key=descriptor.key,
                scope_type=scope,
                scope_id=scope_id,
                old_value=existing.value if existing else descriptor.default,
                new_value=value,
                change_type="set",
                reason=reason,
                actor_id=user.id,
                actor_email=user.email,
                approval_state="pending",
                request_id=request_id,
            )
            db.add(change)
            await record_audit(
                db,
                user=user,
                action="settings.change.request",
                module="settings",
                entity="SettingChange",
                entity_id=change.id,
                changes={"key": descriptor.key, "old": existing.value if existing else descriptor.default, "new": value},
                request=None,
                correlation_id=request_id,
            )
            await db.commit()
            return {
                "key": descriptor.key,
                "approval_state": "pending",
                "id": str(change.id),
                "message": f"Change requires approval: {reason}",
            }

        now = datetime.now(timezone.utc)
        old_value = existing.value if existing else descriptor.default
        if existing is None:
            existing = AppSetting(
                tenant_id=user.tenant_id,
                key=descriptor.key,
                value=value,
                category=descriptor.module,
                description=descriptor.help,
                scope_type=scope,
                scope_id=scope_id,
                value_type=descriptor.type,
                is_secret=descriptor.is_secret,
                version=1,
                source=source,
                checksum=checksum(value),
                updated_by_id=user.id,
            )
            db.add(existing)
        else:
            existing.value = value
            existing.version += 1
            existing.category = descriptor.module
            existing.description = descriptor.help
            existing.value_type = descriptor.type
            existing.is_secret = descriptor.is_secret
            existing.checksum = checksum(value)
            existing.source = source
            existing.updated_by_id = user.id

        change = SettingChange(
            tenant_id=user.tenant_id,
            key=descriptor.key,
            scope_type=scope,
            scope_id=scope_id,
            old_value=old_value,
            new_value=value,
            change_type="set",
            reason=reason,
            actor_id=user.id,
            actor_email=user.email,
            approval_state="approved" if descriptor.critical else "none",
            approved_by_id=user.id if descriptor.critical else None,
            decided_at=now if descriptor.critical else None,
            request_id=request_id,
        )
        db.add(change)
        await self._bump_version(db, user.tenant_id)
        await record_audit(
            db,
            user=user,
            action="settings.setting.update",
            module="settings",
            entity="AppSetting",
            entity_id=existing.id,
            changes={"key": descriptor.key, "old": old_value, "new": value, "reason": reason},
            request=None,
            correlation_id=request_id,
        )
        await db.commit()
        self._invalidate(user.tenant_id)
        await self._publish_changed(user.tenant_id, descriptor.key, request_id)
        return {
            "key": descriptor.key,
            "value": value,
            "source": source or "admin",
            "applied": True,
        }

    async def unset(
        self,
        db: AsyncSession,
        user: User,
        *,
        key: str,
        scope: str = "tenant",
        scope_id: UUID | None = None,
        reason: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        descriptor = get_descriptor(key)
        if descriptor is None:
            raise ValidationError(f"Unknown setting key '{key}'", code="settings.unknown_key")
        if descriptor.deploy_only:
            raise ValidationError(f"'{descriptor.key}' is deploy-only", code="settings.deploy_only")
        if scope not in descriptor.scopes:
            raise ValidationError(
                f"'{descriptor.key}' is not configurable at scope '{scope}'",
                code="settings.scope_forbidden",
            )
        reason = _reason_text(reason)
        if descriptor.critical and not reason:
            raise ValidationError(
                f"'{descriptor.key}' requires a reason", code="settings.reason_required"
            )
        existing = await self._find_row(db, user.tenant_id, descriptor.key, scope, scope_id)
        if existing is None:
            return {"key": descriptor.key, "unset": False, "value": descriptor.default}
        old_value = existing.value

        if descriptor.critical:
            change = SettingChange(
                tenant_id=user.tenant_id,
                key=descriptor.key,
                scope_type=scope,
                scope_id=scope_id,
                old_value=old_value,
                new_value=None,
                change_type="unset",
                reason=reason,
                actor_id=user.id,
                actor_email=user.email,
                approval_state="pending",
                request_id=request_id,
            )
            db.add(change)
            await record_audit(
                db,
                user=user,
                action="settings.change.request",
                module="settings",
                entity="SettingChange",
                entity_id=change.id,
                changes={"key": descriptor.key, "old": old_value, "new": None, "reason": reason},
                request=None,
                correlation_id=request_id,
            )
            await db.commit()
            return {
                "key": descriptor.key,
                "approval_state": "pending",
                "id": str(change.id),
                "message": f"Unset requires approval: {reason}",
            }

        await db.delete(existing)
        db.add(
            SettingChange(
                tenant_id=user.tenant_id,
                key=descriptor.key,
                scope_type=scope,
                scope_id=scope_id,
                old_value=old_value,
                new_value=None,
                change_type="unset",
                reason=reason,
                actor_id=user.id,
                actor_email=user.email,
                approval_state="none",
                request_id=request_id,
            )
        )
        await self._bump_version(db, user.tenant_id)
        await record_audit(
            db,
            user=user,
            action="settings.setting.unset",
            module="settings",
            entity="AppSetting",
            entity_id=existing.id,
            changes={"key": descriptor.key, "old": old_value},
            request=None,
            correlation_id=request_id,
        )
        await db.commit()
        self._invalidate(user.tenant_id)
        await self._publish_changed(user.tenant_id, descriptor.key, request_id)
        return {"key": descriptor.key, "unset": True, "value": descriptor.default}

    # ------------------------------------------------------------ approvals
    async def approve(self, db: AsyncSession, user: User, change_id: UUID, *, accept: bool) -> dict:
        change = await db.scalar(select(SettingChange).where(SettingChange.id == change_id))
        if change is None:
            raise NotFoundError("Setting change not found")
        if change.approval_state != "pending":
            raise ConflictError("Setting change is not pending approval")
        if change.actor_id == user.id:
            raise ForbiddenError("You cannot approve your own change")
        descriptor = get_descriptor(change.key)
        if descriptor is None:
            raise ConflictError("Setting key no longer exists")
        if descriptor.deploy_only:
            raise ValidationError(
                f"'{descriptor.key}' is deploy-only", code="settings.deploy_only"
            )
        if change.scope_type not in descriptor.scopes:
            raise ValidationError(
                f"'{descriptor.key}' is not configurable at scope '{change.scope_type}'",
                code="settings.scope_forbidden",
            )
        reason = _reason_text(change.reason)
        if descriptor.critical and not reason:
            raise ValidationError(
                f"'{descriptor.key}' requires a reason", code="settings.reason_required"
            )

        value: Any = None
        if accept:
            if change.change_type not in {"set", "unset"}:
                raise ValidationError("Unsupported change type", code="settings.validation_failed")
            if change.change_type == "set":
                value = validate_value(descriptor, change.new_value)
            if descriptor.immutable_after and await self._milestone_reached(
                db, change.tenant_id, descriptor.immutable_after
            ):
                raise ConflictError(
                    f"'{descriptor.key}' cannot change after {descriptor.immutable_after.replace('_', ' ')}",
                    code="settings.immutable",
                )
            change.approval_state = "approved"
            change.approved_by_id = user.id
            change.decided_at = datetime.now(timezone.utc)
            change.reason = reason
            await self._apply_change(db, change, user=user, descriptor=descriptor, value=value)
        else:
            change.approval_state = "rejected"
            change.approved_by_id = user.id
            change.decided_at = datetime.now(timezone.utc)

        await record_audit(
            db,
            user=user,
            action=f"settings.change.{'approve' if accept else 'reject'}",
            module="settings",
            entity="SettingChange",
            entity_id=change.id,
            changes={
                "key": descriptor.key,
                "old": _safe_value(descriptor, change.old_value),
                "new": _safe_value(descriptor, value if accept else change.new_value),
                "reason": reason,
            },
            request=None,
            correlation_id=change.request_id,
        )
        await db.commit()
        self._invalidate(change.tenant_id)
        if accept:
            await self._publish_changed(change.tenant_id, descriptor.key, change.request_id)
        return {"key": descriptor.key, "approval_state": change.approval_state}

    async def _apply_change(
        self,
        db: AsyncSession,
        change: SettingChange,
        *,
        user: User,
        descriptor: SettingDescriptor,
        value: Any,
    ) -> None:
        if descriptor.is_secret:
            from app.modules.settings.secrets import secrets_service

            if change.change_type == "unset":
                await secrets_service.delete(db, user, key=change.key)
            else:
                await secrets_service.set_secret(
                    db,
                    user,
                    key=change.key,
                    plaintext=str(value),
                    reason=change.reason,
                    request_id=change.request_id,
                )
            await self._bump_version(db, change.tenant_id)
            return

        existing = await self._find_row(
            db, change.tenant_id, descriptor.key, change.scope_type, change.scope_id
        )
        if change.change_type == "unset":
            if existing is not None:
                await db.delete(existing)
            await self._bump_version(db, change.tenant_id)
            return
        await self._find_or_create_and_set(
            db, change, descriptor=descriptor, value=value, actor_id=user.id
        )

    async def _find_or_create_and_set(
        self,
        db: AsyncSession,
        change: SettingChange,
        *,
        descriptor: SettingDescriptor,
        value: Any,
        actor_id: UUID | None,
    ) -> None:
        existing = await self._find_row(
            db, change.tenant_id, descriptor.key, change.scope_type, change.scope_id
        )
        if existing is None:
            existing = AppSetting(
                tenant_id=change.tenant_id,
                key=descriptor.key,
                value=value,
                category=descriptor.module,
                description=descriptor.help,
                scope_type=change.scope_type,
                scope_id=change.scope_id,
                value_type=descriptor.type,
                is_secret=descriptor.is_secret,
                version=1,
                source="admin",
                checksum=checksum(value),
                updated_by_id=actor_id,
            )
            db.add(existing)
        else:
            existing.value = value
            existing.version += 1
            existing.category = descriptor.module
            existing.description = descriptor.help
            existing.value_type = descriptor.type
            existing.is_secret = descriptor.is_secret
            existing.source = "admin"
            existing.checksum = checksum(value)
            existing.updated_by_id = actor_id
        await self._bump_version(db, change.tenant_id)

    # ------------------------------------------------------------ utilities
    def _is_approver(self, user: User) -> bool:
        return user.is_superuser or user.has_any_permission(["settings.change.approve"])

    async def _find_row(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        key: str,
        scope_type: str,
        scope_id: UUID | None,
    ) -> AppSetting | None:
        stmt = select(AppSetting).where(
            AppSetting.key == key,
            AppSetting.scope_type == scope_type,
        )
        if tenant_id is not None:
            stmt = stmt.where(AppSetting.tenant_id == tenant_id)
        else:
            stmt = stmt.where(AppSetting.tenant_id.is_(None))
        if scope_id is not None:
            stmt = stmt.where(AppSetting.scope_id == scope_id)
        else:
            stmt = stmt.where(AppSetting.scope_id.is_(None))
        return await db.scalar(stmt)

    async def _bump_version(self, db: AsyncSession, tenant_id: UUID | None) -> None:
        """Increment the tenant config version so every cache invalidates."""
        if tenant_id is None:
            return
        from sqlalchemy import update as _update

        await db.execute(
            _update(Tenant)
            .where(Tenant.id == tenant_id)
            .values(settings_version=Tenant.settings_version + 1)
        )

    async def _publish_changed(
        self, tenant_id: UUID | None, key: str, request_id: str | None = None
    ) -> None:
        await publish(
            "settings.changed",
            {"tenant_id": str(tenant_id) if tenant_id else None, "key": key},
            correlation_id=request_id,
        )

    def _warn_once(self, key: str, value: Any) -> None:
        now = time.monotonic()
        if now - _WARNED.get(key, 0.0) < 3600:
            return
        _WARNED[key] = now
        logger.warning(
            "settings.invalid_value",
            extra={"key": key, "value_type": type(value).__name__},
        )

    def _invalidate(self, tenant_id: UUID | None) -> None:
        prefix = str(tenant_id)
        for key in [k for k in self._cache if k[0] == prefix]:
            self._cache.pop(key, None)

    async def _milestone_reached(
        self, db: AsyncSession, tenant_id: UUID | None, milestone: str
    ) -> bool:
        """Has the tenant progressed past the point where a setting is still editable?"""
        from app.modules.finance.models import FinancialPeriod, JournalEntry
        from app.modules.inventory.models import StockMove
        from app.modules.sales.models import SalesOrder

        target: Any
        extra = None
        if milestone == "finance_first_posting":
            target = JournalEntry
        elif milestone == "stock_exists":
            target = StockMove
        elif milestone == "sales_exists":
            target = SalesOrder
        elif milestone == "fiscal_closed":
            target = FinancialPeriod
            extra = FinancialPeriod.status == "closed"
        else:
            return False

        stmt = select(func.count()).select_from(target)
        if tenant_id is not None and hasattr(target, "tenant_id"):
            stmt = stmt.where(target.tenant_id == tenant_id)
        if extra is not None:
            stmt = stmt.where(extra)
        return int(await db.scalar(stmt) or 0) > 0

    async def history(
        self, db: AsyncSession, *, tenant_id: UUID | None, key: str | None = None, limit: int = 50
    ) -> list[dict]:
        stmt = select(SettingChange).order_by(SettingChange.created_at.desc()).limit(limit)
        if key:
            stmt = select(SettingChange).where(SettingChange.key == key).order_by(
                SettingChange.created_at.desc()
            ).limit(limit)
        if tenant_id is not None:
            stmt = stmt.where(SettingChange.tenant_id == tenant_id)
        rows = (await db.scalars(stmt)).all()
        result: list[dict] = []
        for row in rows:
            descriptor = get_descriptor(row.key)
            result.append(
                {
                    "id": str(row.id),
                    "key": descriptor.key if descriptor else row.key,
                    "old_value": _safe_value(descriptor, row.old_value),
                    "new_value": _safe_value(descriptor, row.new_value),
                    "change_type": row.change_type,
                    "reason": row.reason,
                    "actor": row.actor_email,
                    "actor_id": str(row.actor_id) if row.actor_id else None,
                    "approval_state": row.approval_state,
                    "approved_by": str(row.approved_by_id) if row.approved_by_id else None,
                    "created_at": row.created_at,
                }
            )
        return result

    async def pending_changes(self, db: AsyncSession, *, tenant_id: UUID | None) -> list[dict]:
        stmt = select(SettingChange).where(SettingChange.approval_state == "pending")
        if tenant_id is not None:
            stmt = stmt.where(SettingChange.tenant_id == tenant_id)
        stmt = stmt.order_by(SettingChange.created_at.desc())
        rows = (await db.scalars(stmt)).all()
        result: list[dict] = []
        for row in rows:
            descriptor = get_descriptor(row.key)
            result.append(
                {
                    "id": str(row.id),
                    "key": descriptor.key if descriptor else row.key,
                    "old_value": _safe_value(descriptor, row.old_value),
                    "new_value": _safe_value(descriptor, row.new_value),
                    "reason": row.reason,
                    "actor": row.actor_email,
                    "request_id": row.request_id,
                    "created_at": row.created_at,
                }
            )
        return result

    async def drift_report(self, db: AsyncSession, *, tenant_id: UUID | None) -> dict:
        stmt = select(AppSetting)
        if tenant_id is not None:
            stmt = stmt.where(AppSetting.tenant_id == tenant_id)
        rows = (await db.scalars(stmt)).all()

        secret_stmt = select(SettingSecret)
        if tenant_id is not None:
            secret_stmt = secret_stmt.where(SettingSecret.tenant_id == tenant_id)
        secret_rows = (await db.scalars(secret_stmt)).all()

        change_stmt = select(SettingChange)
        if tenant_id is not None:
            change_stmt = change_stmt.where(SettingChange.tenant_id == tenant_id)
        changes = (await db.scalars(change_stmt)).all()

        unknown_keys: list[dict] = []
        invalid_values: list[dict] = []
        checksum_mismatches: list[dict] = []
        schemas_missing: list[dict] = []
        secrets_outside_registry: list[dict] = []
        seen_schemas: set[str] = set()

        for row in rows:
            descriptor = get_descriptor(row.key)
            item = {"key": row.key, "scope": row.scope_type, "id": str(row.id)}
            if descriptor is None:
                unknown_keys.append(item)
                continue
            if row.is_secret and not descriptor.is_secret:
                secrets_outside_registry.append(item)
            if not row.is_secret:
                if row.checksum and row.checksum != checksum(row.value):
                    checksum_mismatches.append(item)
                try:
                    validate_value(descriptor, row.value)
                except ValidationError as exc:
                    invalid_values.append({**item, "code": exc.code})
            if descriptor.type == "json" and not descriptor.json_schema:
                if descriptor.key not in seen_schemas:
                    schemas_missing.append({"key": descriptor.key})
                    seen_schemas.add(descriptor.key)

        for row in secret_rows:
            if not is_secret_key(row.key):
                secrets_outside_registry.append({"key": row.key, "id": str(row.id), "store": "vault"})

        grouped: dict[tuple[str, str, str], list[AppSetting]] = {}
        for row in rows:
            grouped.setdefault(
                (row.key, row.scope_type, str(row.scope_id or "")), []
            ).append(row)
        scope_conflicts: list[dict] = []
        for (key, scope_type, scope_id), group in grouped.items():
            if len(group) > 1:
                scope_conflicts.append(
                    {
                        "key": key,
                        "scope": scope_type,
                        "scope_id": scope_id,
                        "rows": [str(row.id) for row in group],
                        "reason": "duplicate_effective_scope",
                    }
                )
            descriptor = get_descriptor(key)
            if descriptor is not None and scope_type not in descriptor.scopes:
                scope_conflicts.append(
                    {
                        "key": key,
                        "scope": scope_type,
                        "scope_id": scope_id,
                        "rows": [str(row.id) for row in group],
                        "reason": "scope_not_declared",
                    }
                )

        critical_changes: list[dict] = []
        for change in changes:
            descriptor = get_descriptor(change.key)
            if descriptor is None or not descriptor.critical:
                continue
            missing_reason = not _reason_text(change.reason)
            missing_approval = (
                change.change_type in {"set", "unset"} and change.approval_state == "none"
            )
            if missing_reason or missing_approval:
                critical_changes.append(
                    {
                        "id": str(change.id),
                        "key": descriptor.key,
                        "reason": "missing_reason" if missing_reason else "missing_approval",
                        "approval_state": change.approval_state,
                    }
                )

        counts = {
            "unknown_keys": len(unknown_keys),
            "invalid_values": len(invalid_values),
            "checksum_mismatches": len(checksum_mismatches),
            "schemas_missing": len(schemas_missing),
            "secrets_outside_registry": len(secrets_outside_registry),
            "scope_conflicts": len(scope_conflicts),
            "critical_changes_without_governance": len(critical_changes),
        }
        return {
            "unknown_keys": unknown_keys,
            "invalid_values": invalid_values,
            "checksum_mismatches": checksum_mismatches,
            "schemas_missing": schemas_missing,
            "secrets_outside_registry": secrets_outside_registry,
            "scope_conflicts": scope_conflicts,
            "critical_changes_without_governance": critical_changes,
            "counts": counts,
            "total": sum(counts.values()),
        }

    async def invalid_value_count(self, db: AsyncSession, *, tenant_id: UUID | None) -> int:
        report = await self.drift_report(db, tenant_id=tenant_id)
        return report["counts"]["invalid_values"] + report["counts"]["checksum_mismatches"]


settings_service = SettingsService()
