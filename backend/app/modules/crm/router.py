from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.crud import build_crud_router
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
    ScoreFact,
    SocialAccount,
    SocialMessage,
    SocialPost,
    Stage,
)
from app.modules.crm.schemas import (
    ActivityCreate,
    ActivityRead,
    ActivityUpdate,
    CallAssessmentRead,
    CallCreate,
    CallRead,
    CallUpdate,
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    ConsentRead,
    ContactCreate,
    ContactRead,
    ContactUpdate,
    DealCreate,
    DealRead,
    DealUpdate,
    EngagementRead,
    InboxAssignmentRead,
    LeadCreate,
    LeadRead,
    LeadSourceCreate,
    LeadSourceRead,
    LeadSourceUpdate,
    LeadUpdate,
    ScoreFactRead,
    SocialAccountCreate,
    SocialAccountRead,
    SocialAccountUpdate,
    SocialMessageRead,
    SocialPostRead,
    StageCreate,
    StageRead,
    StageUpdate,
    TranscriptCreate,
    TranscriptRead,
)
from app.modules.crm.scoring import rescore_lead
from app.modules.crm.service import capture_consent, require_tenant
from app.modules.crm.workflow_router import router as workflow_router
from app.modules.identity.models import User

router = APIRouter(prefix="/crm")
router.include_router(workflow_router)


def _include(*args, **kwargs):
    child, _ = build_crud_router(module="crm", **kwargs)
    router.include_router(child)


async def _after_lead_create(
    db: AsyncSession, user: User, obj: Lead, data: dict[str, Any], request: Request
) -> None:
    if obj.whatsapp_opt_in:
        await capture_consent(
            db,
            require_tenant(user),
            subject_type="lead",
            subject_id=obj.id,
            channel="whatsapp",
            status="opted_in",
            source="crm.lead.create",
            actor_id=user.id,
        )
    await rescore_lead(db, obj, user=user, source_event_id=f"lead:{obj.id}:created")


async def _after_lead_update(
    db: AsyncSession, user: User, obj: Lead, data: dict[str, Any], request: Request
) -> None:
    interesting = {
        "name", "company_name", "email", "phone", "source", "status",
        "estimated_value", "whatsapp_opt_in",
    }
    if interesting.intersection(data):
        await rescore_lead(db, obj, user=user, source_event_id=f"lead:{obj.id}:updated")
    if data.get("whatsapp_opt_in") is not None:
        await capture_consent(
            db,
            require_tenant(user),
            subject_type="lead",
            subject_id=obj.id,
            channel="whatsapp",
            status="opted_in" if obj.whatsapp_opt_in else "opted_out",
            source="crm.lead.update",
            actor_id=user.id,
        )


async def _after_deal_create(
    db: AsyncSession, user: User, obj: Deal, data: dict[str, Any], request: Request
) -> None:
    obj.weighted_amount = (
        (Decimal(obj.amount or 0) * Decimal(obj.probability or 0) / Decimal(100))
        .quantize(Decimal("0.01"))
    )
    await db.commit()
    await db.refresh(obj)


async def _after_deal_update(
    db: AsyncSession, user: User, obj: Deal, data: dict[str, Any], request: Request
) -> None:
    await _after_deal_create(db, user, obj, data, request)


_include(
    model=Stage,
    read_schema=StageRead,
    create_schema=StageCreate,
    update_schema=StageUpdate,
    prefix="/stages",
    tags=["CRM · Pipeline"],
    permission_prefix="crm.stage",
    entity="Stage",
    search_fields=("name", "code"),
    filter_fields=("is_won", "is_lost"),
)

_include(
    model=LeadSource,
    read_schema=LeadSourceRead,
    create_schema=LeadSourceCreate,
    update_schema=LeadSourceUpdate,
    prefix="/lead-sources",
    tags=["CRM · Lead sources"],
    permission_prefix="crm.leadsource",
    entity="LeadSource",
    search_fields=("name", "code", "channel"),
    filter_fields=("channel",),
)

_include(
    model=Company,
    read_schema=CompanyRead,
    create_schema=CompanyCreate,
    update_schema=CompanyUpdate,
    prefix="/companies",
    tags=["CRM · Companies"],
    permission_prefix="crm.company",
    entity="Company",
    search_fields=("name", "email", "gstin", "city"),
    filter_fields=("industry", "state", "country"),
)

_include(
    model=Contact,
    read_schema=ContactRead,
    create_schema=ContactCreate,
    update_schema=ContactUpdate,
    prefix="/contacts",
    tags=["CRM · Contacts"],
    permission_prefix="crm.contact",
    entity="Contact",
    search_fields=("first_name", "last_name", "email", "phone"),
    filter_fields=("company_id",),
    load_options=(selectinload(Contact.company),),
)

_include(
    model=Lead,
    read_schema=LeadRead,
    create_schema=LeadCreate,
    update_schema=LeadUpdate,
    prefix="/leads",
    tags=["CRM · Leads"],
    permission_prefix="crm.lead",
    entity="Lead",
    search_fields=("name", "company_name", "email", "phone"),
    filter_fields=("source", "status", "owner_id"),
    after_create=_after_lead_create,
    after_update=_after_lead_update,
)

