from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import TenantBaseModel


class Stage(TenantBaseModel):
    __tablename__ = "crm_stages"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_crm_stages_tenant_code"),
    )

    name: Mapped[str] = mapped_column(String(80), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    probability_default: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    is_won: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_lost: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class LeadSource(TenantBaseModel):
    __tablename__ = "crm_lead_sources"
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", name="uq_crm_lead_sources_tenant_code"),
    )

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    utm_pattern: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)


class Company(TenantBaseModel):
    __tablename__ = "crm_companies"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    industry: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    gstin: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    address: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    state: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    country: Mapped[str] = mapped_column(String(120), default="India")
    annual_revenue: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    parent_company_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True
    )
    employee_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    linked_customer_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    contacts: Mapped[list["Contact"]] = relationship(back_populates="company", lazy="selectin")


class Contact(TenantBaseModel):
    __tablename__ = "crm_contacts"

    company_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True
    )
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), default="")
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consent_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    wa_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=text("false"), nullable=False
    )
    linked_customer_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    company: Mapped[Optional[Company]] = relationship(back_populates="contacts", lazy="selectin")


class Lead(TenantBaseModel):
    __tablename__ = "crm_leads"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    company_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    phone: Mapped[Optional[str]] = mapped_column(String(30), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(60), default="manual")
    status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    estimated_value: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    consent_captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    consent_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    score_model_version: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    score_updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    score_grade: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    score_trend: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    score_features: Mapped[dict[str, Any]] = mapped_column(
        JSON, default=dict, server_default=text("'{}'"), nullable=False
    )
    engagement_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    dedupe_key: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    utm_source: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_medium: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    utm_campaign: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    converted_deal_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True
    )
    lost_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    next_follow_up: Mapped[Optional[date]] = mapped_column(Date, nullable=True)


class Deal(TenantBaseModel):
    __tablename__ = "crm_deals"

    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    company_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_companies.id", ondelete="SET NULL"), nullable=True
    )
    contact_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True
    )
    lead_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_leads.id", ondelete="SET NULL"), nullable=True
    )
    stage: Mapped[str] = mapped_column(String(40), default="qualification", index=True)
    stage_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_stages.id", ondelete="SET NULL"), nullable=True
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    probability: Mapped[int] = mapped_column(Integer, default=20)
    weighted_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=0, server_default=text("0")
    )
    expected_close_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    next_step: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    next_step_due: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    won_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    lost_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    won_event_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)


class Activity(TenantBaseModel):
    __tablename__ = "crm_activities"

    activity_type: Mapped[str] = mapped_column(String(40), default="task")
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    related_entity: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    related_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed: Mapped[bool] = mapped_column(Boolean, default=False)
    outcome: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    channel_message_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("channel_messages.id", ondelete="SET NULL"), nullable=True
    )
    call_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_calls.id", ondelete="SET NULL"), nullable=True
    )
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    reminder_sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class ConsentRecord(TenantBaseModel):
    __tablename__ = "crm_consent_records"

    subject_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    subject_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(40), default="2026-11", nullable=False)
    proof_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ScoreFact(TenantBaseModel):
    __tablename__ = "crm_score_facts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "lead_id", "model_version", "source_event_id",
            name="uq_crm_score_facts_tenant_lead_model_event",
        ),
    )

    lead_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    model_version: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    grade: Mapped[str] = mapped_column(String(2), nullable=False)
    trend: Mapped[str] = mapped_column(String(20), default="new", nullable=False)
    features: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(160), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class Engagement(TenantBaseModel):
    __tablename__ = "crm_engagements"

    channel: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), default="inbound", nullable=False, index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    lead_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deal_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    external_ref: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    actor_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source_event_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class Call(TenantBaseModel):
    __tablename__ = "crm_calls"

    lead_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    deal_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_deals.id", ondelete="SET NULL"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(60), default="manual", nullable=False)
    external_call_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    direction: Mapped[str] = mapped_column(String(20), default="outbound", nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), default="scheduled", nullable=False, index=True)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    recording_ref: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    consent_record_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_consent_records.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CallTranscript(TenantBaseModel):
    __tablename__ = "crm_call_transcripts"

    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    speaker: Mapped[str] = mapped_column(String(60), default="unknown", nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 4), nullable=True)


class CallAssessment(TenantBaseModel):
    __tablename__ = "crm_call_assessments"

    call_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    rubric_version: Mapped[str] = mapped_column(String(60), default="rubric-v1", nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    signals: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    next_best_action: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    reviewer_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SocialAccount(TenantBaseModel):
    __tablename__ = "crm_social_accounts"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "channel", "external_account_id",
            name="uq_crm_social_accounts_tenant_channel_external",
        ),
    )

    channel: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    external_account_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    display_name: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    token_ref: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SocialMessage(TenantBaseModel):
    __tablename__ = "crm_social_messages"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "account_id", "external_message_id",
            name="uq_crm_social_messages_tenant_account_external",
        ),
    )

    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_social_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_message_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    direction: Mapped[str] = mapped_column(String(20), default="inbound", nullable=False, index=True)
    author_external_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    contact_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class SocialPost(TenantBaseModel):
    __tablename__ = "crm_social_posts"

    account_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_social_accounts.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    media_refs: Mapped[list[Any]] = mapped_column(JSON, default=list, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="draft", nullable=False, index=True)
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    external_post_id: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    campaign_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("marketing_campaigns.id", ondelete="SET NULL"), nullable=True
    )
    published_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


class OutboxEvent(TenantBaseModel):
    __tablename__ = "crm_outbox_events"

    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[Optional[UUID]] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    dispatched_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class InboxAssignment(TenantBaseModel):
    __tablename__ = "crm_inbox_assignments"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "conversation_key", name="uq_crm_inbox_tenant_conversation",
        ),
    )

    conversation_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    channel: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    external_ref: Mapped[Optional[str]] = mapped_column(String(160), nullable=True, index=True)
    lead_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_leads.id", ondelete="SET NULL"), nullable=True, index=True
    )
    contact_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("crm_contacts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    assignee_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(30), default="open", nullable=False, index=True)
    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
