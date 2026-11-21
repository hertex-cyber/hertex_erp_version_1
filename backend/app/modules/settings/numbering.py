"""Atomic document-numbering engine (module 15 §3.2 / 15A §5).

Every human-facing document number in the ERP comes from here. The concurrency
primitive is a single ``UPDATE number_sequence_periods … RETURNING`` statement:

* the row lock is taken by the ``UPDATE`` itself, so there is no read-modify-write
  window and no application-level mutex;
* ``RETURNING`` hands back the post-image, so the allocated number is exactly the
  value that was locked;
* ``number_allocations`` records every number ever issued, with a status and a
  reason, so gaps are always explainable (GST Rule 46 / GSTR-1 reconciliation).

Two implementations, per series (Odoo parity, but safer):

``standard`` (default)
    The counter update commits immediately in its own transaction, so a rolled
    back business document leaves a *declared* gap instead of rewinding a counter
    that other requests already advanced. Fast, lock-free beyond the row.

``nogap``
    The counter update runs inside the caller's transaction and is not committed
    here: a rollback rewinds it, so numbers stay consecutive. Serialised on the
    period row — only for low-volume, legally-consecutive channels.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.exceptions import AppError, ConflictError, NotFoundError, ValidationError
from app.modules.identity.models import AuditLog
from app.modules.settings import patterns
from app.modules.settings.models import (
    NumberAllocation,
    NumberSequence,
    NumberSequenceBlock,
    NumberSequencePeriod,
)

logger = logging.getLogger("hertex.numbering")

RETRYABLE = ("database is locked", "deadlock", "could not serialize", "lock timeout")
MAX_ATTEMPTS = 3


class NumberingError(AppError):
    status_code = 409
    code = "numbering.error"


class SeriesMissingError(AppError):
    status_code = 422
    code = "numbering.series_missing"


class PeriodClosedError(ConflictError):
    code = "numbering.period_closed"


class SequenceLockedError(ConflictError):
    code = "numbering.sequence_locked"


@dataclass(frozen=True)
class AllocatedNumber:
    number: int
    rendered: str
    fiscal_year: str
    period_id: UUID
    sequence_id: UUID
    allocation_id: UUID
    replayed: bool = False


class AllocatedNumberRef(str):
    """A rendered number that also carries its ledger allocation id.

    It behaves exactly like the string stored on a document while letting callers
    hand the allocation back to :func:`commit` without a second lookup.
    """

    def __new__(cls, rendered: str, allocation_id: UUID):
        obj = super().__new__(cls, rendered)
        obj.allocation_id = allocation_id
        return obj


GST_DOC_TYPES = frozenset(
    {"gst_invoice", "gst_credit_note", "gst_debit_note", "gst_bill_of_supply"}
)
GST_CHARSET = re.compile(r"^[A-Z0-9\-/]+$")
IRP_LEADING_CHARS = frozenset({"0", "-", "/"})
ENGINE_FLAG = "features.numbering.engine"


# Prefix -> engine key. Only used by legacy callers that still pass a prefix;
# every migrated module passes an explicit key.
PREFIX_TO_KEY = {
    "INV": "invoice",
    "SO": "sales_order",
    "PO": "purchase_order",
    "GRN": "goods_receipt",
    "DC": "delivery_challan",
    "JE": "journal_entry",
    "PS": "pos_sale",
    "TKT": "ticket",
    "PRJ": "project",
    "PRJ-T": "work_item",
    "SPR": "sprint",
    "PR": "purchase_requisition",
    "PAY": "payment",
    "VB": "vendor_invoice",
    "CN": "credit_note",
}

# Fields frozen once a series has issued at least one number (SE-14, odoo#302782).
LOCKED_FIELDS = ("implementation", "pattern", "reset_policy", "padding", "start_number")


def _dialect(db: AsyncSession) -> str:
    bind = db.get_bind()
    return bind.dialect.name if bind is not None else "postgresql"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _is_retryable(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in RETRYABLE)


def _resolve_key(key: str | None, prefix: str | None) -> str:
    resolved = key or PREFIX_TO_KEY.get((prefix or "").upper())
    if not resolved:
        raise ValidationError(
            f"No numbering key for prefix {prefix!r}", code="numbering.series_missing"
        )
    return resolved


async def _engine_enabled(db: AsyncSession, tenant_id: UUID | None) -> bool:
    """Runtime rollout switch. Enabled unless a tenant explicitly disables it."""
    try:
        from app.modules.settings.service import settings_service

        value = await settings_service.get(db, tenant_id=tenant_id, key=ENGINE_FLAG)
        return value is not False
    except Exception:
        return True


async def _audit_once(
    db: AsyncSession,
    *,
    allocation: NumberAllocation,
    user,
    action: str,
    changes: dict,
) -> None:
    stmt = select(AuditLog.id).where(
        AuditLog.entity == "NumberAllocation",
        AuditLog.entity_id == str(allocation.id),
        AuditLog.action == action,
    )
    if allocation.tenant_id is None:
        stmt = stmt.where(AuditLog.tenant_id.is_(None))
    else:
        stmt = stmt.where(AuditLog.tenant_id == allocation.tenant_id)
    if await db.scalar(stmt) is not None:
        return
    await record_audit(
        db,
        user=user,
        action=action,
        module="settings",
        entity="NumberAllocation",
        entity_id=allocation.id,
        changes=changes,
    )


def validate_gst_renderable(
    rendered: str,
    *,
    doc_type: str = "gst_invoice",
    irp_safe: bool = True,
    max_length: int = 16,
) -> str:
    """Render-time Rule 46(b) / IRP checks for a GST channel number."""
    if not rendered:
        raise ValidationError("Document number is empty", code="numbering.pattern_invalid")
    if len(rendered) > max_length:
        raise ValidationError(
            f"Document number '{rendered}' exceeds {max_length} characters",
            code="numbering.pattern_too_long",
        )
    if rendered != rendered.upper():
        raise ValidationError(
            f"Document number '{rendered}' must be uppercase for {doc_type}",
            code="numbering.pattern_invalid",
        )
    if not GST_CHARSET.fullmatch(rendered):
        raise ValidationError(
            f"Document number '{rendered}' uses characters not allowed for {doc_type}",
            code="numbering.pattern_invalid",
        )
    if irp_safe and rendered[0] in IRP_LEADING_CHARS:
        raise ValidationError(
            f"IRP rejects document numbers starting with '{rendered[0]}'",
            code="numbering.pattern_invalid",
        )
    return rendered


async def assert_no_collision(
    db: AsyncSession,
    *,
    tenant_id: UUID | None,
    rendered: str,
    fiscal_year: str | None = None,
    doc_type: str | None = None,
    sequence_id: UUID | None = None,
    exclude_allocation_id: UUID | None = None,
) -> None:
    """Duplicate guard scoped to the statutory (tenant, series, FY) namespace.

    GST uniqueness is per financial year and per configured series, including
    GSTIN-specific series. Narrowing the precheck to that namespace keeps
    independent internal series (which may share a display prefix) from blocking
    each other while still rejecting a real GST duplicate.
    """
    stmt = select(NumberAllocation.id).where(NumberAllocation.rendered == rendered)
    if tenant_id is None:
        stmt = stmt.where(NumberAllocation.tenant_id.is_(None))
    else:
        stmt = stmt.where(NumberAllocation.tenant_id == tenant_id)
    if fiscal_year is not None:
        stmt = stmt.where(NumberAllocation.fiscal_year == fiscal_year)
    if doc_type is not None:
        stmt = stmt.where(NumberAllocation.document_type == doc_type)
    if sequence_id is not None:
        stmt = stmt.where(NumberAllocation.sequence_id == sequence_id)
    if exclude_allocation_id is not None:
        stmt = stmt.where(NumberAllocation.id != exclude_allocation_id)
    if await db.scalar(stmt) is not None:
        raise ConflictError(
            f"Document number '{rendered}' is already allocated", code="numbering.duplicate"
        )


async def find_allocation(
    db: AsyncSession,
    *,
    tenant_id: UUID | None,
    rendered: str,
    doc_type: str | None = None,
) -> NumberAllocation | None:
    """Look up the ledger row behind an already-rendered document number."""
    stmt = select(NumberAllocation).where(NumberAllocation.rendered == rendered)
    if tenant_id is None:
        stmt = stmt.where(NumberAllocation.tenant_id.is_(None))
    else:
        stmt = stmt.where(NumberAllocation.tenant_id == tenant_id)
    if doc_type is not None:
        stmt = stmt.where(NumberAllocation.document_type == doc_type)
    return await db.scalar(stmt.order_by(NumberAllocation.allocated_at.desc()))


async def select_gstin_series(
    db: AsyncSession, *, tenant_id: UUID | None, key: str, gstin: str | None
) -> NumberSequence | None:
    """Return the series configured for a GSTIN, or ``None`` for the tenant default."""
    if not gstin:
        return None
    stmt = select(NumberSequence).where(
        NumberSequence.key == key,
        NumberSequence.gstin == gstin,
        NumberSequence.status != "draft",
    )
    if tenant_id is None:
        stmt = stmt.where(NumberSequence.tenant_id.is_(None))
    else:
        stmt = stmt.where(NumberSequence.tenant_id == tenant_id)
    return await db.scalar(stmt.order_by(NumberSequence.created_at.desc()))


class NumberSequenceService:
    """Single entry point for allocation, preview, status, voids and blocks."""

    # ---------------------------------------------------------------- lookups
    async def _load_sequence(
        self,
        db: AsyncSession,
        tenant_id: UUID | None,
        key: str,
        branch_id: UUID | None = None,
        *,
        allow_branch_fallback: bool = False,
        gstin: str | None = None,
    ) -> NumberSequence:
        base = select(NumberSequence).where(NumberSequence.key == key)
        if tenant_id is not None:
            base = base.where(NumberSequence.tenant_id == tenant_id)
        else:
            base = base.where(NumberSequence.tenant_id.is_(None))
        if gstin:
            gstin_series = await db.scalar(base.where(NumberSequence.gstin == gstin))
            if gstin_series is not None:
                return gstin_series
        if branch_id is not None:
            branch_series = await db.scalar(base.where(NumberSequence.branch_id == branch_id))
            if branch_series is not None:
                return branch_series
            if not allow_branch_fallback:
                raise SeriesMissingError(
                    f"No numbering series for '{key}' on branch {branch_id}"
                )
        series = await db.scalar(base.where(NumberSequence.branch_id.is_(None)))
        if series is None:
            raise SeriesMissingError(
                f"No numbering series configured for '{key}'. "
                "Create one under Settings → Numbering."
            )
        return series

    async def _branch_fallback_allowed(self, db: AsyncSession, tenant_id: UUID | None) -> bool:
        from app.modules.settings.service import settings_service

        value = await settings_service.get(
            db,
            tenant_id=tenant_id,
            key="settings.sequence.branch_fallback",
        )
        return value is True

    async def ensure_period(
        self,
        db: AsyncSession,
        sequence: NumberSequence,
        on_date: date,
        *,
        fiscal_year_start_month: int = 4,
        commit: bool = False,
    ) -> NumberSequencePeriod:
        start, end, fiscal_year = patterns.period_bounds(
            on_date, sequence.reset_policy, fiscal_year_start_month
        )
        sequence_id = sequence.id
        existing = await db.scalar(
            select(NumberSequencePeriod).where(
                NumberSequencePeriod.sequence_id == sequence_id,
                NumberSequencePeriod.fiscal_year == fiscal_year,
            )
        )
        if existing is not None:
            return existing

        period = NumberSequencePeriod(
            tenant_id=sequence.tenant_id,
            sequence_id=sequence_id,
            fiscal_year=fiscal_year,
            period_start=start,
            period_end=end,
            next_number=sequence.start_number,
            allocated_count=0,
            status="open",
        )
        db.add(period)
        try:
            await db.flush()
        except IntegrityError:
            # Concurrent first allocation of the period: re-read the winner.
            await db.rollback()
            existing = await db.scalar(
                select(NumberSequencePeriod).where(
                    NumberSequencePeriod.sequence_id == sequence_id,
                    NumberSequencePeriod.fiscal_year == fiscal_year,
                )
            )
            if existing is None:
                raise
            return existing
        if commit:
            await db.commit()
            await db.refresh(period)
        return period

    # ------------------------------------------------------------- allocation
    async def allocate(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        key: str,
        user=None,
        branch_id: UUID | None = None,
        on_date: date | None = None,
        idempotency_key: str | None = None,
        document_type: str | None = None,
        document_id: UUID | None = None,
        fiscal_year_start_month: int = 4,
        branch_code: str = "",
        state_code: str = "",
        tenant_code: str = "",
        gstin: str | None = None,
    ) -> AllocatedNumber:
        on_date = on_date or date.today()
        actor_id = getattr(user, "id", None)

        if idempotency_key:
            replay = await self._replay(db, tenant_id, idempotency_key)
            if replay is not None:
                return replay

        allow_fallback = await self._branch_fallback_allowed(db, tenant_id)
        sequence = await self._load_sequence(
            db, tenant_id, key, branch_id, allow_branch_fallback=allow_fallback, gstin=gstin
        )
        if sequence.status == "draft":
            raise SeriesMissingError(f"Numbering series '{key}' is not active yet")

        autonomous = sequence.implementation == "standard" and _dialect(db) != "sqlite"

        for attempt in range(MAX_ATTEMPTS):
            try:
                if autonomous:
                    from app.db.session import AsyncSessionLocal

                    async with AsyncSessionLocal() as engine_db:
                        sequence = await self._load_sequence(
                            engine_db, tenant_id, key, branch_id,
                            allow_branch_fallback=allow_fallback,
                            gstin=gstin,
                        )
                        allocated = await self._write_allocation(
                            engine_db,
                            sequence=sequence,
                            on_date=on_date,
                            actor_id=actor_id,
                            document_type=document_type,
                            document_id=document_id,
                            idempotency_key=idempotency_key,
                            branch_id=branch_id,
                            fiscal_year_start_month=fiscal_year_start_month,
                            branch_code=branch_code,
                            state_code=state_code,
                            tenant_code=tenant_code,
                        )
                        await engine_db.commit()
                        return allocated
                return await self._write_allocation(
                    db,
                    sequence=sequence,
                    on_date=on_date,
                    actor_id=actor_id,
                    document_type=document_type,
                    document_id=document_id,
                    idempotency_key=idempotency_key,
                    branch_id=branch_id,
                    fiscal_year_start_month=fiscal_year_start_month,
                    branch_code=branch_code,
                    state_code=state_code,
                    tenant_code=tenant_code,
                )
            except (OperationalError, IntegrityError) as exc:
                if not _is_retryable(exc) or attempt == MAX_ATTEMPTS - 1:
                    if isinstance(exc, IntegrityError) and idempotency_key:
                        replay = await self._replay(db, tenant_id, idempotency_key)
                        if replay is not None:
                            return replay
                        raise ConflictError(
                            "Duplicate document number", code="numbering.duplicate"
                        ) from exc
                    if isinstance(exc, IntegrityError):
                        raise ConflictError(
                            "Duplicate document number", code="numbering.duplicate"
                        ) from exc
                    raise NumberingError(
                        "Numbering is busy, retry the request", code="numbering.busy"
                    ) from exc
                logger.warning("numbering.retry", extra={"attempt": attempt + 1, "key": key})
        raise NumberingError("Numbering is busy, retry the request", code="numbering.busy")

    async def _replay(
        self, db: AsyncSession, tenant_id: UUID | None, idempotency_key: str
    ) -> AllocatedNumber | None:
        allocation = await db.scalar(
            select(NumberAllocation).where(
                NumberAllocation.idempotency_key == idempotency_key,
                NumberAllocation.tenant_id == tenant_id
                if tenant_id is not None
                else NumberAllocation.tenant_id.is_(None),
            )
        )
        if allocation is None:
            return None
        return AllocatedNumber(
            number=allocation.number,
            rendered=allocation.rendered,
            fiscal_year=allocation.fiscal_year,
            period_id=allocation.period_id,
            sequence_id=allocation.sequence_id,
            allocation_id=allocation.id,
            replayed=True,
        )

    async def _write_allocation(
        self,
        db: AsyncSession,
        *,
        sequence: NumberSequence,
        on_date: date,
        actor_id: UUID | None,
        document_type: str | None,
        document_id: UUID | None,
        idempotency_key: str | None,
        branch_id: UUID | None,
        fiscal_year_start_month: int,
        branch_code: str,
        state_code: str,
        tenant_code: str,
    ) -> AllocatedNumber:
        period = await self.ensure_period(
            db, sequence, on_date, fiscal_year_start_month=fiscal_year_start_month
        )
        stmt = (
            update(NumberSequencePeriod)
            .where(
                NumberSequencePeriod.id == period.id,
                NumberSequencePeriod.status == "open",
            )
            .values(
                next_number=NumberSequencePeriod.next_number + sequence.increment,
                allocated_count=NumberSequencePeriod.allocated_count + 1,
                last_allocated_at=func.now(),
                last_allocated_by_id=actor_id,
            )
            .returning(NumberSequencePeriod.next_number)
        )
        next_after = await db.scalar(stmt)
        if next_after is None:
            raise PeriodClosedError(
                f"Numbering period {period.fiscal_year or '-'} is closed for '{sequence.key}'"
            )
        allocated_number = int(next_after) - sequence.increment
        rendered = patterns.sanitize(
            patterns.render(
                sequence.pattern or "",
                patterns.RenderContext(
                    seq=allocated_number,
                    padding=sequence.padding or 5,
                    prefix=sequence.prefix or "",
                    suffix=sequence.suffix or "",
                    on_date=on_date,
                    fiscal_year=period.fiscal_year,
                    branch_code=branch_code,
                    state_code=state_code,
                    tenant_code=tenant_code,
                    doc_code=sequence.prefix or "",
                ),
            ),
            sequence.doc_type or "internal",
        )
        self._assert_renderable(sequence, rendered)
        if sequence.doc_type in GST_DOC_TYPES:
            validate_gst_renderable(
                rendered,
                doc_type=sequence.doc_type,
                irp_safe=sequence.irp_safe or patterns.profile_for(sequence.doc_type).irp_safe,
                max_length=sequence.max_length or 16,
            )
            await assert_no_collision(
                db,
                tenant_id=sequence.tenant_id,
                rendered=rendered,
                fiscal_year=period.fiscal_year,
                doc_type=sequence.doc_type,
            )

        allocation = NumberAllocation(
            tenant_id=sequence.tenant_id,
            sequence_id=sequence.id,
            period_id=period.id,
            fiscal_year=period.fiscal_year,
            number=allocated_number,
            rendered=rendered,
            status="manual" if document_type == "__manual__" else "allocated",
            document_type=document_type,
            document_id=document_id,
            branch_id=branch_id,
            idempotency_key=idempotency_key,
            allocated_by_id=actor_id,
        )
        db.add(allocation)
        sequence.last_allocated_at = _now()
        await db.flush()
        return AllocatedNumber(
            number=allocated_number,
            rendered=rendered,
            fiscal_year=period.fiscal_year,
            period_id=period.id,
            sequence_id=sequence.id,
            allocation_id=allocation.id,
        )

    def _assert_renderable(self, sequence: NumberSequence, rendered: str) -> None:
        profile = patterns.profile_for(sequence.doc_type)
        limit = sequence.max_length or profile.max_length
        if len(rendered) > limit:
            raise ValidationError(
                f"Rendered number '{rendered}' exceeds the {limit}-character limit for "
                f"{sequence.doc_type}",
                code="numbering.pattern_too_long",
            )
        import re

        regex = sequence.allowed_chars_regex or profile.allowed_regex
        if not re.match(regex, rendered):
            raise ValidationError(
                f"Rendered number '{rendered}' violates {regex}",
                code="numbering.pattern_invalid",
            )

    # ------------------------------------------------------------------ reads
    async def peek(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        key: str,
        branch_id: UUID | None = None,
        on_date: date | None = None,
        branch_code: str = "",
        state_code: str = "",
        tenant_code: str = "",
    ) -> dict:
        on_date = on_date or date.today()
        allow_fallback = await self._branch_fallback_allowed(db, tenant_id)
        sequence = await self._load_sequence(
            db, tenant_id, key, branch_id, allow_branch_fallback=allow_fallback
        )
        start, end, fiscal_year = patterns.period_bounds(on_date, sequence.reset_policy)
        period = await db.scalar(
            select(NumberSequencePeriod).where(
                NumberSequencePeriod.sequence_id == sequence.id,
                NumberSequencePeriod.fiscal_year == fiscal_year,
            )
        )
        next_number = period.next_number if period else sequence.start_number
        rendered = patterns.sanitize(
            patterns.render(
                sequence.pattern or "",
                patterns.RenderContext(
                    seq=next_number,
                    padding=sequence.padding or 5,
                    prefix=sequence.prefix or "",
                    suffix=sequence.suffix or "",
                    on_date=on_date,
                    fiscal_year=fiscal_year,
                    branch_code=branch_code,
                    state_code=state_code,
                    tenant_code=tenant_code,
                    doc_code=sequence.prefix or "",
                ),
            ),
            sequence.doc_type or "internal",
        )
        return {
            "key": key,
            "fiscal_year": fiscal_year,
            "period_start": start,
            "period_end": end,
            "next_number": next_number,
            "rendered": rendered,
            "consumed": False,
            "implementation": sequence.implementation,
            "period_open": bool(period and period.status == "open"),
        }

    async def status(
        self, db: AsyncSession, *, tenant_id: UUID | None, key: str, fiscal_year: str | None = None
    ) -> dict:
        sequence = await self._load_sequence(db, tenant_id, key)
        stmt = select(NumberSequencePeriod).where(
            NumberSequencePeriod.sequence_id == sequence.id
        )
        if fiscal_year:
            stmt = stmt.where(NumberSequencePeriod.fiscal_year == fiscal_year)
        else:
            stmt = stmt.order_by(NumberSequencePeriod.period_start.desc())
        period = await db.scalar(stmt)
        blocks_open = 0
        manual_recent = 0
        void_recent = 0
        if period is not None:
            blocks_open = int(
                await db.scalar(
                    select(func.count()).select_from(NumberSequenceBlock).where(
                        NumberSequenceBlock.period_id == period.id,
                        NumberSequenceBlock.status.in_(("issued", "partially_used")),
                    )
                )
                or 0
            )
            manual_recent = int(
                await db.scalar(
                    select(func.count()).select_from(NumberAllocation).where(
                        NumberAllocation.period_id == period.id,
                        NumberAllocation.status == "manual",
                    )
                )
                or 0
            )
            void_recent = int(
                await db.scalar(
                    select(func.count()).select_from(NumberAllocation).where(
                        NumberAllocation.period_id == period.id,
                        NumberAllocation.status == "void",
                    )
                )
                or 0
            )
        preview = await self.peek(db, tenant_id=tenant_id, key=key)
        return {
            "key": key,
            "doc_type": sequence.doc_type,
            "owner_module": sequence.owner_module,
            "pattern": sequence.pattern,
            "implementation": sequence.implementation,
            "reset_policy": sequence.reset_policy,
            "status": sequence.status,
            "branch_id": sequence.branch_id,
            "fiscal_year": period.fiscal_year if period else None,
            "next_number": period.next_number if period else sequence.start_number,
            "allocated_count": period.allocated_count if period else 0,
            "period_status": period.status if period else "not_open",
            "period_start": period.period_start if period else None,
            "period_end": period.period_end if period else None,
            "last_allocated_at": sequence.last_allocated_at,
            "open_blocks": blocks_open,
            "manual_allocations": manual_recent,
            "voided_allocations": void_recent,
            "preview": preview["rendered"],
        }

    # ------------------------------------------------------------------ voids
    async def void(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        key: str,
        rendered: str,
        reason_code: str,
        reason_text: str,
        user=None,
    ) -> NumberAllocation:
        if reason_code not in {
            "abandoned",
            "cancelled",
            "void",
            "manual_skip",
            "block_unused",
            "block_expired",
        }:
            raise ValidationError(f"Unknown void reason '{reason_code}'")
        if not (reason_text or "").strip():
            raise ValidationError(
                "A declared reason is required when voiding a number",
                code="numbering.reason_required",
            )
        stmt = select(NumberAllocation).where(NumberAllocation.rendered == rendered)
        if tenant_id is not None:
            stmt = stmt.where(NumberAllocation.tenant_id == tenant_id)
        allocation = await db.scalar(stmt)
        if allocation is None:
            raise NotFoundError(f"No allocation registered for {rendered}")
        if allocation.status == "void":
            return allocation
        allocation.status = "void"
        allocation.reason_code = reason_code
        allocation.reason_text = reason_text[:200]
        allocation.voided_at = _now()
        await db.flush()
        await record_audit(
            db,
            user=user,
            action="numbering.void",
            module="settings",
            entity="NumberAllocation",
            entity_id=allocation.id,
            changes={
                "rendered": allocation.rendered,
                "reason_code": reason_code,
                "reason_text": reason_text[:200],
            },
        )
        return allocation

    async def commit(
        self,
        db: AsyncSession,
        number: str | UUID | AllocatedNumber,
        *,
        document_type: str,
        document_id: UUID | None = None,
        tenant_id: UUID | None = None,
        user=None,
        request=None,
    ) -> NumberAllocation:
        """Commit an allocation to its document, idempotently, with full audit."""
        allocation = None
        if isinstance(number, (AllocatedNumber, AllocatedNumberRef)):
            allocation = await db.scalar(
                select(NumberAllocation).where(NumberAllocation.id == number.allocation_id)
            )
        elif isinstance(number, UUID):
            allocation = await db.scalar(
                select(NumberAllocation).where(NumberAllocation.id == number)
            )
        else:
            try:
                allocation_id = UUID(str(number))
            except (TypeError, ValueError):
                stmt = select(NumberAllocation).where(NumberAllocation.rendered == str(number))
                if tenant_id is not None:
                    stmt = stmt.where(NumberAllocation.tenant_id == tenant_id)
                allocation = await db.scalar(
                    stmt.order_by(
                        NumberAllocation.created_at.desc(),
                        NumberAllocation.allocated_at.desc(),
                    )
                )
            else:
                allocation = await db.scalar(
                    select(NumberAllocation).where(NumberAllocation.id == allocation_id)
                )
        if allocation is None:
            raise NotFoundError("Number allocation not found")
        if (
            allocation.status == "committed"
            and allocation.document_type == document_type
            and allocation.document_id == document_id
        ):
            return allocation
        if allocation.status in {"void", "expired"}:
            raise ConflictError(
                f"Number {allocation.rendered} is {allocation.status} and cannot be committed"
            )
        if allocation.status == "committed":
            raise ConflictError(
                f"Number {allocation.rendered} is already committed to another document",
                code="numbering.duplicate",
            )
        sequence = await db.scalar(
            select(NumberSequence).where(NumberSequence.id == allocation.sequence_id)
        )
        if sequence is not None and sequence.doc_type in GST_DOC_TYPES:
            validate_gst_renderable(
                allocation.rendered,
                doc_type=sequence.doc_type,
                irp_safe=sequence.irp_safe or patterns.profile_for(sequence.doc_type).irp_safe,
                max_length=sequence.max_length or 16,
            )
            await assert_no_collision(
                db,
                tenant_id=allocation.tenant_id,
                rendered=allocation.rendered,
                fiscal_year=allocation.fiscal_year,
                doc_type=sequence.doc_type,
                sequence_id=sequence.id,
                exclude_allocation_id=allocation.id,
            )
        allocation.status = "committed"
        allocation.document_type = document_type
        allocation.document_id = document_id
        allocation.committed_at = _now()
        await db.flush()
        changes = {
            "rendered": allocation.rendered,
            "key": sequence.key if sequence else None,
            "fiscal_year": allocation.fiscal_year,
            "document_type": document_type,
            "document_id": str(document_id) if document_id else None,
        }
        await _audit_once(
            db,
            allocation=allocation,
            user=user,
            action="numbering.allocated",
            changes=changes,
        )
        await _audit_once(
            db,
            allocation=allocation,
            user=user,
            action="numbering.committed",
            changes=changes,
        )
        return allocation

    # ----------------------------------------------------------------- blocks
    async def reserve_block(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        key: str,
        size: int,
        device_id: str,
        session_id: UUID | None = None,
        on_date: date | None = None,
        expires_in_days: int = 7,
        user=None,
    ) -> NumberSequenceBlock:
        if not 1 <= size <= 500:
            raise ValidationError("Block size must be between 1 and 500")
        on_date = on_date or date.today()
        sequence = await self._load_sequence(db, tenant_id, key)
        period = await self.ensure_period(db, sequence, on_date)
        if period.status != "open":
            raise PeriodClosedError("Numbering period is closed")
        stmt = (
            update(NumberSequencePeriod)
            .where(
                NumberSequencePeriod.id == period.id,
                NumberSequencePeriod.status == "open",
            )
            .values(
                next_number=NumberSequencePeriod.next_number + size,
                allocated_count=NumberSequencePeriod.allocated_count + size,
                last_allocated_at=func.now(),
                last_allocated_by_id=getattr(user, "id", None),
            )
            .returning(NumberSequencePeriod.next_number)
        )
        next_after = await db.scalar(stmt)
        if next_after is None:
            raise PeriodClosedError("Numbering period is closed")
        range_end = int(next_after) - 1
        range_start = range_end - size + 1
        block = NumberSequenceBlock(
            tenant_id=sequence.tenant_id,
            sequence_id=sequence.id,
            period_id=period.id,
            fiscal_year=period.fiscal_year,
            range_start=range_start,
            range_end=range_end,
            size=size,
            device_id=device_id,
            session_id=session_id,
            status="issued",
            expires_at=_now() + timedelta(days=expires_in_days),
        )
        db.add(block)
        await db.flush()
        for number in range(range_start, range_end + 1):
            db.add(
                NumberAllocation(
                    tenant_id=sequence.tenant_id,
                    sequence_id=sequence.id,
                    period_id=period.id,
                    fiscal_year=period.fiscal_year,
                    number=number,
                    rendered=patterns.sanitize(
                        patterns.render(
                            sequence.pattern or "",
                            patterns.RenderContext(
                                seq=number,
                                padding=sequence.padding or 5,
                                prefix=sequence.prefix or "",
                                suffix=sequence.suffix or "",
                                on_date=on_date,
                                fiscal_year=period.fiscal_year,
                                doc_code=sequence.prefix or "",
                            ),
                        ),
                        sequence.doc_type or "internal",
                    ),
                    status="block",
                    document_type=None,
                    device_id=device_id,
                    allocated_by_id=getattr(user, "id", None),
                )
            )
        await db.flush()
        return block

    async def return_block(
        self,
        db: AsyncSession,
        *,
        block_id: UUID,
        used_up_to: int | None = None,
        user=None,
    ) -> NumberSequenceBlock:
        block = await db.scalar(
            select(NumberSequenceBlock).where(NumberSequenceBlock.id == block_id)
        )
        if block is None:
            raise NotFoundError("Number block not found")
        if block.status in {"returned", "expired"}:
            return block
        unused_from = (used_up_to + 1) if used_up_to else block.range_start
        unused_from = max(block.range_start, min(unused_from, block.range_end + 1))
        if unused_from <= block.range_end:
            await db.execute(
                update(NumberAllocation)
                .where(
                    NumberAllocation.sequence_id == block.sequence_id,
                    NumberAllocation.fiscal_year == block.fiscal_year,
                    NumberAllocation.number >= unused_from,
                    NumberAllocation.number <= block.range_end,
                    NumberAllocation.status == "block",
                )
                .values(
                    status="void",
                    reason_code="block_unused",
                    reason_text=f"Returned by device {block.device_id}",
                    voided_at=_now(),
                )
            )
        block.returned_from = unused_from
        block.used_count = max(0, (unused_from - block.range_start))
        block.status = "returned" if block.used_count == 0 else "partially_used"
        await db.flush()
        return block

    # ---------------------------------------------------------------- reports
    async def gap_report(
        self,
        db: AsyncSession,
        *,
        tenant_id: UUID | None,
        key: str | None = None,
        fiscal_year: str | None = None,
        limit: int = 500,
    ) -> dict:
        safe_limit = max(0, limit)
        alloc_filters = []
        if tenant_id is not None:
            alloc_filters.append(NumberAllocation.tenant_id == tenant_id)
        if key:
            sequence = await db.scalar(
                select(NumberSequence).where(
                    NumberSequence.key == key,
                    *(
                        [NumberSequence.tenant_id == tenant_id]
                        if tenant_id is not None
                        else []
                    ),
                )
            )
            if sequence is None:
                raise NotFoundError(f"Numbering series '{key}' not found")
            alloc_filters.append(NumberAllocation.sequence_id == sequence.id)
        if fiscal_year:
            alloc_filters.append(NumberAllocation.fiscal_year == fiscal_year)

        allocation_total = int(
            await db.scalar(
                select(func.count())
                .select_from(NumberAllocation)
                .where(*alloc_filters)
            )
            or 0
        )

        previous_number = func.lag(NumberAllocation.number).over(
            partition_by=[
                NumberAllocation.sequence_id,
                NumberAllocation.fiscal_year,
            ],
            order_by=NumberAllocation.number,
        )
        intervals = (
            select(
                NumberAllocation.sequence_id.label("sequence_id"),
                NumberAllocation.fiscal_year.label("fiscal_year"),
                NumberAllocation.number.label("number"),
                previous_number.label("previous_number"),
            )
            .where(*alloc_filters)
            .subquery()
        )
        gap_size = intervals.c.number - func.coalesce(intervals.c.previous_number, 0) - 1
        gap_filter = gap_size > 0
        gap_total = int(
            await db.scalar(
                select(func.coalesce(func.sum(gap_size), 0))
                .select_from(intervals)
                .where(gap_filter)
            )
            or 0
        )
        gap_rows = (
            await db.execute(
                select(
                    intervals.c.sequence_id,
                    intervals.c.fiscal_year,
                    intervals.c.previous_number,
                    gap_size.label("gap_size"),
                )
                .where(gap_filter)
                .order_by(
                    intervals.c.sequence_id,
                    intervals.c.fiscal_year,
                    intervals.c.number,
                )
                .limit(safe_limit)
            )
        ).all()

        gaps: list[dict] = []
        for sequence_id, fiscal_year, previous, size in gap_rows:
            start = int(previous or 0) + 1
            for number in range(start, start + int(size)):
                gaps.append(
                    {
                        "sequence_id": str(sequence_id),
                        "fiscal_year": fiscal_year,
                        "number": number,
                        "reason_code": "unallocated",
                        "reason_text": "No allocation recorded for this number",
                    }
                )
                if len(gaps) >= safe_limit:
                    break
            if len(gaps) >= safe_limit:
                break

        void_filters = [*alloc_filters, NumberAllocation.status == "void"]
        void_total = int(
            await db.scalar(
                select(func.count())
                .select_from(NumberAllocation)
                .where(*void_filters)
            )
            or 0
        )
        void_rows = (
            await db.scalars(
                select(NumberAllocation)
                .where(*void_filters)
                .order_by(
                    NumberAllocation.sequence_id,
                    NumberAllocation.fiscal_year,
                    NumberAllocation.number,
                )
                .limit(safe_limit)
            )
        ).all()
        voids = [
            {
                "sequence_id": str(row.sequence_id),
                "fiscal_year": row.fiscal_year,
                "number": row.number,
                "rendered": row.rendered,
                "reason_code": row.reason_code or "void",
                "reason_text": row.reason_text or "",
                "voided_at": row.voided_at,
            }
            for row in void_rows
        ]

        block_filters = [
            (
                NumberSequenceBlock.tenant_id == tenant_id
                if tenant_id is not None
                else NumberSequenceBlock.tenant_id.is_(None)
            ),
            NumberSequenceBlock.status.in_(("issued", "partially_used")),
        ]
        unreturned_total = int(
            await db.scalar(
                select(func.count())
                .select_from(NumberSequenceBlock)
                .where(*block_filters)
            )
            or 0
        )
        unreturned = (
            await db.scalars(
                select(NumberSequenceBlock)
                .where(*block_filters)
                .order_by(NumberSequenceBlock.created_at.desc())
                .limit(50)
            )
        ).all()
        return {
            "unexplained": gaps,
            "declared": voids,
            "unreturned_blocks": [
                {
                    "id": block.id,
                    "device_id": block.device_id,
                    "range_start": block.range_start,
                    "range_end": block.range_end,
                    "status": block.status,
                    "expires_at": block.expires_at,
                }
                for block in unreturned
            ],
            "totals": {
                "allocations": allocation_total,
                "unexplained": gap_total,
                "declared": void_total,
                "unreturned_blocks": unreturned_total,
            },
        }

    async def usage_report(self, db: AsyncSession, *, tenant_id: UUID | None) -> dict:
        seq_stmt = select(NumberSequence)
        if tenant_id is not None:
            seq_stmt = seq_stmt.where(NumberSequence.tenant_id == tenant_id)
        sequences = list((await db.scalars(seq_stmt)).all())
        rows = []
        for sequence in sequences:
            period_stmt = select(NumberSequencePeriod).where(
                NumberSequencePeriod.sequence_id == sequence.id
            )
            if tenant_id is not None:
                period_stmt = period_stmt.where(NumberSequencePeriod.tenant_id == tenant_id)
            period = await db.scalar(
                period_stmt.order_by(NumberSequencePeriod.period_start.desc())
            )
            rows.append(
                {
                    "key": sequence.key,
                    "owner_module": sequence.owner_module,
                    "doc_type": sequence.doc_type,
                    "fiscal_year": period.fiscal_year if period else None,
                    "allocated_count": period.allocated_count if period else 0,
                    "next_number": period.next_number if period else sequence.start_number,
                    "last_allocated_at": sequence.last_allocated_at,
                    "status": sequence.status,
                }
            )
        rows.sort(key=lambda item: (item["owner_module"], item["key"]))
        return {"items": rows, "total": len(rows)}

    # -------------------------------------------------------------- utilities
    async def assert_mutable(self, db: AsyncSession, sequence: NumberSequence, changes: dict) -> None:
        """Freeze structural fields once the series has issued a number (SE-14)."""
        if sequence.status == "locked":
            if any(field in changes for field in LOCKED_FIELDS):
                raise SequenceLockedError(
                    f"Series '{sequence.key}' is locked after its first allocation; "
                    "create a new series key to change the format"
                )
            return
        has_allocations = await db.scalar(
            select(func.count())
            .select_from(NumberAllocation)
            .where(NumberAllocation.sequence_id == sequence.id)
        )
        if has_allocations and any(field in changes for field in LOCKED_FIELDS):
            raise SequenceLockedError(
                f"Series '{sequence.key}' already issued numbers; structural fields are frozen"
            )

    async def validate_configuration(self, db: AsyncSession, sequence: NumberSequence) -> list[str]:
        allow_fallback = await self._branch_fallback_allowed(db, sequence.tenant_id)
        del allow_fallback
        return patterns.validate(
            sequence.pattern,
            doc_type=sequence.doc_type,
            padding=sequence.padding,
            prefix=sequence.prefix,
            suffix=sequence.suffix,
            irp_safe=sequence.irp_safe,
            max_length=sequence.max_length,
            allowed_chars_regex=sequence.allowed_chars_regex,
            doc_code=sequence.prefix,
        )


numbering = NumberSequenceService()


async def allocate_document(
    db: AsyncSession,
    *,
    tenant_id: UUID | None,
    key: str | None = None,
    prefix: str | None = None,
    user=None,
    on_date: date | None = None,
    branch_id: UUID | None = None,
    gstin: str | None = None,
    document_type: str | None = None,
    document_id: UUID | None = None,
    idempotency_key: str | None = None,
    branch_code: str = "",
    state_code: str = "",
    tenant_code: str = "",
) -> AllocatedNumber:
    """Structured allocation entry point used by every document creator.

    Routes at runtime on ``features.numbering.engine``; the disabled path uses a
    safe, atomic count-derived fallback that still writes a ledger row.
    """
    resolved_key = _resolve_key(key, prefix)
    if await _engine_enabled(db, tenant_id):
        return await numbering.allocate(
            db,
            tenant_id=tenant_id,
            key=resolved_key,
            user=user,
            branch_id=branch_id,
            gstin=gstin,
            on_date=on_date,
            idempotency_key=idempotency_key,
            document_type=document_type,
            document_id=document_id,
            branch_code=branch_code,
            state_code=state_code,
            tenant_code=tenant_code,
        )
    return await _allocate_legacy(
        db,
        tenant_id=tenant_id,
        key=resolved_key,
        user=user,
        on_date=on_date,
        branch_id=branch_id,
        gstin=gstin,
        document_type=document_type,
        document_id=document_id,
        idempotency_key=idempotency_key,
    )


async def _allocate_legacy(
    db: AsyncSession,
    *,
    tenant_id: UUID | None,
    key: str,
    user=None,
    on_date: date | None,
    branch_id: UUID | None,
    gstin: str | None,
    document_type: str | None,
    document_id: UUID | None,
    idempotency_key: str | None,
) -> AllocatedNumber:
    """Atomic legacy fallback: advance a counter row, never a ``count(*)`` read.

    The ``next_number`` mirror is advanced in one ``UPDATE … RETURNING`` and kept
    ahead of the ledger maximum, so the number stays unique even if the flag is
    toggled mid-flight or a document was deleted.
    """
    on_date = on_date or date.today()
    if idempotency_key:
        replay = await numbering._replay(db, tenant_id, idempotency_key)
        if replay is not None:
            return replay
    allow_fallback = await numbering._branch_fallback_allowed(db, tenant_id)
    sequence = await numbering._load_sequence(
        db, tenant_id, key, branch_id, allow_branch_fallback=allow_fallback, gstin=gstin
    )
    if sequence.status == "draft":
        raise SeriesMissingError(f"Numbering series '{key}' is not active yet")

    increment = sequence.increment or 1
    number = None
    for _attempt in range(MAX_ATTEMPTS):
        current_row = await db.scalar(
            select(NumberSequence).where(NumberSequence.id == sequence.id)
        )
        ledger_max = await db.scalar(
            select(func.coalesce(func.max(NumberAllocation.number), 0)).where(
                NumberAllocation.sequence_id == sequence.id
            )
        )
        current = int(current_row.next_number or sequence.start_number or 1)
        candidate = (
            max(current, int(ledger_max or 0), int(sequence.start_number or 1) - 1)
            + increment
        )
        claimed = await db.scalar(
            update(NumberSequence)
            .where(
                NumberSequence.id == sequence.id,
                NumberSequence.next_number <= candidate,
            )
            .values(next_number=candidate)
            .returning(NumberSequence.next_number)
        )
        if claimed is not None:
            number = int(claimed)
            break
    if number is None:
        raise NumberingError("Numbering is busy, retry the request", code="numbering.busy")
    period = await numbering.ensure_period(db, sequence, on_date)
    period_row = await db.scalar(
        select(NumberSequencePeriod).where(NumberSequencePeriod.id == period.id)
    )
    period_next = max(int(period_row.next_number or number), number + increment)
    await db.execute(
        update(NumberSequencePeriod)
        .where(NumberSequencePeriod.id == period.id)
        .values(
            next_number=period_next,
            allocated_count=NumberSequencePeriod.allocated_count + 1,
            last_allocated_at=func.now(),
            last_allocated_by_id=getattr(user, "id", None),
        )
    )
    rendered = patterns.sanitize(
        patterns.render(
            sequence.pattern or "",
            patterns.RenderContext(
                seq=number,
                padding=sequence.padding or 5,
                prefix=sequence.prefix or "",
                suffix=sequence.suffix or "",
                on_date=on_date,
                fiscal_year=period.fiscal_year,
                doc_code=sequence.prefix or "",
            ),
        ),
        sequence.doc_type or "internal",
    )
    numbering._assert_renderable(sequence, rendered)
    if sequence.doc_type in GST_DOC_TYPES:
        validate_gst_renderable(
            rendered,
            doc_type=sequence.doc_type,
            irp_safe=sequence.irp_safe or patterns.profile_for(sequence.doc_type).irp_safe,
            max_length=sequence.max_length or 16,
        )
        await assert_no_collision(
            db,
            tenant_id=sequence.tenant_id,
            rendered=rendered,
            fiscal_year=period.fiscal_year,
            doc_type=sequence.doc_type,
            sequence_id=sequence.id,
        )
    allocation = NumberAllocation(
        tenant_id=sequence.tenant_id,
        sequence_id=sequence.id,
        period_id=period.id,
        fiscal_year=period.fiscal_year,
        number=number,
        rendered=rendered,
        status="allocated",
        document_type=document_type,
        document_id=document_id,
        branch_id=branch_id,
        idempotency_key=idempotency_key,
        allocated_by_id=getattr(user, "id", None),
    )
    db.add(allocation)
    sequence.last_allocated_at = _now()
    await db.flush()
    return AllocatedNumber(
        number=number,
        rendered=rendered,
        fiscal_year=period.fiscal_year,
        period_id=period.id,
        sequence_id=sequence.id,
        allocation_id=allocation.id,
    )


async def document_number(
    db: AsyncSession,
    *,
    key: str | None = None,
    prefix: str | None = None,
    tenant_id: UUID | None,
    user=None,
    on_date: date | None = None,
    branch_id: UUID | None = None,
    gstin: str | None = None,
    document_type: str | None = None,
    document_id: UUID | None = None,
    idempotency_key: str | None = None,
) -> str:
    """Allocate a number and return a string that also carries its ledger id."""
    allocated = await allocate_document(
        db,
        tenant_id=tenant_id,
        key=key,
        prefix=prefix,
        user=user,
        on_date=on_date,
        branch_id=branch_id,
        gstin=gstin,
        document_type=document_type,
        document_id=document_id,
        idempotency_key=idempotency_key,
    )
    return AllocatedNumberRef(allocated.rendered, allocated.allocation_id)


async def commit(
    db: AsyncSession,
    number: str | UUID | AllocatedNumber,
    *,
    document_type: str,
    document_id: UUID | None = None,
    tenant_id: UUID | None = None,
    user=None,
    request=None,
) -> NumberAllocation:
    """Public commit helper: mark committed and emit the numbering audit trail."""
    return await numbering.commit(
        db,
        number,
        document_type=document_type,
        document_id=document_id,
        tenant_id=tenant_id,
        user=user,
        request=request,
    )


async def open_next_periods(db: AsyncSession, *, days_ahead: int = 7) -> list[dict]:
    """Pre-create the next fiscal period for every active series (beat job)."""
    today = date.today() + timedelta(days=days_ahead)
    sequences = list((await db.scalars(select(NumberSequence).where(NumberSequence.status != "draft"))).all())
    opened = []
    for sequence in sequences:
        period = await numbering.ensure_period(db, sequence, today)
        opened.append(
            {
                "key": sequence.key,
                "tenant_id": str(sequence.tenant_id) if sequence.tenant_id else None,
                "fiscal_year": period.fiscal_year,
                "next_number": period.next_number,
            }
        )
    await db.commit()
    return opened


async def sweep_abandoned_allocations(db: AsyncSession, *, older_than_hours: int = 24) -> int:
    """Void allocations that never became a document (declared gap, not a hole)."""
    cutoff = _now() - timedelta(hours=older_than_hours)
    result = await db.execute(
        update(NumberAllocation)
        .where(
            NumberAllocation.status == "allocated",
            NumberAllocation.document_id.is_(None),
            NumberAllocation.allocated_at < cutoff,
        )
        .values(
            status="void",
            reason_code="abandoned",
            reason_text="Allocated but no document was committed",
            voided_at=_now(),
        )
    )
    await db.commit()
    return int(result.rowcount or 0)


async def consume_block(
    db: AsyncSession, *, block_id: UUID, user=None
) -> AllocatedNumber:
    """Consume the next number from a reserved offline block."""
    block = await db.scalar(
        select(NumberSequenceBlock).where(NumberSequenceBlock.id == block_id)
    )
    if block is None:
        raise NotFoundError("Number block not found")
    if block.status not in {"issued", "partially_used"}:
        raise ConflictError("Number block is not available", code="numbering.block_unavailable")
    if block.expires_at is not None and block.expires_at < _now():
        raise ConflictError("Number block has expired", code="numbering.block_expired")
    next_number = block.range_start + int(block.used_count or 0)
    if next_number > block.range_end:
        raise ConflictError("Number block is exhausted", code="numbering.block_exhausted")
    allocation = await db.scalar(
        select(NumberAllocation).where(
            NumberAllocation.sequence_id == block.sequence_id,
            NumberAllocation.number == next_number,
            NumberAllocation.status == "block",
        )
    )
    if allocation is None:
        raise ConflictError("Reserved number is no longer available", code="numbering.block_exhausted")
    block.used_count = int(block.used_count or 0) + 1
    block.status = "used" if block.used_count >= block.size else "partially_used"
    allocation.status = "allocated"
    allocation.device_id = block.device_id
    allocation.allocated_by_id = getattr(user, "id", None)
    allocation.allocated_at = _now()
    await db.flush()
    return AllocatedNumber(
        number=allocation.number,
        rendered=allocation.rendered,
        fiscal_year=allocation.fiscal_year,
        period_id=allocation.period_id,
        sequence_id=allocation.sequence_id,
        allocation_id=allocation.id,
    )


async def expire_blocks(db: AsyncSession) -> int:
    """Mark expired unreturned blocks so the gap report can explain them."""
    now = _now()
    result = await db.execute(
        update(NumberSequenceBlock)
        .where(
            NumberSequenceBlock.status.in_(("issued", "partially_used")),
            NumberSequenceBlock.expires_at.is_not(None),
            NumberSequenceBlock.expires_at < now,
        )
        .values(status="expired")
    )
    await db.commit()
    return int(result.rowcount or 0)


UNRETURNED_BLOCK_REPORTS: dict[str, list[dict]] = {}


async def refresh_unreturned_block_report(
    db: AsyncSession, *, tenant_id: UUID | None = None
) -> dict:
    """Rebuild the unreturned-block report consumed by POS fleet operations."""
    report = await numbering.gap_report(db, tenant_id=tenant_id, limit=50)
    blocks = list(report["unreturned_blocks"])
    UNRETURNED_BLOCK_REPORTS[str(tenant_id)] = blocks
    return {
        "tenant_id": str(tenant_id) if tenant_id else None,
        "unreturned_blocks": blocks,
        "total": report["totals"]["unreturned_blocks"],
    }
