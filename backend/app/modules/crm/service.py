import hashlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.crud import tenant_scoped
from app.core.events import publish
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationError
from app.modules.crm.models import (
    Activity,
    Call,
    CallAssessment,
    CallTranscript,
    Company,
    ConsentRecord,
    Contact,
    Deal,
    Engagement,
    InboxAssignment,
    Lead,
    LeadSource,
    OutboxEvent,
    ScoreFact,
    SocialAccount,
    SocialPost,
    Stage,
)
from app.modules.crm.schemas import (
    DealStageRequest,
    EngagementCreate,
    LeadConvertRequest,
    SocialPostCreate,
)
from app.modules.crm.scoring import rescore_lead
from app.modules.identity.models import User

CONSENT_POLICY = "2026-11"
RUBRIC_VERSION = "rubric-v1"


def phone_key(value: Optional[str]) -> str:
    return re.sub(r"\D", "", value or "")


def dedupe_key(email: Optional[str], phone: Optional[str]) -> Optional[str]:
    if email:
        return f"email:{email.strip().lower()}"
    digits = phone_key(phone)
    return f"phone:{digits}" if digits else None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def require_tenant(user: User) -> UUID:
    tenant_id = user.tenant_id
    if tenant_id is None:
        raise ForbiddenError("Tenant context required")
    return tenant_id


async def get_scoped(db: AsyncSession, model, item_id: UUID, user: User):
    obj = await db.scalar(tenant_scoped(select(model), model, user).where(model.id == item_id))
    if obj is None:
        raise NotFoundError(f"{model.__name__} not found")
    return obj


async def seed_default_pipeline(db: AsyncSession, tenant_id: UUID) -> None:
    defaults = [
        ("qualification", "Qualification", 10, 20, False, False),
        ("proposal", "Proposal", 20, 40, False, False),
        ("negotiation", "Negotiation", 30, 65, False, False),
        ("won", "Won", 40, 100, True, False),
        ("lost", "Lost", 50, 0, False, True),
    ]
    for code, name, sequence, probability, is_won, is_lost in defaults:
        existing = await db.scalar(
            select(Stage).where(Stage.tenant_id == tenant_id, Stage.code == code)
        )
        if existing is None:
            db.add(
                Stage(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    sequence=sequence,
                    probability_default=probability,
                    is_won=is_won,
                    is_lost=is_lost,
                )
            )
    sources = [
        ("manual", "Manual", "manual"),
        ("website", "Website", "website"),
        ("referral", "Referral", "referral"),
        ("whatsapp", "WhatsApp", "whatsapp"),
        ("instagram", "Instagram", "instagram"),
        ("facebook", "Facebook", "facebook"),
        ("meta_lead_ads", "Meta lead ads", "meta"),
        ("event", "Event", "event"),
    ]
    for code, name, channel in sources:
        existing = await db.scalar(
            select(LeadSource).where(LeadSource.tenant_id == tenant_id, LeadSource.code == code)
        )
        if existing is None:
            db.add(
                LeadSource(
                    tenant_id=tenant_id,
                    code=code,
                    name=name,
                    channel=channel,
                )
            )
    await db.flush()


async def capture_consent(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    subject_type: str,
    subject_id: UUID,
    channel: str,
    status: str,
    source: str,
    policy_version: str = CONSENT_POLICY,
    proof_ref: Optional[str] = None,
    captured_at: Optional[datetime] = None,
    actor_id: Optional[UUID] = None,
) -> ConsentRecord:
    if subject_type not in {"lead", "contact"}:
        raise ValidationError("Consent subject must be a lead or contact")
    model = Lead if subject_type == "lead" else Contact
    subject = await db.scalar(
        select(model).where(model.id == subject_id, model.tenant_id == tenant_id)
    )
    if subject is None:
        raise NotFoundError(f"{subject_type.title()} not found")

    record = ConsentRecord(
        tenant_id=tenant_id,
        created_by_id=actor_id,
        subject_type=subject_type,
        subject_id=subject_id,
        channel=channel,
        status=status,
        source=source,
        policy_version=policy_version,
        proof_ref=proof_ref,
        captured_at=captured_at or _now(),
    )
    db.add(record)
    subject.whatsapp_opt_in = status == "opted_in" if channel == "whatsapp" else subject.whatsapp_opt_in
    subject.consent_captured_at = record.captured_at
    subject.consent_source = source
    await db.flush()
    return record


