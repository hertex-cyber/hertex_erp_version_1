"""Durable finance control plane: source-event inbox, outbox, webhooks and ledger balances."""

import hashlib
import hmac
import json
import logging
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

import httpx
from sqlalchemy import Select, event, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.modules.finance.compliance_models import (
    FinanceAuditLog,
    LedgerBalance,
    OutboxEvent,
    SourceEvent,
    WebhookDelivery,
    WebhookEndpoint,
)
from app.modules.finance.models import FinancialPeriod, JournalEntry
from app.modules.identity.models import Role, User

logger = logging.getLogger("hertex.finance.control")

MAX_OUTBOX_ATTEMPTS = 5
RETRY_BACKOFF_MINUTES = 5


def _json(value: Any) -> Any:
    if isinstance(value, (Decimal, UUID, date, datetime)):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return value


def _scope(stmt: Select, model: Any, user: User) -> Select:
    if not user.is_superuser and user.tenant_id:
        return stmt.where(model.tenant_id == user.tenant_id)
    return stmt


async def record_finance_audit(
    db: AsyncSession,
    *,
    user: User | None,
    entity_type: str,
    entity_id: UUID | None,
    action: str,
    before: Optional[dict[str, Any]] = None,
    after: Optional[dict[str, Any]] = None,
    reason: str | None = None,
    source_module: str = "finance",
    correlation_id: str | None = None,
    ip_address: str | None = None,
    approval_context_id: UUID | None = None,
) -> FinanceAuditLog:
    roles = [role.slug for role in user.roles] if user and getattr(user, "roles", None) else []
    log = FinanceAuditLog(
        tenant_id=user.tenant_id if user else None,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        source_module=source_module,
        actor_id=user.id if user else None,
        actor_email=user.email if user else "system",
        actor_role=",".join(roles) if roles else None,
        before_state=_json(before or {}),
        after_state=_json(after or {}),
        reason=reason,
        correlation_id=correlation_id,
        ip_address=ip_address,
        approval_context_id=approval_context_id,
    )
    db.add(log)
    return log


async def claim_source_event(
    db: AsyncSession,
    *,
    user: User,
    event_type: str,
    source_module: str,
    idempotency_key: str,
    payload: Optional[dict[str, Any]] = None,
    source_document_type: str | None = None,
    source_document_id: UUID | None = None,
) -> tuple[SourceEvent, bool]:
    """Atomically claim a source event. Returns (event, created)."""
    key = idempotency_key.strip()
    if len(key) < 8 or len(key) > 180:
        raise ValidationError("Source event idempotency key must be 8-180 characters")
    existing = await db.scalar(
        _scope(
            select(SourceEvent).where(
                SourceEvent.event_type == event_type,
                SourceEvent.idempotency_key == key,
            ),
            SourceEvent,
            user,
        )
    )
    if existing is not None:
        return existing, False
    event = SourceEvent(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        event_type=event_type,
        source_module=source_module,
        source_document_type=source_document_type,
        source_document_id=source_document_id,
        idempotency_key=key,
        payload=_json(payload or {}),
        status="received",
    )
    db.add(event)
    await db.flush()
    return event, True


def complete_source_event(
    event: SourceEvent, *, result_reference: str | None = None, error: str | None = None
) -> None:
    event.attempts += 1
    if error:
        event.status = "dead" if event.attempts >= MAX_OUTBOX_ATTEMPTS else "failed"
        event.last_error = error[:2000]
    else:
        event.status = "processed"
        event.result_reference = result_reference
        event.processed_at = datetime.now(timezone.utc)


def enqueue_outbox_sync(
    session: Session,
    *,
    tenant_id: UUID | None,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict[str, Any],
) -> OutboxEvent:
    existing = session.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.event_type == event_type,
            OutboxEvent.aggregate_id == aggregate_id,
        )
    )
    if existing is not None:
        return existing
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=_json(payload),
        status="pending",
        next_attempt_at=datetime.now(timezone.utc),
    )
    session.add(event)
    return event


async def enqueue_outbox(
    db: AsyncSession,
    *,
    tenant_id: UUID | None,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict[str, Any],
) -> OutboxEvent:
    existing = await db.scalar(
        select(OutboxEvent).where(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.event_type == event_type,
            OutboxEvent.aggregate_id == aggregate_id,
        )
    )
    if existing is not None:
        return existing
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        payload=_json(payload),
        status="pending",
        next_attempt_at=datetime.now(timezone.utc),
    )
    db.add(event)
    return event


