"""crm unified engagement

Revision ID: 849004a6aca2
Revises: f4b8c2d9a601
Create Date: 2026-11-21 17:52:44.952842

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "849004a6aca2"
down_revision: str | None = "f4b8c2d9a601"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integration_webhook_events",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("external_event_id", sa.String(length=160), nullable=False),
        sa.Column("payload_hash", sa.String(length=64), nullable=False),
        sa.Column("signature_valid", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider",
            "event_type",
            "external_event_id",
            name="uq_integration_webhook_event_provider_type_external",
        ),
    )
    op.create_index(
        op.f("ix_integration_webhook_events_event_type"),
        "integration_webhook_events",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_webhook_events_external_event_id"),
        "integration_webhook_events",
        ["external_event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_webhook_events_processed_at"),
        "integration_webhook_events",
        ["processed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_webhook_events_provider"),
        "integration_webhook_events",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_webhook_events_status"),
        "integration_webhook_events",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_webhook_events_tenant_id"),
        "integration_webhook_events",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "crm_consent_records",
        sa.Column("subject_type", sa.String(length=40), nullable=False),
        sa.Column("subject_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("source", sa.String(length=120), nullable=False),
        sa.Column("policy_version", sa.String(length=40), nullable=False),
        sa.Column("proof_ref", sa.String(length=255), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crm_consent_records_channel"), "crm_consent_records", ["channel"], unique=False
    )
    op.create_index(
        op.f("ix_crm_consent_records_is_active"), "crm_consent_records", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_crm_consent_records_status"), "crm_consent_records", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_crm_consent_records_subject_id"),
        "crm_consent_records",
        ["subject_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_consent_records_subject_type"),
        "crm_consent_records",
        ["subject_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_consent_records_tenant_id"), "crm_consent_records", ["tenant_id"], unique=False
    )
    op.create_table(
        "crm_lead_sources",
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("utm_pattern", sa.String(length=255), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_crm_lead_sources_tenant_code"),
    )
    op.create_index(op.f("ix_crm_lead_sources_code"), "crm_lead_sources", ["code"], unique=False)
    op.create_index(
        op.f("ix_crm_lead_sources_is_active"), "crm_lead_sources", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_crm_lead_sources_tenant_id"), "crm_lead_sources", ["tenant_id"], unique=False
    )
    op.create_table(
        "crm_outbox_events",
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=60), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=120), nullable=True),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crm_outbox_events_entity_id"), "crm_outbox_events", ["entity_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_outbox_events_event_type"), "crm_outbox_events", ["event_type"], unique=False
    )
    op.create_index(
        op.f("ix_crm_outbox_events_is_active"), "crm_outbox_events", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_crm_outbox_events_status"), "crm_outbox_events", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_crm_outbox_events_tenant_id"), "crm_outbox_events", ["tenant_id"], unique=False
    )
    op.create_table(
        "crm_score_facts",
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("model_version", sa.String(length=60), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("grade", sa.String(length=2), nullable=False),
        sa.Column("trend", sa.String(length=20), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("source_event_id", sa.String(length=160), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["crm_leads.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "lead_id",
            "model_version",
            "source_event_id",
            name="uq_crm_score_facts_tenant_lead_model_event",
        ),
    )
    op.create_index(
        op.f("ix_crm_score_facts_is_active"), "crm_score_facts", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_crm_score_facts_lead_id"), "crm_score_facts", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_score_facts_model_version"), "crm_score_facts", ["model_version"], unique=False
    )
    op.create_index(
        op.f("ix_crm_score_facts_tenant_id"), "crm_score_facts", ["tenant_id"], unique=False
    )
    op.create_table(
        "crm_social_accounts",
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("external_account_id", sa.String(length=160), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("token_ref", sa.String(length=160), nullable=True),
        sa.Column("last_sync_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "channel",
            "external_account_id",
            name="uq_crm_social_accounts_tenant_channel_external",
        ),
    )
    op.create_index(
        op.f("ix_crm_social_accounts_channel"), "crm_social_accounts", ["channel"], unique=False
    )
    op.create_index(
        op.f("ix_crm_social_accounts_external_account_id"),
        "crm_social_accounts",
        ["external_account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_social_accounts_is_active"), "crm_social_accounts", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_crm_social_accounts_tenant_id"), "crm_social_accounts", ["tenant_id"], unique=False
    )
    op.create_table(
        "crm_stages",
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("code", sa.String(length=60), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("probability_default", sa.Integer(), nullable=False),
        sa.Column("is_won", sa.Boolean(), nullable=False),
        sa.Column("is_lost", sa.Boolean(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_crm_stages_tenant_code"),
    )
    op.create_index(op.f("ix_crm_stages_code"), "crm_stages", ["code"], unique=False)
    op.create_index(op.f("ix_crm_stages_is_active"), "crm_stages", ["is_active"], unique=False)
    op.create_index(op.f("ix_crm_stages_tenant_id"), "crm_stages", ["tenant_id"], unique=False)
    op.create_table(
        "integration_channel_bindings",
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("external_ref", sa.String(length=160), nullable=False),
        sa.Column("label", sa.String(length=160), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "external_ref", name="uq_integration_channel_binding_provider_ref"
        ),
    )
    op.create_index(
        op.f("ix_integration_channel_bindings_external_ref"),
        "integration_channel_bindings",
        ["external_ref"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_channel_bindings_is_active"),
        "integration_channel_bindings",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_channel_bindings_provider"),
        "integration_channel_bindings",
        ["provider"],
        unique=False,
    )
    op.create_index(
        op.f("ix_integration_channel_bindings_tenant_id"),
        "integration_channel_bindings",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "crm_social_posts",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("media_refs", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("external_post_id", sa.String(length=160), nullable=True),
        sa.Column("approved_by_id", sa.UUID(), nullable=True),
        sa.Column("campaign_id", sa.UUID(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["crm_social_accounts.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["approved_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["campaign_id"], ["marketing_campaigns.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crm_social_posts_account_id"), "crm_social_posts", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_social_posts_external_post_id"),
        "crm_social_posts",
        ["external_post_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_social_posts_is_active"), "crm_social_posts", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_crm_social_posts_status"), "crm_social_posts", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_crm_social_posts_tenant_id"), "crm_social_posts", ["tenant_id"], unique=False
    )
    op.create_table(
        "crm_calls",
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("deal_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(length=60), nullable=False),
        sa.Column("external_call_id", sa.String(length=160), nullable=True),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=True),
        sa.Column("recording_ref", sa.String(length=255), nullable=True),
        sa.Column("consent_record_id", sa.UUID(), nullable=True),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(
            ["consent_record_id"], ["crm_consent_records.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["contact_id"], ["crm_contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deal_id"], ["crm_deals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["crm_leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_crm_calls_contact_id"), "crm_calls", ["contact_id"], unique=False)
    op.create_index(op.f("ix_crm_calls_deal_id"), "crm_calls", ["deal_id"], unique=False)
    op.create_index(op.f("ix_crm_calls_direction"), "crm_calls", ["direction"], unique=False)
    op.create_index(
        op.f("ix_crm_calls_external_call_id"), "crm_calls", ["external_call_id"], unique=False
    )
    op.create_index(op.f("ix_crm_calls_is_active"), "crm_calls", ["is_active"], unique=False)
    op.create_index(op.f("ix_crm_calls_lead_id"), "crm_calls", ["lead_id"], unique=False)
    op.create_index(op.f("ix_crm_calls_status"), "crm_calls", ["status"], unique=False)
    op.create_index(op.f("ix_crm_calls_tenant_id"), "crm_calls", ["tenant_id"], unique=False)
    op.create_table(
        "crm_engagements",
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("deal_id", sa.UUID(), nullable=True),
        sa.Column("external_ref", sa.String(length=160), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column("source_event_id", sa.String(length=160), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["crm_contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["deal_id"], ["crm_deals.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["crm_leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crm_engagements_channel"), "crm_engagements", ["channel"], unique=False
    )
    op.create_index(
        op.f("ix_crm_engagements_contact_id"), "crm_engagements", ["contact_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_engagements_deal_id"), "crm_engagements", ["deal_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_engagements_direction"), "crm_engagements", ["direction"], unique=False
    )
    op.create_index(
        op.f("ix_crm_engagements_external_ref"), "crm_engagements", ["external_ref"], unique=False
    )
    op.create_index(
        op.f("ix_crm_engagements_is_active"), "crm_engagements", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_crm_engagements_lead_id"), "crm_engagements", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_engagements_occurred_at"), "crm_engagements", ["occurred_at"], unique=False
    )
    op.create_index(
        op.f("ix_crm_engagements_tenant_id"), "crm_engagements", ["tenant_id"], unique=False
    )
    op.create_table(
        "crm_inbox_assignments",
        sa.Column("conversation_key", sa.String(length=255), nullable=False),
        sa.Column("channel", sa.String(length=40), nullable=False),
        sa.Column("external_ref", sa.String(length=160), nullable=True),
        sa.Column("lead_id", sa.UUID(), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("assignee_id", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("sla_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["contact_id"], ["crm_contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lead_id"], ["crm_leads.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "conversation_key", name="uq_crm_inbox_tenant_conversation"
        ),
    )
    op.create_index(
        op.f("ix_crm_inbox_assignments_channel"), "crm_inbox_assignments", ["channel"], unique=False
    )
    op.create_index(
        op.f("ix_crm_inbox_assignments_contact_id"),
        "crm_inbox_assignments",
        ["contact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_inbox_assignments_conversation_key"),
        "crm_inbox_assignments",
        ["conversation_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_inbox_assignments_external_ref"),
        "crm_inbox_assignments",
        ["external_ref"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_inbox_assignments_is_active"),
        "crm_inbox_assignments",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_inbox_assignments_lead_id"), "crm_inbox_assignments", ["lead_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_inbox_assignments_status"), "crm_inbox_assignments", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_crm_inbox_assignments_tenant_id"),
        "crm_inbox_assignments",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "crm_social_messages",
        sa.Column("account_id", sa.UUID(), nullable=False),
        sa.Column("external_message_id", sa.String(length=160), nullable=False),
        sa.Column("direction", sa.String(length=20), nullable=False),
        sa.Column("author_external_id", sa.String(length=160), nullable=True),
        sa.Column("contact_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["account_id"], ["crm_social_accounts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["crm_contacts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "account_id",
            "external_message_id",
            name="uq_crm_social_messages_tenant_account_external",
        ),
    )
    op.create_index(
        op.f("ix_crm_social_messages_account_id"),
        "crm_social_messages",
        ["account_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_social_messages_author_external_id"),
        "crm_social_messages",
        ["author_external_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_social_messages_contact_id"),
        "crm_social_messages",
        ["contact_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_social_messages_direction"), "crm_social_messages", ["direction"], unique=False
    )
    op.create_index(
        op.f("ix_crm_social_messages_external_message_id"),
        "crm_social_messages",
        ["external_message_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_social_messages_is_active"), "crm_social_messages", ["is_active"], unique=False
    )
    op.create_index(
        op.f("ix_crm_social_messages_tenant_id"), "crm_social_messages", ["tenant_id"], unique=False
    )
    op.create_table(
        "crm_call_assessments",
        sa.Column("call_id", sa.UUID(), nullable=False),
        sa.Column("rubric_version", sa.String(length=60), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("next_best_action", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("reviewer_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["call_id"], ["crm_calls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crm_call_assessments_call_id"), "crm_call_assessments", ["call_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_call_assessments_is_active"),
        "crm_call_assessments",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_call_assessments_status"), "crm_call_assessments", ["status"], unique=False
    )
    op.create_index(
        op.f("ix_crm_call_assessments_tenant_id"),
        "crm_call_assessments",
        ["tenant_id"],
        unique=False,
    )
    op.create_table(
        "crm_call_transcripts",
        sa.Column("call_id", sa.UUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("speaker", sa.String(length=60), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence", sa.Numeric(precision=5, scale=4), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["call_id"], ["crm_calls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_crm_call_transcripts_call_id"), "crm_call_transcripts", ["call_id"], unique=False
    )
    op.create_index(
        op.f("ix_crm_call_transcripts_is_active"),
        "crm_call_transcripts",
        ["is_active"],
        unique=False,
    )
    op.create_index(
        op.f("ix_crm_call_transcripts_tenant_id"),
        "crm_call_transcripts",
        ["tenant_id"],
        unique=False,
    )
    op.add_column("crm_activities", sa.Column("outcome", sa.String(length=80), nullable=True))
    op.add_column("crm_activities", sa.Column("channel_message_id", sa.UUID(), nullable=True))
    op.add_column("crm_activities", sa.Column("call_id", sa.UUID(), nullable=True))
    op.add_column("crm_activities", sa.Column("duration_seconds", sa.Integer(), nullable=True))
    op.add_column(
        "crm_activities", sa.Column("reminder_sent_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_foreign_key(
        "crm_activities_channel_message_id_fkey",
        "crm_activities",
        "channel_messages",
        ["channel_message_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "crm_activities_call_id_fkey",
        "crm_activities",
        "crm_calls",
        ["call_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("crm_companies", sa.Column("parent_company_id", sa.UUID(), nullable=True))
    op.add_column("crm_companies", sa.Column("employee_count", sa.Integer(), nullable=True))
    op.add_column("crm_companies", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.add_column("crm_companies", sa.Column("linked_customer_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "crm_companies_parent_company_id_fkey",
        "crm_companies",
        "crm_companies",
        ["parent_company_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "crm_companies_owner_id_fkey",
        "crm_companies",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "crm_companies_linked_customer_id_fkey",
        "crm_companies",
        "customers",
        ["linked_customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "crm_contacts", sa.Column("consent_captured_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("crm_contacts", sa.Column("consent_source", sa.String(length=120), nullable=True))
    op.add_column("crm_contacts", sa.Column("wa_id", sa.String(length=80), nullable=True))
    op.add_column(
        "crm_contacts",
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )
    op.add_column("crm_contacts", sa.Column("linked_customer_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_crm_contacts_wa_id"), "crm_contacts", ["wa_id"], unique=False)
    op.create_foreign_key(
        "crm_contacts_linked_customer_id_fkey",
        "crm_contacts",
        "customers",
        ["linked_customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column("crm_deals", sa.Column("stage_id", sa.UUID(), nullable=True))
    op.add_column(
        "crm_deals",
        sa.Column(
            "weighted_amount",
            sa.Numeric(precision=14, scale=2),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column("crm_deals", sa.Column("next_step", sa.String(length=255), nullable=True))
    op.add_column("crm_deals", sa.Column("next_step_due", sa.Date(), nullable=True))
    op.add_column("crm_deals", sa.Column("lost_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("crm_deals", sa.Column("lost_reason", sa.Text(), nullable=True))
    op.add_column("crm_deals", sa.Column("won_event_id", sa.String(length=120), nullable=True))
    op.create_index(op.f("ix_crm_deals_won_event_id"), "crm_deals", ["won_event_id"], unique=False)
    op.create_foreign_key(
        "crm_deals_stage_id_fkey",
        "crm_deals",
        "crm_stages",
        ["stage_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "crm_leads", sa.Column("consent_captured_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("crm_leads", sa.Column("consent_source", sa.String(length=120), nullable=True))
    op.add_column(
        "crm_leads", sa.Column("score_model_version", sa.String(length=60), nullable=True)
    )
    op.add_column(
        "crm_leads", sa.Column("score_updated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("crm_leads", sa.Column("score_grade", sa.String(length=2), nullable=True))
    op.add_column("crm_leads", sa.Column("score_trend", sa.String(length=20), nullable=True))
    op.add_column(
        "crm_leads",
        sa.Column("score_features", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
    )
    op.add_column(
        "crm_leads",
        sa.Column("engagement_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
    )
    op.add_column(
        "crm_leads", sa.Column("last_activity_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("crm_leads", sa.Column("dedupe_key", sa.String(length=255), nullable=True))
    op.add_column("crm_leads", sa.Column("external_ref", sa.String(length=160), nullable=True))
    op.add_column("crm_leads", sa.Column("utm_source", sa.String(length=120), nullable=True))
    op.add_column("crm_leads", sa.Column("utm_medium", sa.String(length=120), nullable=True))
    op.add_column("crm_leads", sa.Column("utm_campaign", sa.String(length=160), nullable=True))
    op.add_column("crm_leads", sa.Column("converted_deal_id", sa.UUID(), nullable=True))
    op.add_column("crm_leads", sa.Column("lost_reason", sa.Text(), nullable=True))
    op.create_index(op.f("ix_crm_leads_dedupe_key"), "crm_leads", ["dedupe_key"], unique=False)
    op.create_index(op.f("ix_crm_leads_external_ref"), "crm_leads", ["external_ref"], unique=False)
    op.create_index(
        op.f("ix_crm_leads_last_activity_at"), "crm_leads", ["last_activity_at"], unique=False
    )
    op.create_foreign_key(
        "crm_leads_converted_deal_id_fkey",
        "crm_leads",
        "crm_deals",
        ["converted_deal_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("crm_leads_converted_deal_id_fkey", "crm_leads", type_="foreignkey")
    op.drop_index(op.f("ix_crm_leads_last_activity_at"), table_name="crm_leads")
    op.drop_index(op.f("ix_crm_leads_external_ref"), table_name="crm_leads")
    op.drop_index(op.f("ix_crm_leads_dedupe_key"), table_name="crm_leads")
    op.drop_column("crm_leads", "lost_reason")
    op.drop_column("crm_leads", "converted_deal_id")
    op.drop_column("crm_leads", "utm_campaign")
    op.drop_column("crm_leads", "utm_medium")
    op.drop_column("crm_leads", "utm_source")
    op.drop_column("crm_leads", "external_ref")
    op.drop_column("crm_leads", "dedupe_key")
    op.drop_column("crm_leads", "last_activity_at")
    op.drop_column("crm_leads", "engagement_count")
    op.drop_column("crm_leads", "score_features")
    op.drop_column("crm_leads", "score_trend")
    op.drop_column("crm_leads", "score_grade")
    op.drop_column("crm_leads", "score_updated_at")
    op.drop_column("crm_leads", "score_model_version")
    op.drop_column("crm_leads", "consent_source")
    op.drop_column("crm_leads", "consent_captured_at")
    op.drop_constraint("crm_deals_stage_id_fkey", "crm_deals", type_="foreignkey")
    op.drop_index(op.f("ix_crm_deals_won_event_id"), table_name="crm_deals")
    op.drop_column("crm_deals", "won_event_id")
    op.drop_column("crm_deals", "lost_reason")
    op.drop_column("crm_deals", "lost_at")
    op.drop_column("crm_deals", "next_step_due")
    op.drop_column("crm_deals", "next_step")
    op.drop_column("crm_deals", "weighted_amount")
    op.drop_column("crm_deals", "stage_id")
    op.drop_constraint("crm_contacts_linked_customer_id_fkey", "crm_contacts", type_="foreignkey")
    op.drop_index(op.f("ix_crm_contacts_wa_id"), table_name="crm_contacts")
    op.drop_column("crm_contacts", "linked_customer_id")
    op.drop_column("crm_contacts", "is_primary")
    op.drop_column("crm_contacts", "wa_id")
    op.drop_column("crm_contacts", "consent_source")
    op.drop_column("crm_contacts", "consent_captured_at")
    op.drop_constraint("crm_companies_linked_customer_id_fkey", "crm_companies", type_="foreignkey")
    op.drop_constraint("crm_companies_owner_id_fkey", "crm_companies", type_="foreignkey")
    op.drop_constraint("crm_companies_parent_company_id_fkey", "crm_companies", type_="foreignkey")
    op.drop_column("crm_companies", "linked_customer_id")
    op.drop_column("crm_companies", "owner_id")
    op.drop_column("crm_companies", "employee_count")
    op.drop_column("crm_companies", "parent_company_id")
    op.drop_constraint("crm_activities_call_id_fkey", "crm_activities", type_="foreignkey")
    op.drop_constraint(
        "crm_activities_channel_message_id_fkey", "crm_activities", type_="foreignkey"
    )
    op.drop_column("crm_activities", "reminder_sent_at")
    op.drop_column("crm_activities", "duration_seconds")
    op.drop_column("crm_activities", "call_id")
    op.drop_column("crm_activities", "channel_message_id")
    op.drop_column("crm_activities", "outcome")
    op.drop_index(op.f("ix_crm_call_transcripts_tenant_id"), table_name="crm_call_transcripts")
    op.drop_index(op.f("ix_crm_call_transcripts_is_active"), table_name="crm_call_transcripts")
    op.drop_index(op.f("ix_crm_call_transcripts_call_id"), table_name="crm_call_transcripts")
    op.drop_table("crm_call_transcripts")
    op.drop_index(op.f("ix_crm_call_assessments_tenant_id"), table_name="crm_call_assessments")
    op.drop_index(op.f("ix_crm_call_assessments_status"), table_name="crm_call_assessments")
    op.drop_index(op.f("ix_crm_call_assessments_is_active"), table_name="crm_call_assessments")
    op.drop_index(op.f("ix_crm_call_assessments_call_id"), table_name="crm_call_assessments")
    op.drop_table("crm_call_assessments")
    op.drop_index(op.f("ix_crm_social_messages_tenant_id"), table_name="crm_social_messages")
    op.drop_index(op.f("ix_crm_social_messages_is_active"), table_name="crm_social_messages")
    op.drop_index(
        op.f("ix_crm_social_messages_external_message_id"), table_name="crm_social_messages"
    )
    op.drop_index(op.f("ix_crm_social_messages_direction"), table_name="crm_social_messages")
    op.drop_index(op.f("ix_crm_social_messages_contact_id"), table_name="crm_social_messages")
    op.drop_index(
        op.f("ix_crm_social_messages_author_external_id"), table_name="crm_social_messages"
    )
    op.drop_index(op.f("ix_crm_social_messages_account_id"), table_name="crm_social_messages")
    op.drop_table("crm_social_messages")
    op.drop_index(op.f("ix_crm_inbox_assignments_tenant_id"), table_name="crm_inbox_assignments")
    op.drop_index(op.f("ix_crm_inbox_assignments_status"), table_name="crm_inbox_assignments")
    op.drop_index(op.f("ix_crm_inbox_assignments_lead_id"), table_name="crm_inbox_assignments")
    op.drop_index(op.f("ix_crm_inbox_assignments_is_active"), table_name="crm_inbox_assignments")
    op.drop_index(op.f("ix_crm_inbox_assignments_external_ref"), table_name="crm_inbox_assignments")
    op.drop_index(
        op.f("ix_crm_inbox_assignments_conversation_key"), table_name="crm_inbox_assignments"
    )
    op.drop_index(op.f("ix_crm_inbox_assignments_contact_id"), table_name="crm_inbox_assignments")
    op.drop_index(op.f("ix_crm_inbox_assignments_channel"), table_name="crm_inbox_assignments")
    op.drop_table("crm_inbox_assignments")
    op.drop_index(op.f("ix_crm_engagements_tenant_id"), table_name="crm_engagements")
    op.drop_index(op.f("ix_crm_engagements_occurred_at"), table_name="crm_engagements")
    op.drop_index(op.f("ix_crm_engagements_lead_id"), table_name="crm_engagements")
    op.drop_index(op.f("ix_crm_engagements_is_active"), table_name="crm_engagements")
    op.drop_index(op.f("ix_crm_engagements_external_ref"), table_name="crm_engagements")
    op.drop_index(op.f("ix_crm_engagements_direction"), table_name="crm_engagements")
    op.drop_index(op.f("ix_crm_engagements_deal_id"), table_name="crm_engagements")
    op.drop_index(op.f("ix_crm_engagements_contact_id"), table_name="crm_engagements")
    op.drop_index(op.f("ix_crm_engagements_channel"), table_name="crm_engagements")
    op.drop_table("crm_engagements")
    op.drop_index(op.f("ix_crm_calls_tenant_id"), table_name="crm_calls")
    op.drop_index(op.f("ix_crm_calls_status"), table_name="crm_calls")
    op.drop_index(op.f("ix_crm_calls_lead_id"), table_name="crm_calls")
    op.drop_index(op.f("ix_crm_calls_is_active"), table_name="crm_calls")
    op.drop_index(op.f("ix_crm_calls_external_call_id"), table_name="crm_calls")
    op.drop_index(op.f("ix_crm_calls_direction"), table_name="crm_calls")
    op.drop_index(op.f("ix_crm_calls_deal_id"), table_name="crm_calls")
    op.drop_index(op.f("ix_crm_calls_contact_id"), table_name="crm_calls")
    op.drop_table("crm_calls")
    op.drop_index(op.f("ix_crm_social_posts_tenant_id"), table_name="crm_social_posts")
    op.drop_index(op.f("ix_crm_social_posts_status"), table_name="crm_social_posts")
    op.drop_index(op.f("ix_crm_social_posts_is_active"), table_name="crm_social_posts")
    op.drop_index(op.f("ix_crm_social_posts_external_post_id"), table_name="crm_social_posts")
    op.drop_index(op.f("ix_crm_social_posts_account_id"), table_name="crm_social_posts")
    op.drop_table("crm_social_posts")
    op.drop_index(
        op.f("ix_integration_channel_bindings_tenant_id"), table_name="integration_channel_bindings"
    )
    op.drop_index(
        op.f("ix_integration_channel_bindings_provider"), table_name="integration_channel_bindings"
    )
    op.drop_index(
        op.f("ix_integration_channel_bindings_is_active"), table_name="integration_channel_bindings"
    )
    op.drop_index(
        op.f("ix_integration_channel_bindings_external_ref"),
        table_name="integration_channel_bindings",
    )
    op.drop_table("integration_channel_bindings")
    op.drop_index(op.f("ix_crm_stages_tenant_id"), table_name="crm_stages")
    op.drop_index(op.f("ix_crm_stages_is_active"), table_name="crm_stages")
    op.drop_index(op.f("ix_crm_stages_code"), table_name="crm_stages")
    op.drop_table("crm_stages")
    op.drop_index(op.f("ix_crm_social_accounts_tenant_id"), table_name="crm_social_accounts")
    op.drop_index(op.f("ix_crm_social_accounts_is_active"), table_name="crm_social_accounts")
    op.drop_index(
        op.f("ix_crm_social_accounts_external_account_id"), table_name="crm_social_accounts"
    )
    op.drop_index(op.f("ix_crm_social_accounts_channel"), table_name="crm_social_accounts")
    op.drop_table("crm_social_accounts")
    op.drop_index(op.f("ix_crm_score_facts_tenant_id"), table_name="crm_score_facts")
    op.drop_index(op.f("ix_crm_score_facts_model_version"), table_name="crm_score_facts")
    op.drop_index(op.f("ix_crm_score_facts_lead_id"), table_name="crm_score_facts")
    op.drop_index(op.f("ix_crm_score_facts_is_active"), table_name="crm_score_facts")
    op.drop_table("crm_score_facts")
    op.drop_index(op.f("ix_crm_outbox_events_tenant_id"), table_name="crm_outbox_events")
    op.drop_index(op.f("ix_crm_outbox_events_status"), table_name="crm_outbox_events")
    op.drop_index(op.f("ix_crm_outbox_events_is_active"), table_name="crm_outbox_events")
    op.drop_index(op.f("ix_crm_outbox_events_event_type"), table_name="crm_outbox_events")
    op.drop_index(op.f("ix_crm_outbox_events_entity_id"), table_name="crm_outbox_events")
    op.drop_table("crm_outbox_events")
    op.drop_index(op.f("ix_crm_lead_sources_tenant_id"), table_name="crm_lead_sources")
    op.drop_index(op.f("ix_crm_lead_sources_is_active"), table_name="crm_lead_sources")
    op.drop_index(op.f("ix_crm_lead_sources_code"), table_name="crm_lead_sources")
    op.drop_table("crm_lead_sources")
    op.drop_index(op.f("ix_crm_consent_records_tenant_id"), table_name="crm_consent_records")
    op.drop_index(op.f("ix_crm_consent_records_subject_type"), table_name="crm_consent_records")
    op.drop_index(op.f("ix_crm_consent_records_subject_id"), table_name="crm_consent_records")
    op.drop_index(op.f("ix_crm_consent_records_status"), table_name="crm_consent_records")
    op.drop_index(op.f("ix_crm_consent_records_is_active"), table_name="crm_consent_records")
    op.drop_index(op.f("ix_crm_consent_records_channel"), table_name="crm_consent_records")
    op.drop_table("crm_consent_records")
    op.drop_index(
        op.f("ix_integration_webhook_events_tenant_id"), table_name="integration_webhook_events"
    )
    op.drop_index(
        op.f("ix_integration_webhook_events_status"), table_name="integration_webhook_events"
    )
    op.drop_index(
        op.f("ix_integration_webhook_events_provider"), table_name="integration_webhook_events"
    )
    op.drop_index(
        op.f("ix_integration_webhook_events_processed_at"), table_name="integration_webhook_events"
    )
    op.drop_index(
        op.f("ix_integration_webhook_events_external_event_id"),
        table_name="integration_webhook_events",
    )
    op.drop_index(
        op.f("ix_integration_webhook_events_event_type"), table_name="integration_webhook_events"
    )
    op.drop_table("integration_webhook_events")