async def current_consent(
    db: AsyncSession,
    tenant_id: UUID,
    subject_type: str,
    subject_id: UUID,
    channel: str,
) -> Optional[ConsentRecord]:
    return await db.scalar(
        select(ConsentRecord)
        .where(
            ConsentRecord.tenant_id == tenant_id,
            ConsentRecord.subject_type == subject_type,
            ConsentRecord.subject_id == subject_id,
            ConsentRecord.channel == channel,
        )
        .order_by(ConsentRecord.captured_at.desc(), ConsentRecord.created_at.desc())
        .limit(1)
    )


async def find_or_create_lead(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    name: str,
    email: Optional[str] = None,
    phone: Optional[str] = None,
    source: str = "manual",
    external_ref: Optional[str] = None,
    whatsapp_opt_in: bool = False,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    actor_id: Optional[UUID] = None,
) -> tuple[Lead, bool]:
    lead: Optional[Lead] = None
    if external_ref:
        lead = await db.scalar(
            select(Lead).where(Lead.tenant_id == tenant_id, Lead.external_ref == external_ref)
        )
    if lead is None and email:
        lead = await db.scalar(
            select(Lead).where(
                Lead.tenant_id == tenant_id,
                func.lower(Lead.email) == email.strip().lower(),
            )
        )
    if lead is None and phone:
        candidates = await db.scalars(
            select(Lead).where(Lead.tenant_id == tenant_id, Lead.phone.is_not(None))
        )
        target = phone_key(phone)
        lead = next((item for item in candidates if phone_key(item.phone) == target), None)

    created = lead is None
    if lead is None:
        lead = Lead(
            tenant_id=tenant_id,
            created_by_id=actor_id,
            name=name,
            email=email,
            phone=phone,
            source=source,
            status="new",
            whatsapp_opt_in=whatsapp_opt_in,
            external_ref=external_ref,
            dedupe_key=dedupe_key(email, phone),
            utm_source=utm_source,
            utm_medium=utm_medium,
            utm_campaign=utm_campaign,
        )
        db.add(lead)
        await db.flush()
        await rescore_lead(db, lead, source_event_id=f"lead:{lead.id}:created", commit=False)
    else:
        if whatsapp_opt_in and not lead.whatsapp_opt_in:
            lead.whatsapp_opt_in = True
        if external_ref and not lead.external_ref:
            lead.external_ref = external_ref
        for field, value in (
            ("utm_source", utm_source),
            ("utm_medium", utm_medium),
            ("utm_campaign", utm_campaign),
        ):
            if value and not getattr(lead, field):
                setattr(lead, field, value)
        await db.flush()
    return lead, created


async def record_engagement(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    channel: str,
    direction: str,
    occurred_at: Optional[datetime],
    lead_id: Optional[UUID],
    summary: Optional[str],
    payload: dict[str, Any],
    external_ref: Optional[str] = None,
    contact_id: Optional[UUID] = None,
    deal_id: Optional[UUID] = None,
    actor_id: Optional[UUID] = None,
    commit: bool = True,
) -> Optional[Engagement]:
    if external_ref:
        existing = await db.scalar(
            select(Engagement).where(
                Engagement.tenant_id == tenant_id,
                Engagement.channel == channel,
                Engagement.external_ref == external_ref,
            )
        )
        if existing is not None:
            return None

    event_id = external_ref or f"engagement:{uuid4().hex}"
    engagement = Engagement(
        tenant_id=tenant_id,
        created_by_id=actor_id,
        channel=channel,
        direction=direction,
        occurred_at=occurred_at or _now(),
        lead_id=lead_id,
        contact_id=contact_id,
        deal_id=deal_id,
        external_ref=external_ref,
        summary=summary,
        payload=payload,
        source_event_id=event_id,
    )
    db.add(engagement)
    if lead_id:
        lead = await db.scalar(select(Lead).where(Lead.id == lead_id, Lead.tenant_id == tenant_id))
        if lead is not None:
            lead.engagement_count = (lead.engagement_count or 0) + 1
            lead.last_activity_at = engagement.occurred_at
            if direction == "inbound" and lead.status == "new":
                lead.status = "contacted"
            await rescore_lead(
                db, lead, source_event_id=f"{event_id}:score", commit=False
            )
    await db.flush()
    if commit:
        await db.commit()
        await db.refresh(engagement)
        await publish(
            "engagement.received",
            {
                "tenant_id": str(tenant_id),
                "engagement_id": str(engagement.id),
                "lead_id": str(lead_id) if lead_id else None,
                "channel": channel,
            },
        )
    return engagement


