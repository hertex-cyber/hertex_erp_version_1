from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class CompanyBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    industry: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "India"
    annual_revenue: Decimal = Decimal("0")
    notes: Optional[str] = None


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(ORMModel):
    name: Optional[str] = None
    industry: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    annual_revenue: Optional[Decimal] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CompanyRead(ORMModel):
    id: UUID
    name: str
    industry: Optional[str] = None
    website: Optional[str] = None
    gstin: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    country: str
    annual_revenue: Decimal
    is_active: bool
    created_at: datetime


class ContactBase(ORMModel):
    company_id: Optional[UUID] = None
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = ""
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    whatsapp_opt_in: bool = False
    notes: Optional[str] = None


class ContactCreate(ContactBase):
    pass


class ContactUpdate(ORMModel):
    company_id: Optional[UUID] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    whatsapp_opt_in: Optional[bool] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class ContactRead(ORMModel):
    id: UUID
    company_id: Optional[UUID] = None
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    title: Optional[str] = None
    whatsapp_opt_in: bool
    is_active: bool
    created_at: datetime
    company: Optional[CompanyRead] = None


class LeadBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: str = "manual"
    status: str = "new"
    estimated_value: Decimal = Decimal("0")
    external_ref: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    owner_id: Optional[UUID] = None
    whatsapp_opt_in: bool = False
    notes: Optional[str] = None
    next_follow_up: Optional[date] = None


class LeadCreate(LeadBase):
    pass


class LeadUpdate(ORMModel):
    name: Optional[str] = None
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: Optional[str] = None
    status: Optional[str] = None
    estimated_value: Optional[Decimal] = None
    external_ref: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    owner_id: Optional[UUID] = None
    whatsapp_opt_in: Optional[bool] = None
    notes: Optional[str] = None
    next_follow_up: Optional[date] = None
    is_active: Optional[bool] = None


class LeadRead(ORMModel):
    id: UUID
    name: str
    company_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    source: str
    status: str
    score: int
    score_model_version: Optional[str] = None
    score_updated_at: Optional[datetime] = None
    score_grade: Optional[str] = None
    score_trend: Optional[str] = None
    score_features: dict[str, Any] = Field(default_factory=dict)
    engagement_count: int
    last_activity_at: Optional[datetime] = None
    dedupe_key: Optional[str] = None
    external_ref: Optional[str] = None
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    converted_deal_id: Optional[UUID] = None
    estimated_value: Decimal
    owner_id: Optional[UUID] = None
    whatsapp_opt_in: bool
    consent_captured_at: Optional[datetime] = None
    consent_source: Optional[str] = None
    next_follow_up: Optional[date] = None
    is_active: bool
    created_at: datetime


class DealBase(ORMModel):
    name: str = Field(min_length=1, max_length=200)
    company_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    stage: str = "qualification"
    stage_id: Optional[UUID] = None
    amount: Decimal = Decimal("0")
    probability: int = 20
    expected_close_date: Optional[date] = None
    owner_id: Optional[UUID] = None
    notes: Optional[str] = None


class DealCreate(DealBase):
    pass


class DealUpdate(ORMModel):
    name: Optional[str] = None
    company_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    stage: Optional[str] = None
    stage_id: Optional[UUID] = None
    amount: Optional[Decimal] = None
    probability: Optional[int] = None
    expected_close_date: Optional[date] = None
    owner_id: Optional[UUID] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class DealRead(ORMModel):
    id: UUID
    name: str
    company_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    lead_id: Optional[UUID] = None
    stage: str
    stage_id: Optional[UUID] = None
    amount: Decimal
    probability: int
    weighted_amount: Decimal
    expected_close_date: Optional[date] = None
    next_step: Optional[str] = None
    next_step_due: Optional[date] = None
    owner_id: Optional[UUID] = None
    won_at: Optional[datetime] = None
    lost_at: Optional[datetime] = None
    lost_reason: Optional[str] = None
    is_active: bool
    created_at: datetime


class ActivityBase(ORMModel):
    activity_type: str = "task"
    subject: str = Field(min_length=1, max_length=255)
    notes: Optional[str] = None
    related_entity: Optional[str] = None
    related_id: Optional[UUID] = None
    due_at: Optional[datetime] = None
    completed: bool = False
    owner_id: Optional[UUID] = None


class ActivityCreate(ActivityBase):
    pass


