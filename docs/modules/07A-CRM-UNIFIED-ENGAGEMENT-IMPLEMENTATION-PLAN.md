# 07A — CRM Unified Engagement: Implementation Plan

**Module owner:** CRM (consumes Integrations, Settings, Sales, AI) · **Status:** proposed · **Date:** 2026-11-21
**Scope:** one engagement record per person, explainable lead scoring, consented conversational channels, and a path from inbound message to scored lead to won deal.
**Normative base:** `docs/modules/00-MASTER-ARCHITECTURE.md` (invariants I1–I6, decisions D2/D3/D4, AI tiers A1–A5); extends `docs/modules/07-CRM.md` and `docs/modules/12-INTEGRATIONS.md` without contradicting them.
**Grounding:** current-state claims cite `backend/` code inspected on 2026-11-21. This is a planning document only.

---

## 1. Executive summary

CRM currently stores five lead/deal tables behind generic CRUD. `Lead.score` remains a writable, always-zero column; there is no pipeline configuration, no lead-to-deal conversion, no `deal.won` publication, no consent provenance, and no engagement timeline. Integrations has improved since the 2026-07 design docs: webhook signature verification, inbound dedupe by `external_id`, and a real WhatsApp Graph API adapter now exist, but webhook tenant resolution still picks the first tenant, the consent gate lets `unknown` recipients through, and Meta Lead Ads, social channels, and call transcripts are absent.

Target state is a unified engagement layer: every WhatsApp message, Meta Lead Ads lead, social DM/comment, call, and task lands in one tenant-scoped timeline attached to a contact/lead; a deterministic, versioned scorer turns those signals into a read-only 0–100 score with its top three contributing features; and a consent ledger gates every outbound action. Phase 1 implements the ingest → explain → convert spine now; social inbox/publishing and AI calling follow in later phases. All cross-module effects use events and the outbox (D2); CRM never writes Sales or Finance tables (I1/I3).

---

## 2. Competitor findings (official vendor docs patterns)