async def ingest_channel_message(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    message_id: str,
    phone: str,
    contact_name: str | None,
    body: str,
    occurred_at: datetime | None,
    payload: dict[str, Any],
    actor_id: UUID | None = None,
) -> tuple[Lead, Engagement]:
    lead, _ = await find_or_create_lead(
        db,
        tenant_id,
        name=contact_name or f"WhatsApp {phone}",
        phone=phone,
        source="whatsapp",
        external_ref=f"whatsapp:{phone_key(phone)}",
        whatsapp_opt_in=True,
        actor_id=actor_id,
    )
    await capture_consent(
        db,
        tenant_id,
        subject_type="lead",
        subject_id=lead.id,
        channel="whatsapp",
        status="opted_in",
        source="whatsapp.inbound_session",
        actor_id=actor_id,
    )
    engagement = await record_engagement(
        db,
        tenant_id,
        channel="whatsapp",
        direction="inbound",
        occurred_at=occurred_at,
        lead_id=lead.id,
        summary=body[:200] or "WhatsApp message received",
        payload=payload,
        external_ref=f"whatsapp:{message_id}",
        actor_id=actor_id,
        commit=False,
    )
    if engagement is None:
        raise ConflictError("WhatsApp message has already been ingested")
    await assign_inbox_conversation(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        conversation_key=phone,
        channel="whatsapp",
        assignee_id=None,
        status="open",
        sla_minutes=60,
        external_ref=message_id,
        lead_id=lead.id,
    )
    await db.commit()
    await db.refresh(lead)
    await db.refresh(engagement)
    return lead, engagement


async def ingest_meta_lead(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    external_ref: str,
    name: str,
    email: str | None,
    phone: str | None,
    utm_source: str | None,
    utm_medium: str | None,
    utm_campaign: str | None,
    payload: dict[str, Any],
    actor_id: UUID | None = None,
) -> tuple[Lead, bool]:
    lead, created = await find_or_create_lead(
        db,
        tenant_id,
        name=name,
        email=email,
        phone=phone,
        source="meta_lead_ads",
        external_ref=external_ref,
        whatsapp_opt_in=bool(phone),
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        actor_id=actor_id,
    )
    if phone:
        await capture_consent(
            db,
            tenant_id,
            subject_type="lead",
            subject_id=lead.id,
            channel="whatsapp",
            status="opted_in",
            source="meta.leadgen",
            actor_id=actor_id,
        )
    await record_engagement(
        db,
        tenant_id,
        channel="meta_lead_ads",
        direction="inbound",
        occurred_at=_now(),
        lead_id=lead.id,
        summary=f"Meta lead {external_ref}",
        payload=payload,
        external_ref=f"meta_lead:{external_ref}",
        actor_id=actor_id,
        commit=False,
    )
    await db.commit()
    await db.refresh(lead)
    return lead, created


async def enqueue_outbox(
    db: AsyncSession,
    tenant_id: UUID,
    event_type: str,
    *,
    entity_type: str,
    entity_id: Optional[UUID],
    payload: dict[str, Any],
    correlation_id: Optional[str] = None,
) -> OutboxEvent:
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        correlation_id=correlation_id,
    )
    db.add(event)
    await db.flush()
    return event