class ActivityUpdate(ORMModel):
    activity_type: Optional[str] = None
    subject: Optional[str] = None
    notes: Optional[str] = None
    related_entity: Optional[str] = None
    related_id: Optional[UUID] = None
    due_at: Optional[datetime] = None
    completed: Optional[bool] = None
    owner_id: Optional[UUID] = None
    is_active: Optional[bool] = None


class ActivityRead(ORMModel):
    id: UUID
    activity_type: str
    subject: str
    notes: Optional[str] = None
    related_entity: Optional[str] = None
    related_id: Optional[UUID] = None
    due_at: Optional[datetime] = None
    completed: bool
    owner_id: Optional[UUID] = None
    created_at: datetime


class StageBase(ORMModel):
    name: str = Field(min_length=1, max_length=80)
    code: str = Field(min_length=1, max_length=60)
    sequence: int = Field(ge=0)
    probability_default: int = Field(ge=0, le=100, default=20)
    is_won: bool = False
    is_lost: bool = False


class StageCreate(StageBase):
    pass


class StageUpdate(ORMModel):
    name: Optional[str] = None
    code: Optional[str] = None
    sequence: Optional[int] = Field(default=None, ge=0)
    probability_default: Optional[int] = Field(default=None, ge=0, le=100)
    is_won: Optional[bool] = None
    is_lost: Optional[bool] = None
    is_active: Optional[bool] = None


class StageRead(StageBase):
    id: UUID
    is_active: bool
    created_at: datetime


class StageReorderRequest(ORMModel):
    stage_ids: list[UUID] = Field(min_length=1)


class LeadSourceBase(ORMModel):
    name: str = Field(min_length=1, max_length=120)
    code: str = Field(min_length=1, max_length=60)
    channel: str = "manual"
    utm_pattern: Optional[str] = None


class LeadSourceCreate(LeadSourceBase):
    pass


class LeadSourceUpdate(ORMModel):
    name: Optional[str] = None
    code: Optional[str] = None
    channel: Optional[str] = None
    utm_pattern: Optional[str] = None
    is_active: Optional[bool] = None


class LeadSourceRead(LeadSourceBase):
    id: UUID
    is_active: bool
    created_at: datetime


class ConsentCaptureRequest(ORMModel):
    subject_type: str = Field(min_length=1, max_length=40)
    subject_id: UUID
    channel: str = Field(min_length=1, max_length=40)
    status: str = Field(pattern="^(opted_in|opted_out|revoked|unknown)$")
    source: str = Field(min_length=1, max_length=120)
    policy_version: str = "2026-11"
    proof_ref: Optional[str] = None
    captured_at: Optional[datetime] = None


class ConsentRead(ORMModel):
    id: UUID
    subject_type: str
    subject_id: UUID
    channel: str
    status: str
    source: str
    policy_version: str
    proof_ref: Optional[str] = None
    captured_at: datetime
    revoked_at: Optional[datetime] = None
    created_at: datetime


class ConsentStateRead(ORMModel):
    status: str
    channel: str
    record: Optional[ConsentRead] = None


class ScoreFactRead(ORMModel):
    id: UUID
    lead_id: UUID
    model_version: str
    score: int
    grade: str
    trend: str
    features: dict[str, Any]
    source_event_id: str
    computed_at: datetime


class ScoreExplanation(ORMModel):
    lead_id: UUID
    score: int
    grade: Optional[str] = None
    trend: Optional[str] = None
    model_version: Optional[str] = None
    top_features: list[dict[str, Any]] = Field(default_factory=list)
    facts: list[ScoreFactRead] = Field(default_factory=list)


class EngagementCreate(ORMModel):
    channel: str = Field(min_length=1, max_length=40)
    direction: str = "inbound"
    occurred_at: Optional[datetime] = None
    lead_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    external_ref: Optional[str] = None
    summary: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class EngagementRead(ORMModel):
    id: UUID
    channel: str
    direction: str
    occurred_at: datetime
    lead_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    external_ref: Optional[str] = None
    summary: Optional[str] = None
    payload: dict[str, Any]
    created_at: datetime


class LeadConvertRequest(ORMModel):
    deal_name: Optional[str] = None
    stage: Optional[str] = "qualification"
    stage_id: Optional[UUID] = None
    amount: Optional[Decimal] = None
    expected_close_date: Optional[date] = None
    create_contact: bool = True


class LeadConvertResult(ORMModel):
    lead_id: UUID
    deal_id: UUID
    company_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    events: list[str]


class DealStageRequest(ORMModel):
    stage: Optional[str] = None
    stage_id: Optional[UUID] = None
    reason: Optional[str] = None
    next_step: Optional[str] = None
    next_step_due: Optional[date] = None


