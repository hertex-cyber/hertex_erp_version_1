from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import tenant_scoped
from app.core.deps import require_permissions
from app.core.exceptions import NotFoundError
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.crm.models import (
    Call,
    CallAssessment,
    CallTranscript,
    ConsentRecord,
    Lead,
    OutboxEvent,
    Stage,
)
from app.modules.crm.schemas import (
    AssessmentApproveRequest,
    CallAssessmentRead,
    ConsentCaptureRequest,
    ConsentRead,
    ConsentStateRead,
    DealRead,
    DealStageRequest,
    EngagementCreate,
    EngagementRead,
    InboxAssignmentRead,
    InboxAssignRequest,
    InboxReplyRequest,
    LeadConvertRequest,
    LeadConvertResult,
    LeadMergeRequest,
    LeadRead,
    OutboxEventRead,
    PipelineReport,
    ScoreExplanation,
    ScoreFactRead,
    SocialPostCreate,
    SocialPostRead,
    StageRead,
    StageReorderRequest,
    TranscriptCreate,
    TranscriptRead,
)
from app.modules.crm.scoring import rescore_lead
from app.modules.crm.service import (
    approve_assessment,
    approve_social_post,
    assess_call,
    assign_inbox_conversation,
    capture_consent,
    convert_lead,
    create_engagement,
    create_social_post,
    current_consent,
    dispatch_outbox,
    get_scoped,
    lead_score_explanation,
    merge_leads,
    pipeline_report,
    publish_social_post,
    require_tenant,
    transition_deal,
)
from app.modules.identity.models import User
from app.modules.integrations.service import send_message

router = APIRouter()


@router.post("/leads/{item_id}/rescore", response_model=ScoreFactRead, tags=["CRM · Scoring"])
async def rescore(
    item_id: str,
    user: User = Depends(require_permissions("crm.lead.rescore")),
    db: AsyncSession = Depends(get_db),
):
    lead = await get_scoped(db, Lead, UUID(item_id), user)
    fact = await rescore_lead(db, lead, user=user)
    return fact


@router.get("/leads/{item_id}/score-explanation", response_model=ScoreExplanation, tags=["CRM · Scoring"])
async def score_explanation(
    item_id: str,
    user: User = Depends(require_permissions("crm.score.read")),
    db: AsyncSession = Depends(get_db),
):
    return await lead_score_explanation(db, user, UUID(item_id))