async def dispatch_outbox(db: AsyncSession, user: User) -> int:
    events = list(
        (
            await db.scalars(
                tenant_scoped(select(OutboxEvent), OutboxEvent, user).where(
                    OutboxEvent.status == "pending"
                )
            )
        ).all()
    )
    for event in events:
        event.attempts += 1
        await publish(
            event.event_type,
            {
                "tenant_id": str(event.tenant_id) if event.tenant_id else None,
                "entity_type": event.entity_type,
                "entity_id": str(event.entity_id) if event.entity_id else None,
                **event.payload,
            },
            correlation_id=event.correlation_id,
        )
        event.status = "dispatched"
        event.dispatched_at = _now()
    await db.commit()
    return len(events)


async def convert_lead(
    db: AsyncSession, user: User, lead_id: UUID, request: LeadConvertRequest
) -> dict[str, Any]:
    lead = await get_scoped(db, Lead, lead_id, user)
    if lead.converted_deal_id:
        raise ConflictError("Lead has already been converted")
    if lead.status in {"won", "lost", "converted"}:
        raise ConflictError("A closed lead cannot be converted")

    stage = None
    if request.stage_id:
        stage = await get_scoped(db, Stage, request.stage_id, user)
    elif request.stage:
        stage = await db.scalar(
            select(Stage).where(Stage.tenant_id == require_tenant(user), Stage.code == request.stage)
        )

    company_id = None
    if lead.company_name:
        company = Company(
            tenant_id=require_tenant(user),
            created_by_id=user.id,
            name=lead.company_name,
            email=lead.email,
            phone=lead.phone,
        )
        db.add(company)
        await db.flush()
        company_id = company.id

    contact_id = None
    if request.create_contact and (lead.name or lead.email or lead.phone):
        first, _, last = (lead.name or "").partition(" ")
        contact = Contact(
            tenant_id=require_tenant(user),
            created_by_id=user.id,
            company_id=company_id,
            first_name=first or "Lead",
            last_name=last,
            email=lead.email,
            phone=lead.phone,
            whatsapp_opt_in=lead.whatsapp_opt_in,
        )
        db.add(contact)
        await db.flush()
        contact_id = contact.id
        if lead.whatsapp_opt_in:
            await capture_consent(
                db,
                require_tenant(user),
                subject_type="contact",
                subject_id=contact_id,
                channel="whatsapp",
                status="opted_in",
                source="lead.conversion",
                actor_id=user.id,
            )

    deal = Deal(
        tenant_id=require_tenant(user),
        created_by_id=user.id,
        name=request.deal_name or f"{lead.name} opportunity",
        company_id=company_id,
        contact_id=contact_id,
        lead_id=lead.id,
        stage=stage.code if stage else (request.stage or "qualification"),
        stage_id=stage.id if stage else None,
        amount=request.amount if request.amount is not None else lead.estimated_value or Decimal("0"),
        probability=stage.probability_default if stage else 20,
        weighted_amount=(request.amount if request.amount is not None else lead.estimated_value or Decimal("0"))
        * Decimal((stage.probability_default if stage else 20) / 100),
        expected_close_date=request.expected_close_date,
        owner_id=lead.owner_id or user.id,
    )
    db.add(deal)
    await db.flush()
    weighted = Decimal(deal.amount or 0) * Decimal(deal.probability or 0) / Decimal(100)
    deal.weighted_amount = weighted.quantize(Decimal("0.01"))

    lead.status = "converted"
    lead.converted_deal_id = deal.id
    await rescore_lead(db, lead, user=user, source_event_id=f"lead:{lead.id}:converted", commit=False)
    await enqueue_outbox(
        db,
        require_tenant(user),
        "lead.converted",
        entity_type="Lead",
        entity_id=lead.id,
        payload={
            "lead_id": str(lead.id),
            "deal_id": str(deal.id),
            "company_id": str(company_id) if company_id else None,
            "contact_id": str(contact_id) if contact_id else None,
        },
    )
    await record_audit(
        db,
        user=user,
        action="convert",
        module="crm",
        entity="Lead",
        entity_id=lead.id,
        changes={"deal_id": str(deal.id), "status": "converted"},
    )
    await db.commit()
    await publish(
        "lead.converted",
        {
            "tenant_id": str(require_tenant(user)),
            "lead_id": str(lead.id),
            "deal_id": str(deal.id),
            "company_id": str(company_id) if company_id else None,
            "contact_id": str(contact_id) if contact_id else None,
        },
    )
    return {
        "lead_id": lead.id,
        "deal_id": deal.id,
        "company_id": company_id,
        "contact_id": contact_id,
        "events": ["lead.converted"],
    }