class LeadMergeRequest(ORMModel):
    duplicate_id: UUID


class CallBase(ORMModel):
    lead_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    deal_id: Optional[UUID] = None
    provider: str = "manual"
    external_call_id: Optional[str] = None
    direction: str = "outbound"
    status: str = "scheduled"
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    recording_ref: Optional[str] = None
    consent_record_id: Optional[UUID] = None
    owner_id: Optional[UUID] = None
    notes: Optional[str] = None


class CallCreate(CallBase):
    pass


class CallUpdate(ORMModel):
    status: Optional[str] = None
    ended_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    recording_ref: Optional[str] = None
    notes: Optional[str] = None
    is_active: Optional[bool] = None


class CallRead(CallBase):
    id: UUID
    is_active: bool
    created_at: datetime


class TranscriptCreate(ORMModel):
    sequence: int = Field(ge=0, default=0)
    speaker: str = "unknown"
    text: str = Field(min_length=1)
    started_at: Optional[datetime] = None
    confidence: Optional[Decimal] = None


class TranscriptRead(ORMModel):
    id: UUID
    call_id: UUID
    sequence: int
    speaker: str
    text: str
    started_at: Optional[datetime] = None
    confidence: Optional[Decimal] = None
    created_at: datetime


class CallAssessmentRead(ORMModel):
    id: UUID
    call_id: UUID
    rubric_version: str
    score: int
    signals: dict[str, Any]
    summary: str
    next_best_action: str
    status: str
    reviewer_id: Optional[UUID] = None
    reviewed_at: Optional[datetime] = None
    created_at: datetime


class AssessmentApproveRequest(ORMModel):
    status: str = Field(pattern="^(approved|rejected)$")


class SocialAccountBase(ORMModel):
    channel: str = Field(min_length=1, max_length=40)
    external_account_id: str = Field(min_length=1, max_length=160)
    display_name: Optional[str] = None
    token_ref: Optional[str] = None


class SocialAccountCreate(SocialAccountBase):
    pass


class SocialAccountUpdate(ORMModel):
    display_name: Optional[str] = None
    token_ref: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    is_active: Optional[bool] = None


class SocialAccountRead(SocialAccountBase):
    id: UUID
    last_sync_at: Optional[datetime] = None
    is_active: bool
    created_at: datetime


class SocialMessageRead(ORMModel):
    id: UUID
    account_id: UUID
    external_message_id: str
    direction: str
    author_external_id: Optional[str] = None
    contact_id: Optional[UUID] = None
    body: Optional[str] = None
    posted_at: datetime
    payload: dict[str, Any]
    created_at: datetime


class SocialPostBase(ORMModel):
    account_id: UUID
    body: str = Field(min_length=1)
    media_refs: list[str] = Field(default_factory=list)
    scheduled_at: Optional[datetime] = None
    campaign_id: Optional[UUID] = None


class SocialPostCreate(SocialPostBase):
    pass


class SocialPostUpdate(ORMModel):
    body: Optional[str] = None
    media_refs: Optional[list[str]] = None
    scheduled_at: Optional[datetime] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class SocialPostRead(SocialPostBase):
    id: UUID
    status: str
    external_post_id: Optional[str] = None
    approved_by_id: Optional[UUID] = None
    published_at: Optional[datetime] = None
    metrics: dict[str, Any]
    is_active: bool
    created_at: datetime


class InboxAssignmentRead(ORMModel):
    id: UUID
    conversation_key: str
    channel: str
    external_ref: Optional[str] = None
    lead_id: Optional[UUID] = None
    contact_id: Optional[UUID] = None
    assignee_id: Optional[UUID] = None
    status: str
    sla_due_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime


class InboxAssignRequest(ORMModel):
    assignee_id: Optional[UUID] = None
    status: str = "open"
    sla_minutes: int = Field(default=60, ge=1, le=10080)


class InboxReplyRequest(ORMModel):
    body: str = Field(min_length=1)
    channel: str = "whatsapp"
    to: str = Field(min_length=1)
    template: Optional[str] = None


class PipelineReport(ORMModel):
    total: int
    weighted_amount: Decimal
    stages: list[dict[str, Any]]
    owners: list[dict[str, Any]]


class OutboxEventRead(ORMModel):
    id: UUID
    event_type: str
    entity_type: str
    entity_id: Optional[UUID] = None
    payload: dict[str, Any]
    status: str
    attempts: int
    correlation_id: Optional[str] = None
    dispatched_at: Optional[datetime] = None
    created_at: datetime