def journal_posted_effects_sync(session: Session, entry: JournalEntry) -> None:
    before = {
        "status": "draft",
        "entry_number": entry.entry_number,
        "entry_date": str(entry.entry_date),
    }
    after = {
        "status": "posted",
        "entry_number": entry.entry_number,
        "entry_date": str(entry.entry_date),
        "reference": entry.reference,
        "source_module": entry.source_module,
        "source_document_type": entry.source_document_type,
        "source_document_id": str(entry.source_document_id) if entry.source_document_id else None,
        "debit_total": str(sum((Decimal(str(line.debit or 0)) for line in entry.lines), Decimal("0"))),
        "credit_total": str(sum((Decimal(str(line.credit or 0)) for line in entry.lines), Decimal("0"))),
    }
    actor_id = entry.posted_by_id or entry.created_by_id
    actor = session.scalar(select(User).where(User.id == actor_id)) if actor_id else None
    role_slugs: list[str] = []
    if actor_id:
        role_slugs = [
            role.slug
            for role in session.scalars(select(Role).join(User.roles).where(User.id == actor_id)).all()
        ]
    session.add(
        FinanceAuditLog(
            tenant_id=entry.tenant_id,
            entity_type="journal_entry",
            entity_id=entry.id,
            action="post",
            source_module=entry.source_module or "finance",
            actor_id=actor_id,
            actor_email=actor.email if actor else "system",
            actor_role=",".join(role_slugs) if role_slugs else None,
            before_state=before,
            after_state=after,
        )
    )
    enqueue_outbox_sync(
        session,
        tenant_id=entry.tenant_id,
        event_type="journal.posted",
        aggregate_type="journal_entry",
        aggregate_id=entry.id,
        payload=after,
    )
    period = None
    if entry.tenant_id:
        period = session.scalar(
            select(FinancialPeriod).where(
                FinancialPeriod.tenant_id == entry.tenant_id,
                FinancialPeriod.start_date <= entry.entry_date,
                FinancialPeriod.end_date >= entry.entry_date,
            )
        )
    for line in entry.lines:
        stmt = select(LedgerBalance).where(
            LedgerBalance.tenant_id == entry.tenant_id,
            LedgerBalance.account_id == line.account_id,
        )
        stmt = (
            stmt.where(LedgerBalance.period_id == period.id)
            if period is not None
            else stmt.where(LedgerBalance.period_id.is_(None))
        )
        balance = session.scalar(stmt)
        if balance is None:
            balance = LedgerBalance(
                tenant_id=entry.tenant_id,
                account_id=line.account_id,
                period_id=period.id if period else None,
                opening_balance=Decimal("0"),
                debit_total=Decimal("0"),
                credit_total=Decimal("0"),
                closing_balance=Decimal("0"),
            )
            session.add(balance)
        balance.debit_total = Decimal(str(balance.debit_total or 0)) + Decimal(str(line.debit or 0))
        balance.credit_total = Decimal(str(balance.credit_total or 0)) + Decimal(str(line.credit or 0))
        balance.closing_balance = balance.opening_balance + balance.debit_total - balance.credit_total


@event.listens_for(Session, "before_flush")
def _capture_posted_journals(session: Session, flush_context: Any, instances: Any) -> None:
    transitioned: list[JournalEntry] = []
    new_objects = set(session.new)
    for obj in list(session.new) + list(session.dirty):
        if not isinstance(obj, JournalEntry) or obj.status != "posted":
            continue
        state = inspect(obj)
        history = state.attrs.status.history
        if obj in new_objects or (history.added and "posted" in history.added):
            if obj not in transitioned:
                transitioned.append(obj)
    if not transitioned:
        return
    with session.no_autoflush:
        for entry in transitioned:
            if entry.id is None:
                from uuid import uuid4

                entry.id = uuid4()
            journal_posted_effects_sync(session, entry)


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def verify_signature(secret: str, body: bytes, signature: str | None) -> bool:
    if not signature:
        return False
    return hmac.compare_digest(sign_payload(secret, body), signature)