async def transition_deal(
    db: AsyncSession,
    user: User,
    deal_id: UUID,
    action: str,
    request: DealStageRequest,
) -> Deal:
    deal = await get_scoped(db, Deal, deal_id, user)
    if deal.won_at or deal.lost_at:
        raise ConflictError("Deal is already closed")

    stage = None
    if request.stage_id:
        stage = await get_scoped(db, Stage, request.stage_id, user)
    elif request.stage:
        stage = await db.scalar(
            select(Stage).where(Stage.tenant_id == require_tenant(user), Stage.code == request.stage)
        )

    if action == "win":
        stage = stage or await db.scalar(
            select(Stage).where(Stage.tenant_id == require_tenant(user), Stage.is_won.is_(True))
        )
        if stage and not stage.is_won:
            raise ValidationError("Target stage is not a won stage")
        deal.stage = stage.code if stage else "won"
        deal.stage_id = stage.id if stage else None
        deal.probability = 100
        deal.won_at = _now()
        deal.won_event_id = f"deal.won:{deal.id}"
        event_type = "deal.won"
    elif action == "lose":
        stage = stage or await db.scalar(
            select(Stage).where(Stage.tenant_id == require_tenant(user), Stage.is_lost.is_(True))
        )
        if stage and not stage.is_lost:
            raise ValidationError("Target stage is not a lost stage")
        deal.stage = stage.code if stage else "lost"
        deal.stage_id = stage.id if stage else None
        deal.probability = 0
        deal.lost_at = _now()
        deal.lost_reason = request.reason
        event_type = "deal.lost"
    else:
        if stage is None:
            raise ValidationError("A target stage is required")
        current = await db.scalar(
            select(Stage).where(
                Stage.tenant_id == require_tenant(user), Stage.code == deal.stage
            )
        )
        if current and stage.sequence <= current.sequence:
            raise ValidationError("Deals can only move forward to a later stage")
        deal.stage = stage.code
        deal.stage_id = stage.id
        deal.probability = stage.probability_default
        event_type = "deal.advanced"

    if request.next_step:
        deal.next_step = request.next_step
    if request.next_step_due:
        deal.next_step_due = request.next_step_due
    deal.weighted_amount = (Decimal(deal.amount or 0) * Decimal(deal.probability or 0) / Decimal(100)).quantize(Decimal("0.01"))

    if deal.lead_id:
        lead = await db.scalar(select(Lead).where(Lead.id == deal.lead_id))
        if lead is not None and event_type == "deal.won":
            lead.status = "won"
            lead.lost_reason = None
            await rescore_lead(db, lead, user=user, source_event_id=f"{deal.won_event_id}:score", commit=False)
        elif lead is not None and event_type == "deal.lost":
            lead.status = "lost"
            lead.lost_reason = request.reason
            await rescore_lead(db, lead, user=user, source_event_id=f"deal.lost:{deal.id}:score", commit=False)

    await enqueue_outbox(
        db,
        require_tenant(user),
        event_type,
        entity_type="Deal",
        entity_id=deal.id,
        payload={
            "deal_id": str(deal.id),
            "stage": deal.stage,
            "amount": str(deal.amount),
            "lead_id": str(deal.lead_id) if deal.lead_id else None,
        },
    )
    await record_audit(
        db,
        user=user,
        action="transition",
        module="crm",
        entity="Deal",
        entity_id=deal.id,
        changes={"action": action, "stage": deal.stage, "reason": request.reason},
    )
    await db.commit()
    await publish(
        event_type,
        {
            "tenant_id": str(require_tenant(user)),
            "deal_id": str(deal.id),
            "lead_id": str(deal.lead_id) if deal.lead_id else None,
            "stage": deal.stage,
        },
    )
    return deal


