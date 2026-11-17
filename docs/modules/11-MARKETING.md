# 11 — Marketing Automation

**Module owner:** Marketing
**Current state:** Campaign/Segment/CampaignSend tables + CRUD exist; segments are stored JSON with **no evaluation engine**; no Meta Ads / Conversions API
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns outbound marketing: campaigns, audiences (segments), scheduled sends, and Meta ad attribution. Per the strategic plan (§2 row 14 and §4), Marketing Automation is the home for Click-to-WhatsApp ads, Meta Conversions API and campaign measurement — and per `Best-Product-Plan §3`, it is a **Phase 4 / "adequate" module**: build it well enough to run real campaigns and attribute them, don't gold-plate.

**In scope:** campaigns, segments (saved filters over the same DB — the single-database advantage), scheduling, send tracking, CTWA attribution, Conversions API events.
**Out of scope (v1):** full email marketing (ESP-style drag-drop editors, bounces), A/B testing, marketing attribution model across channels beyond Meta, loyalty/referral programs.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Campaign` (`marketing_campaigns`), `Segment` (`marketing_segments`), `CampaignSend` (`marketing_campaign_sends`) | ✅ 3 tables (`marketing/models.py`) |
| Campaign fields | `name, channel, status, start/end, budget, spend, goal, description` |
| Segment fields | `name, description, filters (JSON)` |
| CampaignSend fields | `campaign_id, segment_id, channel, status, scheduled_at, sent/delivered/failed_count` |
| CRUD routers | ✅ `marketing.campaign.*`, `marketing.segment.*`, `marketing.campaignsend.*` |
| **Segment evaluation** | ❌ `filters` is JSON but **no engine runs it** — nothing resolves a segment to a contact list |
| **Send execution** | ❌ `CampaignSend` has counters but **no worker actually sends anything** (no Celery worker, no Engage call) |
| **CTWA attribution** | ❌ no utm capture → Lead.source (module 07 M4) |
| **Meta Conversions API** | ❌ no server-side event posts |
| **Message templates** | ❌ no template library or Meta approval tracking |

**Headline:** the marketing *records* exist but nothing executes. A campaign cannot currently send a single message — the counters would just stay at zero. The real work is: segment engine, send executor (through Engage), template approval tracking, and Meta attribution.

---

## 3. Domain model

### 3.1 Target entities

```
marketing_campaigns
  + add: message_template_id, audience_total, sent_total, converted_total, roas,
          cost_per_acquisition, utm_campaign, cta_link, is_scheduled

marketing_segments
  + add: query_type [sql_snapshot|orm_filter], where_clause (safe, param), params,
          is_dynamic (re-evaluated at send), last_evaluated_count, created_by

marketing_campaign_sends
  + add: template_id, batch_size, status [scheduled|sending|paused|completed|failed],
          started_at, completed_at, error_log (JSON), schedule_cron

NEW:
marketing_message_templates   name, channel [whatsapp|email|sms], template_type,
                              body, params (JSON), meta_template_id, approval_status [draft|pending|approved|rejected],
                              category, language, media_url
marketing_send_items          campaign_send_id, contact_id (or phone), status [queued|sent|delivered|read|failed|undelivered],
                              channel_message_id, attempt, last_error, sent_at
marketing_conversion_events   source [capi|whatsapp|webhook], event_name, event_id, payload,
                              sent_to_meta (bool), meta_success, sent_at
marketing_campaign_leads      campaign_id, lead_id, attributed_at, source [ctwa|whatsapp]
```

### 3.2 Segment engine design
Segments are **saved filters over the live tables** (Strategic Plan §7, "no separate customer-data warehouse — again the single-database advantage"). The engine:
- `filters` JSON describes an ORM filter over `customers`/`contacts` (+ optional joins to orders/invoices).
- `evaluate()` returns matching IDs and counts; `is_dynamic` re-evaluates at send time.
- The query is built from an **allow-listed field map** (never raw SQL from stored text) — safe by construction.

---

## 4. State machines

### 4.1 Campaign
```
draft       --configure-->  ready       (template + segment + schedule set)
ready       --schedule-->   scheduled
scheduled   --launch-->     sending     (executor starts)
sending     --pause-->      paused      (rate-limit/resume)
sending     --complete-->   completed   (all items terminal)
sending/paused --cancel-->  cancelled
```
### 4.2 Send item
```
queued    --deliver-->   delivered   (WhatsApp delivered ack)
queued    --fail-->      failed      guard: retry exhausted
delivered --read-->      read        (WhatsApp read ack, optional)
delivered --convert-->   converted   (lead/order attributed)
```

---

## 5. API surface

Current: campaigns/segments/campaign-sends CRUD.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/marketing/segments/{id}/evaluate` | POST | `marketing.segment.read` | resolve to count + sample |
| `/marketing/segments/{id}/preview` | GET | `marketing.segment.read` | preview contacts |
| `/marketing/templates` | CRUD | `marketing.campaign.manage` | message templates + approval status |
| `/marketing/campaigns/{id}/schedule` | POST | `marketing.campaign.manage` | set schedule + template |
| `/marketing/campaigns/{id}/launch` | POST | `marketing.campaign.manage` | start send |
| `/marketing/campaigns/{id}/pause` | POST | `marketing.campaign.manage` | pause |
| `/marketing/campaigns/{id}/report` | GET | `marketing.campaign.read` | sends/ROAS/conversions |
| `/marketing/capi/events` | POST | `system.integration.manage` | Conversions API fire (internal) |

---

## 6. Business rules