| Vendor | Pattern confirmed in official docs | Adopted here |
|---|---|---|
| [Salesforce Einstein Lead Scoring](https://help.salesforce.com/s/articleView?id=einstein_sales_lead_insights&type=5) | Score is read-only in a separate `ScoreIntelligence` object; the component shows which fields most influenced it; admins exclude fields; model reanalyzes about every 10 days; segmentation by criteria | Separate `crm_score_facts` table, read-only score, top-3 feature display, allow-listed feature set, scheduled retraining with version history |
| [Dynamics 365 predictive lead scoring](https://learn.microsoft.com/en-us/dynamics365/sales/configure-predictive-lead-scoring) | 0–100 score plus grade A–D and trend; top influencing factors in a widget; scores stored in `msdyn_predictivescore`, not the lead table; requires 40 qualified and 40 disqualified leads; real-time for new leads | 0–100 score, grade/trend, separate score facts, minimum-data gate before ML, event-triggered scoring for new leads |
| [HubSpot lead scoring](https://knowledge.hubspot.com/scoring/understand-the-lead-scoring-tool) | Engagement, fit, and combined scores; score groups with caps and thresholds; retroactive recompute when a score changes; score properties usable in segments/workflows | Fit and engagement feature groups with caps, retroactive rescore job, score exposed to reports via `crm.report.read` |
| [Zoho CRM scoring rules / Zia](https://help.zoho.com/portal/en/kb/crm/automate-business-processes/scoring-rules/articles/multiple-scoring-rule) | Manual and AI scoring across modules; touchpoint scoring includes WhatsApp incoming messages and call insights; scorecard explains what went right and wrong | Channel touchpoints feed `crm_engagements`; score explanation persisted in `score_features`; no cross-app sync gap |
| [Pipedrive Scores](https://support.pipedrive.com/en/article/scores) | Criteria bands (highly positive +25, slightly positive +10, negative -10); one active score per pipeline; non-editable field; hover explains factors; admins manage, regular users view | Rule fallback with fixed bands, one active model per pipeline, read-only score, `crm.pipeline.configure` restricted |
| [Freshsales Freddy](https://crmsupport.freshworks.com/support/solutions/articles/50000003001-how-to-use-contact-scoring-to-prioritize-contacts-) | Contact score 0–99, customer-fit stars, key scoring factors and next best action; out-of-office autoresponders excluded from scoring | Score plus grade plus `next_best_action`; bot/out-of-office replies filtered from engagement features |
| [Meta Lead Ads webhooks](https://developers.facebook.com/docs/graph-api/webhooks/getting-started/webhooks-for-leadgen/) | Page `leadgen` webhook carries `leadgen_id`, `form_id`, `ad_id`, `page_id`, `created_time`; field data fetched via Graph API using `leads_retrieval`; webhooks need `pages_manage_metadata` | Store `leadgen_id` as external key, hydrate fields via a stubbed Graph client in tests, map `ad_id`/`form_id` to UTM attribution |
| [WhatsApp Cloud API](https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/overview) | `messages` webhook with `wamid` IDs and `statuses` webhooks; BSUID may replace phone; 24-hour customer service window; approved templates required outside it; opt-in required; `user_preferences` and template-status webhooks exist | Dedupe on `wamid`, store BSUID, window-aware template gate, consent provenance, status webhook updates |

---

## 3. Current-state gaps (verified from code)

| # | Gap | Evidence |
|---|---|---|
| G1 | Five tables and generic CRUD only; no domain service layer | `backend/app/modules/crm/models.py:13-104`, `backend/app/modules/crm/router.py:32-96` |
| G2 | `Lead.score` defaults to 0, is present in create/update schemas, and nothing computes it | `crm/models.py:58`, `crm/schemas.py:110,129`; no scorer in repo |
| G3 | `Deal.stage` is a free string; no stage table, order, guards, or weighted amount | `crm/models.py:81-89` |
| G4 | No conversion endpoint and no `deal.won` publisher or subscriber | `crm/router.py:24-96`, `backend/app/core/subscribers.py` |
| G5 | `whatsapp_opt_in` is a bare boolean; no consent source, timestamp, policy, or revocation | `crm/models.py:43,63` |
| G6 | Webhook signature check and `external_id` dedupe exist, but tenant is the first tenant in the DB | `backend/app/modules/integrations/router.py:31-33,36-45,72-80` |
| G7 | Consent gate blocks explicit `False` only; `unknown` is allowed, and lookup scans up to 1000 rows per model in Python | `backend/app/modules/integrations/service.py:27-43,58-63` |
| G8 | Inbound subscriber only appends a note to an existing lead; no lead creation, opt-in capture, scoring, or timeline | `backend/app/core/subscribers.py:29-77` |
| G9 | No Meta Lead Ads, social inbox, social publishing, call, transcript, or assessment tables | `backend/app/modules/integrations/`, `backend/app/modules/crm/` file lists |
| G10 | CRM permissions cover only company/contact/lead/deal/activity; bus is in-process with no CRM outbox | `backend/app/core/permissions_catalog.py:11`, `backend/app/core/events.py:21-45` |
| G11 | AI answers pipeline KPIs but produces no scored explanation or approved action | `backend/app/modules/ai/service.py:46,198` |

---

## 4. Target object model

CRM owns every `crm_*` table; Integrations owns `channel_messages` and the new `integration_webhook_events` ledger; Sales owns `customers` (I1). All new tables inherit `TenantBaseModel` (`backend/app/db/base.py:54`).

**Extend existing tables**

| Table | Additions |
|---|---|
| `crm_leads` | `score_model_version`, `score_updated_at`, `score_grade`, `score_trend`, `score_features` (JSON), `engagement_count`, `last_activity_at`, `dedupe_key`, `external_ref`, `utm_source/medium/campaign`, `converted_deal_id`, `lost_reason` |
| `crm_contacts` | `consent_captured_at`, `consent_source`, `wa_id`/`bsuid`, `is_primary`, `linked_customer_id` |
| `crm_deals` | `stage_id` FK, `weighted_amount` (computed), `next_step`, `next_step_due`, `lost_at`, `won_event_id` |
| `crm_companies` | `parent_company_id`, `employee_count`, `owner_id`, `linked_customer_id` |
| `crm_activities` | `outcome`, `channel_message_id`, `call_id`, `duration_seconds`, `reminder_sent_at` |

**New tables**

| Table | Key columns |
|---|---|
| `crm_stages` | `name`, `sequence`, `probability_default`, `is_won`, `is_lost`, `is_active` |
| `crm_lead_sources` | `name`, `type`, `utm_pattern`, `is_active` |
| `crm_consent_records` | `subject_type`, `subject_id`, `channel`, `status`, `source`, `policy_version`, `proof_ref`, `captured_at`, `revoked_at` (append-only) |
| `crm_score_models` | `version`, `feature_spec`, `coefficients`, `metrics`, `trained_at`, `is_active`, `activation_state` |
| `crm_score_facts` | `lead_id`, `model_version`, `score`, `grade`, `trend`, `features`, `source_event_id`, `computed_at`; unique `(lead_id, model_version, source_event_id)` |
| `crm_engagements` | `channel`, `direction`, `occurred_at`, `lead_id`, `contact_id`, `deal_id`, `external_ref`, `summary`, `actor_id`, `source_event_id` |
| `crm_calls` | `lead_id`, `contact_id`, `deal_id`, `provider`, `external_call_id`, `direction`, `started_at`, `ended_at`, `duration_seconds`, `recording_ref`, `consent_record_id`, `owner_id` |
| `crm_call_transcripts` | `call_id`, `sequence`, `speaker`, `text`, `started_at`, `confidence` |
| `crm_call_assessments` | `call_id`, `rubric_version`, `score`, `signals`, `summary`, `next_best_action`, `status`, `reviewer_id`, `reviewed_at` |
| `crm_inbox_assignments` | `conversation_key`, `assignee_id`, `status`, `sla_due_at`, `closed_at` |
| `crm_social_accounts` | `channel`, `external_account_id`, `token_ref` (Settings vault), `is_active`, `last_sync_at` |
| `crm_social_messages` | `account_id`, `external_message_id`, `direction`, `author_external_id`, `contact_id`, `body`, `posted_at`, `raw_payload` |
| `crm_social_posts` | `account_id`, `body`, `media_refs`, `status`, `scheduled_at`, `external_post_id`, `approved_by_id`, `campaign_id`, `published_at` |
| `integration_webhook_events` (Integrations) | `provider`, `event_type`, `external_event_id`, `payload_hash`, `signature_valid`, `status`, `attempts`, `last_error`, `processed_at`; unique `(provider, event_type, external_event_id)` |

---

## 5. API surface

All endpoints are mounted under `/api/v1`. Permission codes follow `module.resource.action`; register new CRM resources in `MODULE_RESOURCES["crm"]` and new verbs in `EXTRA_PERMISSIONS` (`backend/app/core/permissions_catalog.py:10,106`).

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/crm/leads/{id}/convert` | POST | `crm.lead.convert` | Atomic lead → deal (+company/contact) |
| `/crm/leads/{id}/rescore` | POST | `crm.lead.rescore` | Explicit scorer trigger |
| `/crm/leads/{id}/score-explanation` | GET | `crm.score.read` | Score, grade, trend, top-3 features, model version |
| `/crm/leads/duplicates` | GET | `crm.lead.read` | Duplicate candidates by `dedupe_key` |
| `/crm/leads/{id}/merge` | POST | `crm.lead.merge` | Merge duplicate with audit and reversal record |
| `/crm/stages` | CRUD | `crm.stage.*` | Pipeline configuration |
| `/crm/stages/reorder` | POST | `crm.pipeline.configure` | Board column order |
| `/crm/deals/{id}/advance` | POST | `crm.deal.advance` | Guarded stage move |
| `/crm/deals/{id}/win` | POST | `crm.deal.win` | Close won, emit `deal.won` once |
| `/crm/deals/{id}/lose` | POST | `crm.deal.lose` | Close lost with reason |
| `/crm/engagements` | GET/POST | `crm.engagement.read` / `crm.engagement.create` | Unified timeline |
| `/crm/consent` | POST | `crm.consent.capture` | Append consent record with proof |
| `/crm/consent/{subject_type}/{subject_id}` | GET | `crm.consent.read` | Current consent state |
| `/crm/consent/{id}/revoke` | POST | `crm.consent.revoke` | Append revocation |
| `/crm/calls` | POST | `crm.call.create` | Log call and recording consent |
| `/crm/calls/{id}/transcript` | POST | `crm.call.update` | Store transcript segments |
| `/crm/calls/{id}/assess` | POST | `crm.call.assess` | Generate draft assessment |
| `/crm/calls/{id}/assessment` | GET | `crm.call.read` | Read assessment and signals |
| `/crm/calls/{id}/assessment/{aid}/approve` | POST | `crm.call.approve` | Human approval of AI assessment |
| `/crm/inbox/conversations` | GET | `crm.inbox.read` | Unified inbox queue |
| `/crm/inbox/conversations/{id}/assign` | POST | `crm.inbox.assign` | Assign and set SLA |
| `/crm/inbox/conversations/{id}/reply` | POST | `crm.inbox.reply` | Reply via Integrations bridge |
| `/crm/social/accounts` | CRUD | `crm.socialaccount.*` | Connect channels via vault token ref |
| `/crm/social/posts` | POST | `crm.socialpost.create` | Create draft post |
| `/crm/social/posts/{id}/approve` | POST | `crm.socialpost.approve` | Approval gate |
| `/crm/social/posts/{id}/publish` | POST | `crm.socialpost.publish` | Publish via adapter, store external ID |
| `/crm/social/posts/{id}/metrics` | GET | `crm.socialpost.read` | Published post metrics |
| `/integrations/webhooks/meta-lead-ads` | POST | `integrations.webhook.ingest` (service) | Page `leadgen` webhook |
| `/integrations/whatsapp/webhook` | POST | public + signature | Existing WhatsApp webhook (`integrations/router.py:59`) |
| `/crm/reports/pipeline` | GET | `crm.report.read` | Weighted pipeline by stage/owner |
| `/crm/reports/attribution` | GET | `crm.report.read` | Source/CTWA/lead-ads conversion |

---

## 6. Webhook ingestion and idempotency

1. Verify `X-Hub-Signature-256` over the raw body before parsing or writing; production rejects missing secrets (`integrations/router.py:36-45` is the reference). Add a timestamp/nonce replay window.
2. Resolve tenant from a channel binding (phone-number-id or page-id mapped in Integrations config), replacing `_default_tenant_id` at `integrations/router.py:31-33`. No inbound row may be attributed to the first tenant.
3. Insert `integration_webhook_events` with unique `(provider, event_type, external_event_id)`; on redelivery return HTTP 200 with `duplicate: true` and publish nothing. Store `payload_hash` for audit and manual replay.
4. Parse WhatsApp `messages` into `ChannelMessage` deduped on `wamid`; parse `statuses` into sent/delivered/read updates; parse Page `leadgen` notifications, then hydrate `field_data` via the Graph API using `leads_retrieval` and map `ad_id`/`form_id` to `utm_*`.
5. Write rows and outbox event in one transaction; emit `lead.inbound.received` / `engagement.received` only after commit. CRM subscriber upserts Lead/Contact by `dedupe_key`, appends `crm_engagements`, captures consent, and triggers scoring.
6. Store BSUID (`from_user_id`/`user_id`) as stable identity; phone may be absent. Retry with backoff, dead-letter after N attempts; never reprocess a processed event without an explicit replay that writes a new outbox row.

---

## 7. Consent and audit

- `crm_consent_records` is append-only: capture, revoke, and policy-version changes are new rows; subject state is derived from the latest row. WhatsApp opt-in text must name the business and state the purpose (Meta policy + DPDP Act 2023).
- Hard gate in `send_message`: explicit `opted_out` and `unknown` both fail with `CONSENT_REQUIRED` for template/marketing sends; only a verified opt-in or an open 24-hour service window with a bound contact may proceed. This closes G7.
- The 24-hour window is derived from the latest inbound `crm_engagements.occurred_at`; outside it, an approved template is mandatory. Template approval status comes from the `message_template_status_update` webhook.
- Audit every stage move, conversion, consent mutation, score recomputation, assessment approval, and publish decision with `correlation_id` via `backend/app/core/audit.py`; mask phone/email per D4. DPDP erasure anonymises contact PII while retaining the deal's financial record.

---

## 8. Explainable lead scoring

- Tier 1, tabular and deterministic: logistic regression or gradient boosting in sklearn, versioned in `crm_score_models`. No LLM in scoring (A5). Remove `score` from `LeadCreate`/`LeadUpdate`; only the scorer service writes it.
- Feature groups mirror HubSpot/Pipedrive: fit (company size, industry, revenue, title, source) and engagement (recency, `engagement_count`, channel mix, replies, call outcome), each capped; rules add +25/+10/-10 until a model is trained. Score is 0–100 with grade A–D and trend against the prior `crm_score_facts` row.
- Minimum training data gate: at least 40 converted and 40 lost leads per tenant, otherwise the rule scorer runs so `score` is never stuck at 0. One active model per tenant/pipeline.
- Each `crm_score_facts` row stores the top three signed features; `GET /crm/leads/{id}/score-explanation` renders them (A4). Bot, out-of-office, and duplicate-touch signals are filtered from engagement features.
- Recompute on inbound engagement, stage change, and nightly sweep; idempotent on `(lead_id, model_version, source_event_id)`. Model version and coefficients are audited; a drift report is a Phase 4 item.

---

## 9. AI calling with transcript and scoring

- Calls arrive through `POST /crm/calls` from the telephony/Engage provider; recording requires a voice-channel consent record. Transcript segments are stored per call with speaker and confidence; PII is redacted before persistence and raw audio stays as an encrypted reference.
- Assessments use a versioned rubric (qualification questions asked, objections, sentiment, next step) to produce a 0–100 call score, summary, and `next_best_action`. Signals feed both `crm_engagements` and lead scoring features.
- AI output is Tier 2 read-only until a reviewer calls `POST /crm/calls/{id}/assessment/{aid}/approve` (A3). Approval writes an audit row; an AI assessment can never silently change lead status or deal stage. Rejections are logged for rubric tuning.

---

## 10. Unified social inbox and publishing

- `crm_social_messages` normalises comments, DMs, and mentions into the same `crm_engagements` timeline as WhatsApp and calls. Conversation key is `(account_id, channel, author_external_id)`; `crm_inbox_assignments` owns assignee, status, and SLA due time.
- Replies route through `engage_bridge.send_message`; channel caps, the 24-hour window, and consent are enforced by Integrations, never by a vendor SDK in CRM.
- Publishing state machine: `draft → pending_approval → approved → scheduled → published → failed`. `crm.socialpost.approve` and `crm.socialpost.publish` are separate permissions; `external_post_id` gives idempotency and metrics lookup.
- Tokens live in the Settings secret vault as `token_ref` and rotate via the existing external-credentials endpoints; no secret is stored in a CRM table.

---

## 11. Security and tenant isolation

- Every read/write query scopes by `tenant_id` from the authenticated user; webhook and subscriber payloads carry `tenant_id` and are validated against the channel binding. A cross-tenant lead ID returns 404/403, never a filtered empty list that leaks existence.
- Add CRM resources to the catalog: `stage`, `leadsource`, `score`, `consent`, `engagement`, `call`, `inbox`, `socialaccount`, `socialmessage`, `socialpost`, `report`, `outbox`, plus extra verbs `lead.convert`, `lead.rescore`, `lead.merge`, `deal.advance`, `deal.win`, `deal.lose`, `pipeline.configure`, `score.read`, `consent.capture/read/revoke`, `call.assess/approve`, `inbox.read/assign/reply`, `socialpost.approve/publish`, `report.read`, `webhook.ingest`.
- Least privilege: `sales` role gets lead/deal/stage/engagement/call/consent read; `manager` additionally gets `crm.pipeline.configure` and call approvals; social publishing goes to a marketing/social role, not to every viewer.
- Rate-limit inbound webhooks, verify signatures in constant time, mask personal fields without `crm.contact.read` (D4), and keep cross-module effects as outbox events (D2). CRM posts no journals (I3) and creates no customers directly (I1).

---

## 12. Phased rollout

| Phase | Scope | Acceptance |
|---|---|---|
| **Phase 1 — implement now** | G1–G8 closure: tenant-safe signed webhooks for WhatsApp and Meta Lead Ads; consent ledger + hard gate; `crm_stages` with guards; lead conversion and once-only `deal.won`; explainable rule/ML scorer with `crm_score_facts`; dedupe/merge; inbound lead creation and engagement timeline; RBAC, audit, tests | Tests in §13 green; a WhatsApp message and a lead-ads lead each become a scored lead without manual entry; score non-zero and explained; `deal.won` fires once |
| Phase 2 | Unified inbox, social accounts, social publishing with approval, SLA queue | Reply and publish flows audited; token refs only; no unsupported channel writes |
| Phase 3 | Call logging, transcript ingestion, rubric assessment, human approval, call features in scoring | No assessment changes a stage without approval; transcript PII redacted |
| Phase 4 | ML retraining job, drift report, attribution dashboards, automated quality rules | Model version promotion audited; attribution ties back to ad/form IDs |

Phase 1 explicitly excludes social channels, calling, autonomous actions, and ML training; it ships the deterministic rule scorer and the data needed to train later.

---

## 13. Test and verification plan

- New pytest modules under `backend/app/tests/`: `test_crm_scoring.py`, `test_crm_conversion.py`, `test_crm_webhooks.py`, `test_crm_consent.py`, `test_crm_tenant_scope.py`.
- Webhook: wrong signature returns 403 with no row; redelivered `wamid`/`leadgen_id` creates one lead; tenant from channel binding, never first tenant; lead-ads hydration uses a stubbed Graph client.
- Scoring: fixture input gives deterministic 0–100 score and exactly three signed features; score rejects direct PATCH; rule fallback works below the training threshold; duplicate touches do not inflate engagement.
- Consent: `opted_out` and `unknown` block template sends; open 24-hour window allows a service reply; revocation is append-only and visible in audit.
- Conversion: lead → deal atomic; double `win` emits one `deal.won`; stage order guard rejects skips; cross-tenant lead ID is denied.
- Verification commands used in CI (`.github/workflows/ci.yml:58-69,113-117`): `cd backend && ruff check app scripts && pyright --pythonpath python && python -m pytest -q`; `cd frontend && npm test && npm run build`; Playwright happy path via `npm run test:e2e`. Add an Alembic upgrade/replay check for the new tables.

---

## 14. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Webhook still uses first tenant | Cross-tenant lead creation | Channel-binding tenant resolution is a Phase 1 blocker test |
| Consent `unknown` still passes | Meta ban, DPDP exposure | Hard gate change with explicit tests for all three states |
| Score stays writable/zero | "AI CRM" claim stays hollow | Remove from schemas; rule fallback; non-zero assertion in tests |
| ML trained on too little data | Unstable scores | 40/40 minimum gate and versioned rule fallback |
| `deal.won` duplicated | Double customer in Sales | Unique `won_event_id`, outbox idempotency, double-win test |
| Social tokens in wrong store | Credential leak | Settings vault refs and rotation endpoints only |
| Scope creep into calling/social in Phase 1 | Delayed core value | Explicit Phase 2/3 boundary and non-goals |

---

## 15. Non-goals

- Autonomous outbound dialling, AI-sent messages, or AI-driven stage changes without approval.
- Full social listening/firehose, ad campaign authoring, or influencer analytics.
- Building a BSP or replacing Meta's template review; templates remain governed by the provider.
- Duplicating Sales' `customers`, Finance's invoices/journals, or Marketing's campaign engine.
- Custom-field designer, territory/quota management, and a general workflow builder in Phase 1.

---

## 16. Definition of done (Phase 1)

- [ ] New tables migrated with tenant indexes and Alembic replay green.
- [ ] Signed, tenant-resolved, idempotent WhatsApp and Meta Lead Ads ingestion with outbox events.
- [ ] Consent ledger, hard gate, and audit rows for every consent/score/conversion mutation.
- [ ] Read-only, explainable, non-zero score with rule fallback and rescore endpoint.
- [ ] Lead conversion, guarded stages, and exactly-once `deal.won`.
- [ ] Dedupe/merge and unified engagement timeline for inbound messages.
- [ ] Permissions, role templates, field masking, and cross-tenant tests green.
- [ ] `docs/modules/README.md` conformance row updated when the phase is implemented.