async def merge_leads(db: AsyncSession, user: User, primary_id: UUID, duplicate_id: UUID) -> Lead:
    primary = await get_scoped(db, Lead, primary_id, user)
    duplicate = await get_scoped(db, Lead, duplicate_id, user)
    if primary.id == duplicate.id:
        raise ValidationError("Cannot merge a lead into itself")

    for model in (Engagement, Deal, Activity, ConsentRecord):
        field = "lead_id" if model is not ConsentRecord else "subject_id"
        rows = await db.scalars(
            select(model).where(model.tenant_id == require_tenant(user), field == duplicate.id)
        )
        for row in rows:
            setattr(row, field, primary.id)

    primary.engagement_count = (primary.engagement_count or 0) + (duplicate.engagement_count or 0)
    primary.last_activity_at = max(
        [value for value in (primary.last_activity_at, duplicate.last_activity_at) if value],
        default=None,
    )
    if not primary.phone and duplicate.phone:
        primary.phone = duplicate.phone
    if not primary.email and duplicate.email:
        primary.email = duplicate.email
    duplicate.is_active = False
    duplicate.notes = f"{duplicate.notes or ''}\nMerged into {primary.id}".strip()
    await rescore_lead(db, primary, user=user, source_event_id=f"lead:{primary.id}:merge", commit=False)
    await enqueue_outbox(
        db,
        require_tenant(user),
        "lead.merged",
        entity_type="Lead",
        entity_id=primary.id,
        payload={"primary_id": str(primary.id), "duplicate_id": str(duplicate.id)},
    )
    await record_audit(
        db,
        user=user,
        action="merge",
        module="crm",
        entity="Lead",
        entity_id=primary.id,
        changes={"duplicate_id": str(duplicate.id)},
    )
    await db.commit()
    return primary


async def create_engagement(db: AsyncSession, user: User, request: EngagementCreate) -> Engagement:
    engagement = await record_engagement(
        db,
        require_tenant(user),
        channel=request.channel,
        direction=request.direction,
        occurred_at=request.occurred_at,
        lead_id=request.lead_id,
        contact_id=request.contact_id,
        deal_id=request.deal_id,
        external_ref=request.external_ref,
        summary=request.summary,
        payload=request.payload,
        actor_id=user.id,
        commit=False,
    )
    if engagement is None:
        raise ConflictError("Engagement already exists")
    await db.commit()
    await db.refresh(engagement)
    return engagement


async def pipeline_report(db: AsyncSession, user: User) -> dict[str, Any]:
    deals = list((await db.scalars(tenant_scoped(select(Deal), Deal, user))).all())
    stages = list((await db.scalars(tenant_scoped(select(Stage), Stage, user))).all())
    total = len(deals)
    weighted = sum((deal.weighted_amount or Decimal("0") for deal in deals), Decimal("0"))
    stage_rows = []
    for stage in sorted(stages, key=lambda item: item.sequence):
        items = [deal for deal in deals if deal.stage == stage.code]
        stage_rows.append(
            {
                "code": stage.code,
                "name": stage.name,
                "sequence": stage.sequence,
                "count": len(items),
                "amount": str(sum((deal.amount or Decimal("0") for deal in items), Decimal("0"))),
                "weighted_amount": str(
                    sum((deal.weighted_amount or Decimal("0") for deal in items), Decimal("0"))
                ),
            }
        )
    owner_totals: dict[str, dict[str, Any]] = {}
    for deal in deals:
        key = str(deal.owner_id) if deal.owner_id else "unassigned"
        row = owner_totals.setdefault(key, {"owner_id": key, "count": 0, "amount": Decimal("0")})
        row["count"] += 1
        row["amount"] += deal.amount or Decimal("0")
    return {
        "total": total,
        "weighted_amount": weighted,
        "stages": stage_rows,
        "owners": [
            {"owner_id": row["owner_id"], "count": row["count"], "amount": str(row["amount"])}
            for row in owner_totals.values()
        ],
    }