@router.get("/leads/duplicates", response_model=Page[LeadRead], tags=["CRM · Leads"])
async def duplicate_leads(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permissions("crm.lead.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = tenant_scoped(select(Lead), Lead, user).where(
        Lead.dedupe_key.is_not(None),
        Lead.is_active.is_(True),
    )
    keys = select(Lead.dedupe_key).where(
        Lead.tenant_id == require_tenant(user),
        Lead.dedupe_key.is_not(None),
    ).group_by(Lead.dedupe_key).having(func.count(Lead.id) > 1)
    stmt = stmt.where(Lead.dedupe_key.in_(keys))
    total = int((await db.scalar(select(func.count()).select_from(stmt.subquery()))) or 0)
    rows = list((await db.scalars(stmt.order_by(Lead.created_at.desc()).offset((page - 1) * size).limit(size))).all())
    return {"items": rows, "total": total, "page": page, "size": size, "pages": max(1, (total + size - 1) // size)}


@router.post("/leads/{item_id}/merge", response_model=LeadRead, tags=["CRM · Leads"])
async def merge(
    item_id: str,
    payload: LeadMergeRequest,
    user: User = Depends(require_permissions("crm.lead.merge")),
    db: AsyncSession = Depends(get_db),
):
    return await merge_leads(db, user, UUID(item_id), payload.duplicate_id)


@router.post("/leads/{item_id}/convert", response_model=LeadConvertResult, tags=["CRM · Leads"])
async def convert(
    item_id: str,
    payload: LeadConvertRequest,
    user: User = Depends(require_permissions("crm.lead.convert")),
    db: AsyncSession = Depends(get_db),
):
    return await convert_lead(db, user, UUID(item_id), payload)


@router.post("/stages/reorder", response_model=list[StageRead], tags=["CRM · Pipeline"])
async def reorder_stages(
    payload: StageReorderRequest,
    user: User = Depends(require_permissions("crm.pipeline.configure")),
    db: AsyncSession = Depends(get_db),
):
    stages = []
    for sequence, stage_id in enumerate(payload.stage_ids):
        stage = await get_scoped(db, Stage, stage_id, user)
        stage.sequence = sequence
        stages.append(stage)
    await db.commit()
    for stage in stages:
        await db.refresh(stage)
    return stages


@router.post("/deals/{item_id}/advance", response_model=DealRead, tags=["CRM · Deals"])
async def advance(
    item_id: str,
    payload: DealStageRequest,
    user: User = Depends(require_permissions("crm.deal.advance")),
    db: AsyncSession = Depends(get_db),
):
    return await transition_deal(db, user, UUID(item_id), "advance", payload)


@router.post("/deals/{item_id}/win", response_model=DealRead, tags=["CRM · Deals"])
async def win(
    item_id: str,
    payload: DealStageRequest,
    user: User = Depends(require_permissions("crm.deal.win")),
    db: AsyncSession = Depends(get_db),
):
    return await transition_deal(db, user, UUID(item_id), "win", payload)


@router.post("/deals/{item_id}/lose", response_model=DealRead, tags=["CRM · Deals"])
async def lose(
    item_id: str,
    payload: DealStageRequest,
    user: User = Depends(require_permissions("crm.deal.lose")),
    db: AsyncSession = Depends(get_db),
):
    return await transition_deal(db, user, UUID(item_id), "lose", payload)


@router.post("/consent", response_model=ConsentRead, status_code=201, tags=["CRM · Consent"])
async def capture(
    payload: ConsentCaptureRequest,
    user: User = Depends(require_permissions("crm.consent.capture")),
    db: AsyncSession = Depends(get_db),
):
    record = await capture_consent(
        db,
        require_tenant(user),
        subject_type=payload.subject_type,
        subject_id=payload.subject_id,
        channel=payload.channel,
        status=payload.status,
        source=payload.source,
        policy_version=payload.policy_version,
        proof_ref=payload.proof_ref,
        captured_at=payload.captured_at,
        actor_id=user.id,
    )
    await db.commit()
    await db.refresh(record)
    return record


@router.get("/consent/{subject_type}/{subject_id}", response_model=ConsentStateRead, tags=["CRM · Consent"])
async def consent_state(
    subject_type: str,
    subject_id: UUID,
    channel: str = Query("whatsapp"),
    user: User = Depends(require_permissions("crm.consent.read")),
    db: AsyncSession = Depends(get_db),
):
    record = await current_consent(db, require_tenant(user), subject_type, subject_id, channel)
    return {
        "status": record.status if record else "unknown",
        "channel": channel,
        "record": record,
    }


@router.post("/consent/{item_id}/revoke", response_model=ConsentRead, tags=["CRM · Consent"])
async def revoke(
    item_id: str,
    user: User = Depends(require_permissions("crm.consent.revoke")),
    db: AsyncSession = Depends(get_db),
):
    original = await get_scoped(db, ConsentRecord, UUID(item_id), user)
    record = await capture_consent(
        db,
        require_tenant(user),
        subject_type=original.subject_type,
        subject_id=original.subject_id,
        channel=original.channel,
        status="revoked",
        source="consent.revoke",
        policy_version=original.policy_version,
        actor_id=user.id,
    )
    original.revoked_at = record.captured_at
    await db.commit()
    await db.refresh(record)
    return record


@router.post("/engagements", response_model=EngagementRead, status_code=201, tags=["CRM · Engagements"])
async def create_engagement_endpoint(
    payload: EngagementCreate,
    user: User = Depends(require_permissions("crm.engagement.create")),
    db: AsyncSession = Depends(get_db),
):
    return await create_engagement(db, user, payload)


@router.get("/reports/pipeline", response_model=PipelineReport, tags=["CRM · Reports"])
async def pipeline(
    user: User = Depends(require_permissions("crm.report.read")),
    db: AsyncSession = Depends(get_db),
):
    return await pipeline_report(db, user)


@router.post("/calls/{item_id}/transcript", response_model=TranscriptRead, status_code=201, tags=["CRM · Calls"])
async def add_transcript(
    item_id: str,
    payload: TranscriptCreate,
    user: User = Depends(require_permissions("crm.call.update")),
    db: AsyncSession = Depends(get_db),
):
    call = await get_scoped(db, Call, UUID(item_id), user)
    segment = CallTranscript(
        tenant_id=require_tenant(user),
        created_by_id=user.id,
        call_id=call.id,
        sequence=payload.sequence,
        speaker=payload.speaker,
        text=payload.text,
        started_at=payload.started_at,
        confidence=payload.confidence,
    )
    db.add(segment)
    await db.commit()
    await db.refresh(segment)
    return segment


@router.post("/calls/{item_id}/assess", response_model=CallAssessmentRead, status_code=201, tags=["CRM · Calls"])
async def assess(
    item_id: str,
    user: User = Depends(require_permissions("crm.call.assess")),
    db: AsyncSession = Depends(get_db),
):
    return await assess_call(db, user, UUID(item_id))


@router.get("/calls/{item_id}/assessment", response_model=CallAssessmentRead, tags=["CRM · Calls"])
async def latest_assessment(
    item_id: str,
    user: User = Depends(require_permissions("crm.call.read")),
    db: AsyncSession = Depends(get_db),
):
    call = await get_scoped(db, Call, UUID(item_id), user)
    assessment = await db.scalar(
        tenant_scoped(select(CallAssessment), CallAssessment, user)
        .where(CallAssessment.call_id == call.id)
        .order_by(CallAssessment.created_at.desc())
        .limit(1)
    )
    if assessment is None:
        raise NotFoundError("Call assessment not found")
    return assessment


@router.post(
    "/calls/{item_id}/assessment/{assessment_id}/approve",
    response_model=CallAssessmentRead,
    tags=["CRM · Calls"],
)
async def approve(
    item_id: str,
    assessment_id: str,
    payload: AssessmentApproveRequest,
    user: User = Depends(require_permissions("crm.call.approve")),
    db: AsyncSession = Depends(get_db),
):
    await get_scoped(db, Call, UUID(item_id), user)
    return await approve_assessment(db, user, UUID(assessment_id), payload.status)


@router.post("/inbox/conversations/assign", response_model=InboxAssignmentRead, tags=["CRM · Inbox"])
async def assign(
    payload: InboxAssignRequest,
    conversation_key: str = Query(...),
    channel: str = Query("whatsapp"),
    user: User = Depends(require_permissions("crm.inbox.assign")),
    db: AsyncSession = Depends(get_db),
):
    return await assign_inbox_conversation(
        db,
        tenant_id=require_tenant(user),
        actor_id=user.id,
        conversation_key=conversation_key,
        channel=channel,
        assignee_id=payload.assignee_id,
        status=payload.status,
        sla_minutes=payload.sla_minutes,
    )


@router.post("/inbox/conversations/reply", tags=["CRM · Inbox"])
async def reply(
    payload: InboxReplyRequest,
    user: User = Depends(require_permissions("crm.inbox.reply")),
    db: AsyncSession = Depends(get_db),
):
    message = await send_message(
        db,
        tenant_id=require_tenant(user),
        channel=payload.channel,
        to=payload.to,
        body=payload.body,
        template=payload.template,
        module="crm",
        payload={"source": "inbox"},
    )
    return {"message_id": str(message.id), "status": message.status}


@router.post("/social/posts", response_model=SocialPostRead, status_code=201, tags=["CRM · Social"])
async def create_post(
    payload: SocialPostCreate,
    user: User = Depends(require_permissions("crm.socialpost.create")),
    db: AsyncSession = Depends(get_db),
):
    return await create_social_post(db, user, payload)


@router.post("/social/posts/{item_id}/approve", response_model=SocialPostRead, tags=["CRM · Social"])
async def approve_post(
    item_id: str,
    user: User = Depends(require_permissions("crm.socialpost.approve")),
    db: AsyncSession = Depends(get_db),
):
    return await approve_social_post(db, user, UUID(item_id))


@router.post("/social/posts/{item_id}/publish", response_model=SocialPostRead, tags=["CRM · Social"])
async def publish_post(
    item_id: str,
    user: User = Depends(require_permissions("crm.socialpost.publish")),
    db: AsyncSession = Depends(get_db),
):
    return await publish_social_post(db, user, UUID(item_id))


@router.post("/outbox/dispatch", tags=["CRM · Outbox"])
async def dispatch(
    user: User = Depends(require_permissions("crm.outbox.dispatch")),
    db: AsyncSession = Depends(get_db),
):
    return {"dispatched": await dispatch_outbox(db, user)}


@router.get("/outbox", response_model=Page[OutboxEventRead], tags=["CRM · Outbox"])
async def list_outbox(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: User = Depends(require_permissions("crm.outbox.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = tenant_scoped(select(OutboxEvent), OutboxEvent, user)
    total = int((await db.scalar(select(func.count()).select_from(stmt.subquery()))) or 0)
    rows = list((await db.scalars(stmt.order_by(OutboxEvent.created_at.desc()).offset((page - 1) * size).limit(size))).all())
    return {"items": rows, "total": total, "page": page, "size": size, "pages": max(1, (total + size - 1) // size)}