async def dispatch_outbox(
    db: AsyncSession, *, limit: int = 50, force: bool = False
) -> dict[str, int]:
    """Deliver pending outbox events to subscribed webhooks with HMAC signatures and retries."""
    now = datetime.now(timezone.utc)
    stmt = (
        select(OutboxEvent)
        .where(OutboxEvent.status.in_(("pending", "failed")))
        .order_by(OutboxEvent.created_at)
        .limit(limit)
    )
    if not force:
        stmt = stmt.where(
            (OutboxEvent.next_attempt_at.is_(None)) | (OutboxEvent.next_attempt_at <= now)
        )
    events = list((await db.scalars(stmt)).all())
    delivered = 0
    retried = 0
    dead = 0
    for outbox_event in events:
        endpoints = list(
            (
                await db.scalars(
                    select(WebhookEndpoint).where(
                        WebhookEndpoint.tenant_id == outbox_event.tenant_id,
                        WebhookEndpoint.is_enabled.is_(True),
                    )
                )
            ).all()
        )
        endpoints = [
            endpoint
            for endpoint in endpoints
            if not endpoint.event_types or outbox_event.event_type in endpoint.event_types
        ]
        if not endpoints:
            outbox_event.status = "published"
            outbox_event.published_at = now
            delivered += 1
            continue
        all_ok = True
        for endpoint in endpoints:
            delivery = await db.scalar(
                select(WebhookDelivery).where(
                    WebhookDelivery.endpoint_id == endpoint.id,
                    WebhookDelivery.outbox_event_id == outbox_event.id,
                )
            )
            if delivery is None:
                delivery = WebhookDelivery(
                    tenant_id=outbox_event.tenant_id,
                    endpoint_id=endpoint.id,
                    outbox_event_id=outbox_event.id,
                    status="pending",
                )
                db.add(delivery)
            if delivery.status == "delivered":
                continue
            body = json.dumps(
                {
                    "id": str(outbox_event.id),
                    "type": outbox_event.event_type,
                    "tenant_id": str(outbox_event.tenant_id),
                    "occurred_at": outbox_event.created_at.isoformat()
                    if outbox_event.created_at
                    else now.isoformat(),
                    "data": outbox_event.payload,
                },
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.post(
                        endpoint.url,
                        content=body,
                        headers={
                            "content-type": "application/json",
                            "x-hertex-signature": sign_payload(endpoint.secret, body),
                            "x-hertex-event": outbox_event.event_type,
                        },
                    )
                delivery.response_status = response.status_code
                response.raise_for_status()
                delivery.status = "delivered"
                delivery.delivered_at = now
                delivery.last_error = None
            except Exception as exc:
                all_ok = False
                delivery.status = "failed"
                delivery.last_error = str(exc)[:2000]
                delivery.attempts += 1
                if delivery.attempts >= MAX_OUTBOX_ATTEMPTS:
                    delivery.status = "dead"
                    dead += 1
                else:
                    delivery.next_attempt_at = now + timedelta(
                        minutes=RETRY_BACKOFF_MINUTES * (2 ** (delivery.attempts - 1))
                    )
                    retried += 1
        if all_ok:
            outbox_event.status = "published"
            outbox_event.published_at = now
            outbox_event.last_error = None
            delivered += 1
        else:
            outbox_event.status = "failed"
            outbox_event.attempts += 1
            outbox_event.next_attempt_at = now + timedelta(minutes=RETRY_BACKOFF_MINUTES)
            outbox_event.last_error = "One or more webhook deliveries failed"
    await db.flush()
    return {"processed": len(events), "delivered": delivered, "retried": retried, "dead": dead}


async def retry_dead_letter(
    db: AsyncSession, *, event_id: UUID, user: User
) -> dict[str, Any]:
    event = await db.scalar(
        _scope(select(OutboxEvent).where(OutboxEvent.id == event_id), OutboxEvent, user)
    )
    if event is None:
        raise NotFoundError("Outbox event not found")
    if event.status != "dead":
        raise ConflictError("Only dead-letter events can be retried")
    event.status = "pending"
    event.attempts = 0
    event.next_attempt_at = datetime.now(timezone.utc)
    event.last_error = None
    for delivery in (
        await db.scalars(select(WebhookDelivery).where(WebhookDelivery.outbox_event_id == event.id))
    ).all():
        if delivery.status == "dead":
            delivery.status = "pending"
            delivery.attempts = 0
            delivery.next_attempt_at = datetime.now(timezone.utc)
            delivery.last_error = None
    await db.flush()
    return {"status": event.status, "message": "Dead-letter event queued for retry"}