_include(
    model=Deal,
    read_schema=DealRead,
    create_schema=DealCreate,
    update_schema=DealUpdate,
    prefix="/deals",
    tags=["CRM · Deals"],
    permission_prefix="crm.deal",
    entity="Deal",
    search_fields=("name",),
    filter_fields=("stage", "owner_id", "company_id"),
    after_create=_after_deal_create,
    after_update=_after_deal_update,
)

_include(
    model=Activity,
    read_schema=ActivityRead,
    create_schema=ActivityCreate,
    update_schema=ActivityUpdate,
    prefix="/activities",
    tags=["CRM · Activities"],
    permission_prefix="crm.activity",
    entity="Activity",
    search_fields=("subject", "notes"),
    filter_fields=("related_entity", "owner_id"),
)

_include(
    model=ScoreFact,
    read_schema=ScoreFactRead,
    create_schema=ScoreFactRead,
    update_schema=ScoreFactRead,
    prefix="/score-facts",
    tags=["CRM · Scoring"],
    permission_prefix="crm.score",
    entity="ScoreFact",
    search_fields=(),
    filter_fields=("lead_id", "model_version"),
    create_enabled=False,
    update_enabled=False,
    delete_enabled=False,
)

_include(
    model=Engagement,
    read_schema=EngagementRead,
    create_schema=EngagementRead,
    update_schema=EngagementRead,
    prefix="/engagements",
    tags=["CRM · Engagements"],
    permission_prefix="crm.engagement",
    entity="Engagement",
    search_fields=("summary", "external_ref"),
    filter_fields=("channel", "lead_id", "contact_id", "deal_id"),
    create_enabled=False,
    update_enabled=False,
    delete_enabled=False,
)

_include(
    model=ConsentRecord,
    read_schema=ConsentRead,
    create_schema=ConsentRead,
    update_schema=ConsentRead,
    prefix="/consent-records",
    tags=["CRM · Consent"],
    permission_prefix="crm.consent",
    entity="ConsentRecord",
    search_fields=("source",),
    filter_fields=("subject_type", "subject_id", "channel", "status"),
    create_enabled=False,
    update_enabled=False,
    delete_enabled=False,
)

_include(
    model=Call,
    read_schema=CallRead,
    create_schema=CallCreate,
    update_schema=CallUpdate,
    prefix="/calls",
    tags=["CRM · Calls"],
    permission_prefix="crm.call",
    entity="Call",
    search_fields=("external_call_id", "notes"),
    filter_fields=("lead_id", "contact_id", "deal_id", "status", "direction"),
)

_include(
    model=CallTranscript,
    read_schema=TranscriptRead,
    create_schema=TranscriptCreate,
    update_schema=TranscriptCreate,
    prefix="/call-transcripts",
    tags=["CRM · Calls"],
    permission_prefix="crm.call",
    entity="CallTranscript",
    search_fields=("text", "speaker"),
    filter_fields=("call_id",),
    update_enabled=False,
)

_include(
    model=CallAssessment,
    read_schema=CallAssessmentRead,
    create_schema=CallAssessmentRead,
    update_schema=CallAssessmentRead,
    prefix="/call-assessments",
    tags=["CRM · Calls"],
    permission_prefix="crm.call",
    entity="CallAssessment",
    search_fields=("summary",),
    filter_fields=("call_id", "status"),
    create_enabled=False,
    update_enabled=False,
    delete_enabled=False,
)

_include(
    model=SocialAccount,
    read_schema=SocialAccountRead,
    create_schema=SocialAccountCreate,
    update_schema=SocialAccountUpdate,
    prefix="/social/accounts",
    tags=["CRM · Social"],
    permission_prefix="crm.socialaccount",
    entity="SocialAccount",
    search_fields=("display_name", "external_account_id"),
    filter_fields=("channel",),
)

_include(
    model=SocialMessage,
    read_schema=SocialMessageRead,
    create_schema=SocialMessageRead,
    update_schema=SocialMessageRead,
    prefix="/social/messages",
    tags=["CRM · Social"],
    permission_prefix="crm.socialmessage",
    entity="SocialMessage",
    search_fields=("body", "author_external_id"),
    filter_fields=("account_id", "direction", "contact_id"),
    create_enabled=False,
    update_enabled=False,
    delete_enabled=False,
)

_include(
    model=SocialPost,
    read_schema=SocialPostRead,
    create_schema=SocialPostRead,
    update_schema=SocialPostRead,
    prefix="/social/posts",
    tags=["CRM · Social"],
    permission_prefix="crm.socialpost",
    entity="SocialPost",
    search_fields=("body",),
    filter_fields=("account_id", "status", "campaign_id"),
    create_enabled=False,
    update_enabled=False,
    delete_enabled=False,
)

_include(
    model=InboxAssignment,
    read_schema=InboxAssignmentRead,
    create_schema=InboxAssignmentRead,
    update_schema=InboxAssignmentRead,
    prefix="/inbox/conversations",
    tags=["CRM · Inbox"],
    permission_prefix="crm.inbox",
    entity="InboxAssignment",
    search_fields=("conversation_key", "external_ref"),
    filter_fields=("channel", "status", "assignee_id", "lead_id"),
    create_enabled=False,
    update_enabled=False,
    delete_enabled=False,
)