async def assess_call(db: AsyncSession, user: User, call_id: UUID) -> CallAssessment:
    call = await get_scoped(db, Call, call_id, user)
    transcripts = list(
        (
            await db.scalars(
                select(CallTranscript)
                .where(CallTranscript.call_id == call.id)
                .order_by(CallTranscript.sequence)
            )
        ).all()
    )
    text = " ".join(item.text.lower() for item in transcripts)
    signals = {
        "budget": any(word in text for word in ("budget", "price", "cost")),
        "timeline": any(word in text for word in ("deadline", "timeline", "urgent", "this month")),
        "decision_maker": any(word in text for word in ("decision", "approve", "owner")),
        "objection": any(word in text for word in ("concern", "expensive", "objection")),
        "next_step": any(word in text for word in ("follow up", "demo", "proposal", "meeting")),
    }
    score = 35
    for key in ("budget", "timeline", "decision_maker", "next_step"):
        if signals[key]:
            score += 15
    if signals["objection"]:
        score -= 10
    score = max(0, min(100, score))
    next_action = "Book a follow-up demo" if signals["next_step"] else "Confirm next step with the prospect"
    assessment = CallAssessment(
        tenant_id=require_tenant(user),
        created_by_id=user.id,
        call_id=call.id,
        rubric_version=RUBRIC_VERSION,
        score=score,
        signals=signals,
        summary=f"Call covered {sum(1 for value in signals.values() if value)} of 5 qualification signals.",
        next_best_action=next_action,
        status="draft",
    )
    db.add(assessment)
    call.status = "assessed"
    if call.lead_id:
        await record_engagement(
            db,
            require_tenant(user),
            channel="call",
            direction=call.direction,
            occurred_at=call.started_at or _now(),
            lead_id=call.lead_id,
            summary=f"AI call assessment {score}/100",
            payload={"call_id": str(call.id), "signals": signals},
            external_ref=f"call:{call.id}",
            actor_id=user.id,
            commit=False,
        )
    await record_audit(
        db,
        user=user,
        action="assess",
        module="crm",
        entity="Call",
        entity_id=call.id,
        changes={"score": score, "rubric_version": RUBRIC_VERSION},
    )
    await db.commit()
    await publish(
        "call.assessed",
        {
            "tenant_id": str(require_tenant(user)),
            "call_id": str(call.id),
            "assessment_id": str(assessment.id),
            "score": score,
        },
    )
    return assessment


async def approve_assessment(
    db: AsyncSession, user: User, assessment_id: UUID, status: str
) -> CallAssessment:
    assessment = await get_scoped(db, CallAssessment, assessment_id, user)
    if assessment.status in {"approved", "rejected"}:
        raise ConflictError("Assessment has already been reviewed")
    assessment.status = status
    assessment.reviewer_id = user.id
    assessment.reviewed_at = _now()
    await record_audit(
        db,
        user=user,
        action="approve" if status == "approved" else "reject",
        module="crm",
        entity="CallAssessment",
        entity_id=assessment.id,
        changes={"status": status},
    )
    await db.commit()
    await publish(
        "call.assessment.reviewed",
        {
            "tenant_id": str(require_tenant(user)),
            "assessment_id": str(assessment.id),
            "call_id": str(assessment.call_id),
            "status": status,
        },
    )
    return assessment