- **MK-01** — A campaign is launchable only with an approved template (WhatsApp) and a non-empty evaluated segment.
- **MK-02** — Segment evaluation is re-run at send time when `is_dynamic`; counts are snapshotted into `send_items`.
- **MK-03** — Sends respect per-tenant rate limits and business-hours windows; no burst that trips Meta.
- **MK-04** — Every send requires the contact's WhatsApp opt-in (hard gate — CR-07/PS-consent).
- **MK-05** — CTWA deep links carry a campaign tag; the first inbound message records `campaign_leads`.
- **MK-06** — Meta Conversions API fires on `order.completed`/`signup` server-side events, deduped by `event_id`.
- **MK-07** — ROAS = (attributed revenue − spend) / spend; attributed revenue from `conversion_events` + orders.
- **MK-08** — Failed sends retry up to N times with backoff; permanent failures are logged for list hygiene.

---

## 7. Workflows (end-to-end)

### 7.1 WhatsApp campaign (target)
1. Template created → submitted to Meta → approved.
2. Segment built (`customers in region X with >1 order`) → evaluated.
3. Campaign scheduled; launch → executor resolves `send_items`, checks opt-in, calls Engage `send_message` in batches.
4. Delivery/read acks update counters; failures retried.
5. Replies flow in → `channel_message.received` → CRM lead (source=`ctwa`/`whatsapp`, campaign attribution).
6. Conversions API posts order events → ROAS report.

### 7.2 Click-to-WhatsApp ad attribution
1. Ad served with `utm_campaign` deep link → prospect taps → WhatsApp thread.
2. First message → `ChannelMessage.payload` has the tag → CRM `Lead.source=ctwa`, `utm_campaign` stored.
3. `campaign_leads` links lead to campaign → conversion + ROAS.

---

## 8. Accounting impact

None directly. Ad spend is a marketing expense; attribution drives Finance reporting but no journals here.

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally + Excel** | Contact lists | Segments over live data; attribution | — |
| **Zoho Marketing Automation** | Campaigns, segments, CTWA ads | Segments = real filters on the same DB (Zoho syncs lists between apps) | Zoho's email editor/landing pages/automation breadth |
| **Meta Ads Manager** | CTWA, Conversions API | Attribution lands in the same ledger as revenue | Meta's ad-platform depth (we're an integrator) |
| **Odoo Marketing** | Campaigns, mailing lists | WhatsApp-native; no sync gap | Odoo's marketing automation coupling |
| **HubSpot (marketing)** | Workflows, attribution | cheap + WhatsApp | HubSpot's full marketing hub |

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Segment suggestion** — "customers at risk of churn" (last order > X days) | marketer picks an audience | suggestion from fixed template, not freeform |
| 1 | **Best-send-time** per segment from historical engagement | scheduling changes | read-only |
| 2 | "ROAS of last campaign?", "which segment converts best?" | instant answer | read-only |
| 3 | **Auto-draft campaign** from a CRM trigger (e.g. reorder season) | marketer approves | approval + audit (A3) |

Marketing AI stays modest — this is an "adequate" module.

---

## 11. Non-functional & security

- Performance: segment evaluate < 2 s at 100k contacts (index + precomputed counts).
- Rate limits: per-tenant, per-hour WhatsApp cap; backoff on Meta errors.
- RBAC: `marketing.campaign.*`, `marketing.segment.*`, `marketing.campaignsend.*` (exists) + add `marketing.campaign.manage`.
- Consent: opt-in gate (MK-04) is a hard legal requirement, not a setting.
- DPDP: contact PII used only for the campaign purpose; unsubscribe respected; retention for send logs.
- Audit: every launch/pause/template approval.

---

## 12. Reporting & analytics

Sent/delivered/read/convert per campaign, ROAS, CAC, cost per WhatsApp conversation, segment counts trend, channel performance. Materialised views: `marketing_campaign_perf`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `order.completed` | in | Conversions API (server-side) |
| `signup` (new lead) | in | Conversions API |
| `channel_message.received` | in | CRM attribution (campaign_leads) |
| `campaign.completed` | out | Analytics |
| Outbound send | → | Engage `send_message` (module 12) |
| Template submission | → | Meta WhatsApp template API |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (segment engine)** | safe filter evaluation + counts + preview | MK-02 tests; no SQL injection (allow-list) |
| **M2 (send executor)** | template library + approval status; Celery worker → Engage; send_items + retries | MK-01/03/08 tests; one real send in sandbox |
| **M3 (CTWA + CAPI)** | deep-link attribution; Conversions API with dedupe | MK-05/06 tests |
| **M4 (reporting)** | ROAS + CAC reports | MK-07 tests |

Order: **M1 → M2 → M3 → M4**. M2 needs the Engage outbound path (module 12) to actually work.

---

## 15. Test plan

- Segment: dynamic re-evaluation changes list; unsafe filter rejected (M1).
- Send: opt-out excluded; retry logic; burst throttled (M2).
- Attribution: CTWA tap → lead with campaign; CAPI dedupe (M3).
- ROAS math (M4).

---

## 16. Migration & rollout

- Import historical campaigns/segments from CSV; set `is_dynamic=false` for snapshots.
- Cutover: launch a pilot campaign on a test number (Meta sandbox) before production.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Sends without opt-in | Meta ban + DPDP breach | MK-04 hard gate |
| Template rejected by Meta | campaign stalls | approval tracking + fallback template |
| No segment engine (ships CRUD only) | campaigns are decoration | M1 blocker |

---

## 18. Definition of Done

- [ ] M1 segment engine (safe filters, no injection)
- [ ] M2 send executor + template approvals + retries (real sandbox send)
- [ ] M3 CTWA attribution + Conversions API
- [ ] M4 ROAS/CAC reporting
- [ ] RBAC, consent, DPDP, audit, outbox
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated