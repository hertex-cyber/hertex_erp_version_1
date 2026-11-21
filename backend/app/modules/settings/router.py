"""Settings & numbering API (module 15 / 15A).

Two governed halves:

* **Settings** — registry-driven, typed, layered, audited (no free-form JSON).
* **Numbering** — atomic allocation, preview, status, voids, offline blocks and
  the gap/usage reports that make gaps explainable (GST Rule 46).
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_all_permissions, require_permissions
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.settings import patterns
from app.modules.settings.models import (
    NumberAllocation,
    NumberSequence,
    NumberSequenceBlock,
)
from app.modules.settings.numbering import numbering
from app.modules.settings.registry import DESCRIPTORS, is_secret_key, modules, validate_secret_key
from app.modules.settings.schemas import (
    AllocateRequest,
    AllocationRead,
    BlockCreate,
    BlockRead,
    BlockReturn,
    ChangeRead,
    EffectiveSetting,
    GapReport,
    RegistryItem,
    SecretRead,
    SecretRewrap,
    SecretRotate,
    SecretWrite,
    SequenceCreate,
    SequenceNext,
    SequencePreview,
    SequencePreviewRequest,
    SequenceRead,
    SequenceStatus,
    SequenceUpdate,
    SequenceValidationResult,
    SettingWrite,
    SettingWriteResult,
    UsageReport,
    VoidRequest,
)
from app.modules.settings.secrets import secrets_service
from app.modules.settings.service import settings_service

router = APIRouter(prefix="/settings")

read_settings = require_permissions("settings.setting.read")
write_settings = require_permissions("settings.setting.update")
manage_system = require_permissions("system.settings.manage")
manage_secrets = require_permissions("settings.secret.manage")
read_settings_and_audit = require_all_permissions("settings.setting.read", "system.audit.read")
read_sequences = require_permissions("settings.sequence.read")
create_sequences = require_permissions("settings.sequence.create")
update_sequences = require_permissions("settings.sequence.update")
delete_sequences = require_permissions("settings.sequence.delete")
allocate_sequences = require_permissions("settings.sequence.allocate", "settings.sequence.update")
audit_read = require_permissions("system.audit.read", "system.settings.manage")


def _dialect_name(db: AsyncSession) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "postgresql"


# =============================================================================
# Registry & values
# =============================================================================
@router.get("/registry", response_model=list[RegistryItem], tags=["Settings · Registry"])
async def list_registry(
    module: Optional[str] = None,
    user: User = Depends(read_settings),
):
    """The allow-list of configurable keys. Contains no tenant values."""
    items = []
    for descriptor in DESCRIPTORS:
        if module and descriptor.module != module:
            continue
        items.append(
            RegistryItem(
                key=descriptor.key,
                type=descriptor.type,
                module=descriptor.module,
                label=descriptor.label,
                help=descriptor.help,
                choices=list(descriptor.choices) if descriptor.choices else None,
                min=descriptor.min,
                max=descriptor.max,
                regex=descriptor.regex,
                critical=descriptor.critical,
                deploy_only=descriptor.deploy_only,
                 immutable_after=descriptor.immutable_after,
                 scopes=list(descriptor.scopes),
                 default=descriptor.default,
                 data_impact=descriptor.data_impact or "none",
                 is_secret=descriptor.is_secret,
                 env_var=descriptor.env_var,
                 json_schema=descriptor.json_schema,
             )

        )
    return items


@router.get("/registry/modules", response_model=list[str], tags=["Settings · Registry"])
async def list_registry_modules(user: User = Depends(read_settings)):
    return modules()


@router.get("/values", response_model=dict, tags=["Settings · Values"])
async def list_values(
    q: Optional[str] = None,
    module: Optional[str] = None,
    branch_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=500),
    user: User = Depends(read_settings),
    db: AsyncSession = Depends(get_db),
):
    """Effective configuration for the caller, with per-key provenance."""
    rows = await settings_service.provenance(
        db, tenant_id=user.tenant_id, branch_id=branch_id, user_id=user.id
    )
    if module:
        rows = [row for row in rows if row["module"] == module]
    if q:
        needle = q.lower()
        rows = [
            row
            for row in rows
            if needle in row["key"].lower()
            or needle in row["label"].lower()
            or needle in (row["help"] or "").lower()
        ]
    total = len(rows)
    start = (page - 1) * size
    page_rows = rows[start : start + size]
    return {
        "items": page_rows,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
        "modules": modules(),
    }


@router.get("/values/{key}", response_model=EffectiveSetting, tags=["Settings · Values"])
async def get_value(
    key: str,
    branch_id: Optional[UUID] = None,
    user: User = Depends(read_settings),
    db: AsyncSession = Depends(get_db),
):
    rows = await settings_service.provenance(
        db, tenant_id=user.tenant_id, keys=[key], branch_id=branch_id, user_id=user.id
    )
    if not rows:
        raise NotFoundError(f"Unknown setting key '{key}'")
    return EffectiveSetting(**rows[0])


@router.put("/values/{key}", response_model=SettingWriteResult, tags=["Settings · Values"])
async def write_value(
    key: str,
    payload: SettingWrite,
    user: User = Depends(write_settings),
    db: AsyncSession = Depends(get_db),
):
    result = await settings_service.set(
        db,
        user,
        key=key,
        value=payload.value,
        scope=payload.scope,
        scope_id=payload.scope_id,
        reason=payload.reason,
        version=payload.version,
    )
    return SettingWriteResult(**result)


@router.delete("/values/{key}", response_model=SettingWriteResult, tags=["Settings · Values"])
async def unset_value(
    key: str,
    scope: str = Query("tenant"),
    scope_id: Optional[UUID] = None,
    reason: Optional[str] = None,
    user: User = Depends(write_settings),
    db: AsyncSession = Depends(get_db),
):
    result = await settings_service.unset(
        db, user, key=key, scope=scope, scope_id=scope_id, reason=reason
    )
    return SettingWriteResult(
        key=key,
        value=result.get("value"),
        applied=bool(result.get("unset")),
        approval_state=result.get("approval_state"),
        id=result.get("id"),
        message=result.get("message"),
    )


@router.get("/values/{key}/history", response_model=list[ChangeRead], tags=["Settings · Values"])
async def value_history(
    key: str,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(read_settings_and_audit),
    db: AsyncSession = Depends(get_db),
):
    return await settings_service.history(db, tenant_id=user.tenant_id, key=key, limit=limit)


@router.get("/features", response_model=dict, tags=["Settings · Features"])
async def feature_flags(
    user: User = Depends(read_settings),
    db: AsyncSession = Depends(get_db),
):
    effective = await settings_service.resolve_all(
        db, tenant_id=user.tenant_id, user_id=user.id
    )
    return {
        key: value for key, value in effective.items() if key.startswith("features.")
    }


# =============================================================================
# Critical-change approvals
# =============================================================================
@router.get("/changes", response_model=list[ChangeRead], tags=["Settings · Changes"])
async def list_changes(
    pending_only: bool = False,
    limit: int = Query(50, ge=1, le=200),
    user: User = Depends(manage_system),
    db: AsyncSession = Depends(get_db),
):
    if pending_only:
        rows = await settings_service.pending_changes(db, tenant_id=user.tenant_id)
        return [ChangeRead(**row) for row in rows[:limit]]
    return await settings_service.history(db, tenant_id=user.tenant_id, limit=limit)


@router.post("/changes/{change_id}/approve", response_model=ChangeRead, tags=["Settings · Changes"])
async def approve_change(
    change_id: UUID,
    user: User = Depends(manage_system),
    db: AsyncSession = Depends(get_db),
):
    result = await settings_service.approve(db, user, change_id, accept=True)
    return ChangeRead(key=result["key"], approval_state=result["approval_state"], actor=user.email)


@router.post("/changes/{change_id}/reject", response_model=ChangeRead, tags=["Settings · Changes"])
async def reject_change(
    change_id: UUID,
    user: User = Depends(manage_system),
    db: AsyncSession = Depends(get_db),
):
    result = await settings_service.approve(db, user, change_id, accept=False)
    return ChangeRead(key=result["key"], approval_state=result["approval_state"], actor=user.email)


# =============================================================================
# Secrets
# =============================================================================
@router.get("/secrets", response_model=list[SecretRead], tags=["Settings · Secrets"])
async def list_secrets(
    user: User = Depends(manage_secrets),
    db: AsyncSession = Depends(get_db),
):
    rows = await secrets_service.list_masked(db, tenant_id=user.tenant_id)
    return [SecretRead(**row) for row in rows if is_secret_key(row["key"])]


@router.put("/secrets/{key}", response_model=SecretRead, tags=["Settings · Secrets"])
async def write_secret(
    key: str,
    payload: SecretWrite,
    user: User = Depends(manage_secrets),
    db: AsyncSession = Depends(get_db),
):
    validate_secret_key(key)
    result = await secrets_service.set_secret(
        db, user, key=key, plaintext=payload.value, reason=payload.reason or ""
    )
    return SecretRead(**result)


@router.delete("/secrets/{key}", tags=["Settings · Secrets"])
async def delete_secret(
    key: str,
    user: User = Depends(manage_secrets),
    db: AsyncSession = Depends(get_db),
):
    validate_secret_key(key)
    await secrets_service.delete(db, user, key=key)
    return {"message": f"Secret {key} deleted"}


@router.post("/secrets/{key}/rotate", response_model=SecretRead, tags=["Settings · Secrets"])
async def rotate_secret(
    key: str,
    payload: SecretRotate,
    user: User = Depends(manage_secrets),
    db: AsyncSession = Depends(get_db),
):
    validate_secret_key(key)
    result = await secrets_service.rotate(
        db, user, key=key, plaintext=payload.value, window_hours=payload.window_hours
    )
    return SecretRead(
        key=result["key"],
        status=result["status"],
        rotation_ends_at=result["window_ends_at"],
        configured=True,
    )


@router.post("/secrets/{key}/rewrap", response_model=SecretRead, tags=["Settings · Secrets"])
async def rewrap_secret(
    key: str,
    payload: SecretRewrap,
    user: User = Depends(manage_secrets),
    db: AsyncSession = Depends(get_db),
):
    validate_secret_key(key)
    result = await secrets_service.rewrap_secret(
        db, user, key=key, key_version=payload.key_version
    )
    return SecretRead(**result)


@router.post("/secrets/{key}/commit", response_model=SecretRead, tags=["Settings · Secrets"])
async def commit_secret(
    key: str,
    user: User = Depends(manage_secrets),
    db: AsyncSession = Depends(get_db),
):
    validate_secret_key(key)
    result = await secrets_service.commit(db, user, key=key)
    return SecretRead(key=result["key"], status=result["status"], configured=True)


@router.post("/secrets/{key}/rollback", response_model=SecretRead, tags=["Settings · Secrets"])
async def rollback_secret(
    key: str,
    user: User = Depends(manage_secrets),
    db: AsyncSession = Depends(get_db),
):
    validate_secret_key(key)
    result = await secrets_service.rollback(db, user, key=key)
    return SecretRead(key=result["key"], status=result["status"], configured=True)


# =============================================================================
# Sequences
# =============================================================================
def _sequence_response(db: AsyncSession, sequence: NumberSequence) -> dict:
    return {
        "id": sequence.id,
        "key": sequence.key,
        "doc_type": sequence.doc_type,
        "owner_module": sequence.owner_module,
        "pattern": sequence.pattern,
        "prefix": sequence.prefix,
        "suffix": sequence.suffix,
        "next_number": sequence.next_number,
        "padding": sequence.padding,
        "start_number": sequence.start_number,
        "increment": sequence.increment,
        "implementation": sequence.implementation,
        "reset_policy": sequence.reset_policy,
        "branch_id": sequence.branch_id,
        "gstin": sequence.gstin,
        "max_length": sequence.max_length,
        "irp_safe": sequence.irp_safe,
        "manual_allowed": sequence.manual_allowed,
        "status": sequence.status,
        "is_active": sequence.is_active,
        "created_at": sequence.created_at,
    }


@router.get("/sequences", response_model=dict, tags=["Settings · Sequences"])
async def list_sequences(
    q: Optional[str] = None,
    owner_module: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(100, ge=1, le=200),
    user: User = Depends(read_sequences),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NumberSequence)
    count_stmt = select(func.count()).select_from(NumberSequence)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(NumberSequence.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(NumberSequence.tenant_id == user.tenant_id)
    if owner_module:
        stmt = stmt.where(NumberSequence.owner_module == owner_module)
        count_stmt = count_stmt.where(NumberSequence.owner_module == owner_module)
    if q:
        needle = f"%{q}%"
        stmt = stmt.where(
            NumberSequence.key.ilike(needle) | NumberSequence.pattern.ilike(needle)
        )
    total = int(await db.scalar(count_stmt) or 0)
    stmt = stmt.order_by(NumberSequence.owner_module, NumberSequence.key)
    stmt = stmt.offset((page - 1) * size).limit(size)
    sequences = list((await db.scalars(stmt)).all())

    items = []
    for sequence in sequences:
        status = await numbering.status(
            db, tenant_id=sequence.tenant_id, key=sequence.key
        )
        payload = _sequence_response(db, sequence)
        payload.update(
            {
                "fiscal_year": status["fiscal_year"],
                "allocated_count": status["allocated_count"],
                "period_next_number": status["next_number"],
                "preview": status["preview"],
                "open_blocks": status["open_blocks"],
                "period_status": status["period_status"],
                "locked": sequence.status == "locked",
            }
        )
        items.append(payload)
    return {
        "items": items,
        "total": total,
        "page": page,
        "size": size,
        "pages": max(1, (total + size - 1) // size),
    }


@router.post("/sequences/validate", response_model=SequenceValidationResult, tags=["Settings · Sequences"])
async def validate_sequence(
    payload: SequenceCreate,
    user: User = Depends(read_sequences),
):
    problems = patterns.validate(
        payload.pattern,
        doc_type=payload.doc_type,
        padding=payload.padding,
        prefix=payload.prefix,
        suffix=payload.suffix,
        irp_safe=payload.irp_safe,
        max_length=payload.max_length,
        allowed_chars_regex=payload.allowed_chars_regex,
        doc_code=payload.prefix,
    )
    sample = None
    if payload.pattern:
        try:
            sample = patterns.worst_case(
                payload.pattern,
                padding=payload.padding,
                prefix=payload.prefix,
                suffix=payload.suffix,
                doc_code=payload.prefix,
            )
        except patterns.PatternError:
            sample = None
    return SequenceValidationResult(
        key=payload.key,
        pattern=payload.pattern,
        sample=sample,
        problems=problems,
        valid=not problems,
    )


@router.post("/sequences", response_model=SequenceRead, status_code=201, tags=["Settings · Sequences"])
async def create_sequence(
    payload: SequenceCreate,
    user: User = Depends(create_sequences),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(
        select(NumberSequence).where(
            NumberSequence.key == payload.key,
            NumberSequence.tenant_id == user.tenant_id,
            NumberSequence.branch_id.is_(None),
        )
    )
    if existing is not None:
        raise ConflictError(f"Series '{payload.key}' already exists")
    problems = patterns.validate(
        payload.pattern,
        doc_type=payload.doc_type,
        padding=payload.padding,
        prefix=payload.prefix,
        suffix=payload.suffix,
        irp_safe=payload.irp_safe,
        max_length=payload.max_length,
        allowed_chars_regex=payload.allowed_chars_regex,
        doc_code=payload.prefix,
    )
    if problems:
        raise ValidationError("; ".join(problems), code="numbering.pattern_invalid")
    sequence = NumberSequence(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        **payload.model_dump(),
    )
    db.add(sequence)
    await db.flush()
    await db.commit()
    await db.refresh(sequence)
    return _sequence_response(db, sequence)


@router.get("/sequences/{key}", response_model=SequenceStatus, tags=["Settings · Sequences"])
async def get_sequence(
    key: str,
    fiscal_year: Optional[str] = None,
    user: User = Depends(read_sequences),
    db: AsyncSession = Depends(get_db),
):
    return SequenceStatus(**await numbering.status(db, tenant_id=user.tenant_id, key=key, fiscal_year=fiscal_year))


@router.patch("/sequences/{key}", response_model=SequenceRead, tags=["Settings · Sequences"])
async def update_sequence(
    key: str,
    payload: SequenceUpdate,
    user: User = Depends(update_sequences),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NumberSequence).where(NumberSequence.key == key)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(NumberSequence.tenant_id == user.tenant_id)
    sequence = await db.scalar(stmt)
    if sequence is None:
        raise NotFoundError(f"Numbering series '{key}' not found")
    changes = payload.model_dump(exclude_unset=True)
    await numbering.assert_mutable(db, sequence, changes)
    candidate = {
        "pattern": changes.get("pattern", sequence.pattern),
        "doc_type": changes.get("doc_type", sequence.doc_type),
        "padding": changes.get("padding", sequence.padding),
        "prefix": changes.get("prefix", sequence.prefix),
        "suffix": changes.get("suffix", sequence.suffix),
        "irp_safe": changes.get("irp_safe", sequence.irp_safe),
        "max_length": changes.get("max_length", sequence.max_length),
        "allowed_chars_regex": changes.get("allowed_chars_regex", sequence.allowed_chars_regex),
    }
    problems = patterns.validate(
        candidate["pattern"],
        doc_type=candidate["doc_type"],
        padding=candidate["padding"],
        prefix=candidate["prefix"],
        suffix=candidate["suffix"],
        irp_safe=candidate["irp_safe"],
        max_length=candidate["max_length"],
        allowed_chars_regex=candidate["allowed_chars_regex"],
    )
    if problems:
        raise ValidationError("; ".join(problems), code="numbering.pattern_invalid")
    for field, value in changes.items():
        setattr(sequence, field, value)
    await db.commit()
    await db.refresh(sequence)
    return _sequence_response(db, sequence)


@router.delete("/sequences/{key}", tags=["Settings · Sequences"])
async def delete_sequence(
    key: str,
    user: User = Depends(delete_sequences),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NumberSequence).where(NumberSequence.key == key)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(NumberSequence.tenant_id == user.tenant_id)
    sequence = await db.scalar(stmt)
    if sequence is None:
        raise NotFoundError(f"Numbering series '{key}' not found")
    allocations = int(
        await db.scalar(
            select(func.count())
            .select_from(NumberAllocation)
            .where(NumberAllocation.sequence_id == sequence.id)
        )
        or 0
    )
    if allocations:
        raise ConflictError(
            "This series has issued numbers; deactivate it instead of deleting"
        )
    await db.delete(sequence)
    await db.commit()
    return {"message": f"Series {key} deleted"}


@router.post("/sequences/{key}/preview", response_model=SequencePreview, tags=["Settings · Sequences"])
async def preview_sequence(
    key: str,
    payload: SequencePreviewRequest | None = None,
    user: User = Depends(read_sequences),
    db: AsyncSession = Depends(get_db),
):
    payload = payload or SequencePreviewRequest()
    result = await numbering.peek(
        db,
        tenant_id=user.tenant_id,
        key=key,
        branch_id=payload.branch_id,
        on_date=payload.on_date,
        branch_code=payload.branch_code,
        state_code=payload.state_code,
    )
    return SequencePreview(**result)


@router.get("/sequences/{key}/status", response_model=SequenceStatus, tags=["Settings · Sequences"])
async def sequence_status(
    key: str,
    fiscal_year: Optional[str] = None,
    user: User = Depends(read_sequences),
    db: AsyncSession = Depends(get_db),
):
    return SequenceStatus(**await numbering.status(db, tenant_id=user.tenant_id, key=key, fiscal_year=fiscal_year))


@router.post("/sequences/{key}/allocate", response_model=AllocationRead, tags=["Settings · Sequences"])
async def allocate_number(
    key: str,
    payload: AllocateRequest,
    user: User = Depends(allocate_sequences),
    db: AsyncSession = Depends(get_db),
):
    allocated = await numbering.allocate(
        db,
        tenant_id=user.tenant_id,
        key=key,
        user=user,
        branch_id=payload.branch_id,
        on_date=payload.on_date,
        idempotency_key=payload.idempotency_key,
        document_type=payload.document_type,
        document_id=payload.document_id,
    )
    await db.commit()
    return AllocationRead(**allocated.__dict__)


@router.post("/sequences/{key}/next", response_model=SequenceNext, tags=["Settings · Sequences"])
async def next_sequence_number_legacy(
    key: str,
    user: User = Depends(allocate_sequences),
    db: AsyncSession = Depends(get_db),
):
    """Deprecated compatibility endpoint; allocation moved to the atomic engine API."""
    raise HTTPException(
        status_code=410,
        detail={"code": "settings.endpoint_gone", "link": f"/api/v1/settings/sequences/{key}/allocate"},
    )


@router.post("/allocations/{allocation_id}/void", tags=["Settings · Sequences"])
async def void_allocation(
    allocation_id: UUID,
    payload: VoidRequest,
    user: User = Depends(update_sequences),
    db: AsyncSession = Depends(get_db),
):
    allocation = await db.scalar(
        select(NumberAllocation).where(NumberAllocation.id == allocation_id)
    )
    if allocation is None:
        raise NotFoundError("Allocation not found")
    if not user.is_superuser and allocation.tenant_id != user.tenant_id:
        raise ForbiddenError("Allocation belongs to another tenant")
    updated = await numbering.void(
        db,
        tenant_id=allocation.tenant_id,
        key="",
        rendered=allocation.rendered,
        reason_code=payload.reason_code,
        reason_text=payload.reason_text,
        user=user,
    )
    await db.commit()
    return {"id": str(updated.id), "status": updated.status, "reason_code": updated.reason_code}


# =============================================================================
# Offline blocks
# =============================================================================
def _block_response(block: NumberSequenceBlock) -> BlockRead:
    now = datetime.now(timezone.utc)
    expires_at = block.expires_at
    expired = bool(expires_at and expires_at < now)
    return BlockRead(
        id=block.id,
        sequence_id=block.sequence_id,
        fiscal_year=block.fiscal_year,
        range_start=block.range_start,
        range_end=block.range_end,
        size=block.size,
        device_id=block.device_id,
        status=block.status,
        used_count=block.used_count,
        expired=expired,
        expires_at=block.expires_at,
        issued_at=block.issued_at,
    )


@router.post("/sequences/{key}/blocks", response_model=BlockRead, status_code=201, tags=["Settings · Sequences"])
async def create_block(
    key: str,
    payload: BlockCreate,
    user: User = Depends(allocate_sequences),
    db: AsyncSession = Depends(get_db),
):
    block = await numbering.reserve_block(
        db,
        tenant_id=user.tenant_id,
        key=key,
        size=payload.size,
        device_id=payload.device_id,
        session_id=payload.session_id,
        expires_in_days=payload.expires_in_days,
        user=user,
    )
    await db.commit()
    return _block_response(block)


@router.get("/sequences/{key}/blocks", response_model=list[BlockRead], tags=["Settings · Sequences"])
async def list_blocks(
    key: str,
    user: User = Depends(read_sequences),
    db: AsyncSession = Depends(get_db),
):
    sequence = await db.scalar(
        select(NumberSequence).where(
            NumberSequence.key == key,
            NumberSequence.tenant_id == user.tenant_id,
        )
    )
    if sequence is None:
        raise NotFoundError(f"Numbering series '{key}' not found")
    blocks = (
        await db.scalars(
            select(NumberSequenceBlock)
            .where(NumberSequenceBlock.sequence_id == sequence.id)
            .order_by(NumberSequenceBlock.issued_at.desc())
            .limit(100)
        )
    ).all()
    return [_block_response(block) for block in blocks]


@router.post("/blocks/{block_id}/return", response_model=BlockRead, tags=["Settings · Sequences"])
async def return_block(
    block_id: UUID,
    payload: BlockReturn,
    user: User = Depends(allocate_sequences),
    db: AsyncSession = Depends(get_db),
):
    block = await numbering.return_block(
        db, block_id=block_id, used_up_to=payload.used_up_to, user=user
    )
    await db.commit()
    return _block_response(block)


# =============================================================================
# Reports
# =============================================================================
@router.get("/reports/numbering/gaps", response_model=GapReport, tags=["Settings · Reports"])
async def gap_report(
    key: Optional[str] = None,
    fiscal_year: Optional[str] = None,
    user: User = Depends(audit_read),
    db: AsyncSession = Depends(get_db),
):
    return GapReport(
        **(await numbering.gap_report(db, tenant_id=user.tenant_id, key=key, fiscal_year=fiscal_year))
    )


@router.get("/reports/numbering/usage", response_model=UsageReport, tags=["Settings · Reports"])
async def usage_report(
    user: User = Depends(audit_read),
    db: AsyncSession = Depends(get_db),
):
    return UsageReport(**(await numbering.usage_report(db, tenant_id=user.tenant_id)))


@router.get("/reports/settings/coverage", tags=["Settings · Reports"])
async def settings_coverage(
    user: User = Depends(read_settings),
    db: AsyncSession = Depends(get_db),
):
    rows = await settings_service.provenance(db, tenant_id=user.tenant_id)
    report = await settings_service.drift_report(db, tenant_id=user.tenant_id)
    critical = [row for row in rows if row["critical"]]
    explicit = [row for row in rows if row["effective_source"] != "default"]
    critical_explicit = [
        row for row in critical if row["effective_source"] != "default"
    ]
    return {
        "total_keys": len(rows),
        "explicit": len(explicit),
        "critical_keys": len(critical),
        "critical_explicit": len(critical_explicit),
        "missing_critical": [
            row["key"] for row in critical if row["effective_source"] == "default"
        ],
        "drift": report["total"],
        "drift_report": report,
    }