async def create_social_post(db: AsyncSession, user: User, request: SocialPostCreate) -> SocialPost:
    account = await get_scoped(db, SocialAccount, request.account_id, user)
    if not account.is_active:
        raise ValidationError("Social account is inactive")
    post = SocialPost(
        tenant_id=require_tenant(user),
        created_by_id=user.id,
        account_id=account.id,
        body=request.body,
        media_refs=request.media_refs,
        status="draft",
        scheduled_at=request.scheduled_at,
        campaign_id=request.campaign_id,
    )
    db.add(post)
    await record_audit(
        db,
        user=user,
        action="create",
        module="crm",
        entity="SocialPost",
        entity_id=post.id,
        changes={"channel": account.channel, "status": "draft"},
    )
    await db.commit()
    await db.refresh(post)
    return post


async def approve_social_post(db: AsyncSession, user: User, post_id: UUID) -> SocialPost:
    post = await get_scoped(db, SocialPost, post_id, user)
    if post.status not in {"draft", "pending_approval"}:
        raise ConflictError("Only draft posts can be approved")
    post.status = "approved"
    post.approved_by_id = user.id
    await record_audit(
        db,
        user=user,
        action="approve",
        module="crm",
        entity="SocialPost",
        entity_id=post.id,
        changes={"status": "approved"},
    )
    await db.commit()
    return post


async def publish_social_post(db: AsyncSession, user: User, post_id: UUID) -> SocialPost:
    post = await get_scoped(db, SocialPost, post_id, user)
    if post.status not in {"approved", "scheduled"}:
        raise ConflictError("Social post must be approved before publishing")
    if post.external_post_id:
        raise ConflictError("Social post has already been published")
    digest = hashlib.sha256(f"{post.id}:{_now().isoformat()}".encode()).hexdigest()[:16]
    post.external_post_id = f"local-{digest}"
    post.status = "published"
    post.published_at = _now()
    await enqueue_outbox(
        db,
        require_tenant(user),
        "social.post.published",
        entity_type="SocialPost",
        entity_id=post.id,
        payload={"post_id": str(post.id), "external_post_id": post.external_post_id},
    )
    await record_audit(
        db,
        user=user,
        action="publish",
        module="crm",
        entity="SocialPost",
        entity_id=post.id,
        changes={"external_post_id": post.external_post_id},
    )
    await db.commit()
    await publish(
        "social.post.published",
        {
            "tenant_id": str(require_tenant(user)),
            "post_id": str(post.id),
            "external_post_id": post.external_post_id,
        },
    )
    return post


async def assign_inbox_conversation(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    actor_id: Optional[UUID],
    conversation_key: str,
    channel: str,
    assignee_id: Optional[UUID],
    status: str,
    sla_minutes: int,
    external_ref: Optional[str] = None,
    lead_id: Optional[UUID] = None,
    contact_id: Optional[UUID] = None,
) -> InboxAssignment:
    assignment = await db.scalar(
        select(InboxAssignment).where(
            InboxAssignment.tenant_id == tenant_id,
            InboxAssignment.conversation_key == conversation_key,
        )
    )
    if assignment is None:
        assignment = InboxAssignment(
            tenant_id=tenant_id,
            created_by_id=actor_id,
            conversation_key=conversation_key,
            channel=channel,
            external_ref=external_ref,
            lead_id=lead_id,
            contact_id=contact_id,
        )
        db.add(assignment)
    assignment.assignee_id = assignee_id
    assignment.status = status
    assignment.sla_due_at = _now() + timedelta(minutes=sla_minutes)
    if status == "closed":
        assignment.closed_at = _now()
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def lead_score_explanation(db: AsyncSession, user: User, lead_id: UUID) -> dict[str, Any]:
    lead = await get_scoped(db, Lead, lead_id, user)
    facts = list(
        (
            await db.scalars(
                tenant_scoped(select(ScoreFact), ScoreFact, user)
                .where(ScoreFact.lead_id == lead.id)
                .order_by(ScoreFact.computed_at.desc())
                .limit(10)
            )
        ).all()
    )
    top_features = (lead.score_features or {}).get("top_features", [])
    return {
        "lead_id": lead.id,
        "score": lead.score,
        "grade": lead.score_grade,
        "trend": lead.score_trend,
        "model_version": lead.score_model_version,
        "top_features": top_features,
        "facts": facts,
    }
