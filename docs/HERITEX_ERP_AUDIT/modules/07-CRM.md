# 07 — CRM (Companies, Contacts, Leads, Deals)

**Module owner:** CRM
**Current state:** 5 tables + generic CRUD exist; `Lead.score` is a dead column (nothing computes it); no pipeline stages config, no conversion
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns demand generation: companies, contacts, leads, deals (pipeline), activities. CRM is where conversations with prospects live, and where the WhatsApp channel first touches a person. It does **not** own customers — Sales does (Invariant I1); CRM feeds a customer into Sales on `deal.won`.

**In scope:** companies/contacts, leads with source attribution, deals with stages and probability, activities/tasks, lead→deal→customer conversion, WhatsApp opt-in capture.
**Out of scope (v1):** email marketing campaigns (module 11), call logging via voice (module 12), territory/quota management (v1.5), custom field designer.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Company`, `Contact`, `Lead`, `Deal`, `Activity` | ✅ 5 tables (`crm/models.py`) |
| Contact fields | `company_id, first_name, last_name, email, phone, title, whatsapp_opt_in, notes` |
| Lead fields | `name, company_name, email, phone, source, status, score, estimated_value, owner_id, whatsapp_opt_in, next_follow_up` |
| Deal fields | `name, company_id, contact_id, lead_id, stage, amount, probability, expected_close_date, owner_id, won_at` |
| CRUD routers | ✅ `crm.company.*`, `crm.contact.*`, `crm.lead.*`, `crm.deal.*`, `crm.activity.*` |
| **Lead scoring** | ❌ `score` column exists, **nothing computes it** — always 0 |
| **Pipeline stages** | 🟡 `stage` is a free string, default `qualification`; no configurable stage list, no stage-gate rules |
| **Lead→Deal→Customer conversion** | ❌ no conversion endpoint; `deal.won` event exists in plan but **is never published** |
| **WhatsApp opt-in enforcement** | ❌ field exists; nothing reads it before a channel send |
| **Activity automation** | ❌ no reminders/next-action enforcement |
| **Duplicate detection** | ❌ (two contacts with same phone create two leads) |
| **Kanban/board ordering** | ❌ no stage ordering column |

**Headline gaps:** the data model is complete but **inert** — `score` never computed, no conversion path to Sales, `deal.won` never emitted, opt-in never enforced. CRM today is a CRUD form set, not a pipeline.

---

## 3. Domain model

### 3.1 Target entities

```
crm_companies
  name, industry, website, gstin, email, phone, address, city, state, country, annual_revenue, notes
  + add: is_active, parent_company_id, employee_count, owner_id, source, linked_customer_id (Sales customer)

crm_contacts
  company_id, first_name, last_name, email, phone, title, whatsapp_opt_in, notes
  + add: is_primary, consent_captured_at (DPDP), consent_source, owner_id, linked_customer_id

crm_leads
  name, company_name, email, phone, source [manual|whatsapp|web|ctwa|referral], status [new|contacted|qualified|converted|lost],
  score (int, computed), estimated_value, owner_id, whatsapp_opt_in, notes, next_follow_up
  + add: score_updated_at, score_features (JSON — explains the score, AI rule A4),
          converted_deal_id, lost_reason, utm_source/medium/campaign (CTWA attribution),
          last_activity_at, engagement_count

crm_deals
  name, company_id, contact_id, lead_id, stage, amount, probability, expected_close_date, owner_id, notes, won_at
  + add: stage_id -> crm_stages (configurable), lost_at, lost_reason, weighted_amount (computed),
          owner_type, source, next_step, next_step_due

crm_activities
  activity_type [task|call|meeting|whatsapp|email], subject, notes, related_entity, related_id, due_at, completed, owner_id
  + add: outcome, channel_message_id (link to Integrations), duration, reminder_sent

NEW:
crm_stages        name, sequence, probability_default, is_won, is_lost, is_active
crm_lead_sources  name, type [manual|web|whatsapp|ctwa|referral], utm_pattern, is_active
```

### 3.2 Why stages become a table
A free-string `stage` cannot be ordered, gated, or reported. `crm_stages` gives a Kanban board its column order and gives the win-probability used in forecasts. This is table stakes against Zoho/SAP.

---

## 4. State machines

### 4.1 Lead
```
new       --contact-->   contacted     → activity created, engagement_count++
contacted --qualify-->   qualified     guard: has phone/email, an activity logged     → score recomputed
qualified --convert-->   converted     → creates Deal (+Company/Contact if absent)    → event 'lead.converted'
any open  --lose-->      lost          guard: lost_reason present
```
### 4.2 Deal
```
qualification --advance--> proposal      (stage order from crm_stages)
proposal      --advance--> negotiation
negotiation   --advance--> closed_won    guard: amount > 0                   → event 'deal.won' → Sales creates customer
any           --close-lost--> closed_lost guard: lost_reason
closed_won    --reopen-->   negotiation  (audit; rare)
```
### 4.3 Activity
```
planned  --complete-->  completed   guard: outcome recorded
planned  --cancel-->    cancelled
planned  --escalate-->  planned     (overdue → reminder via Engage, module 12)
```

---

## 5. API surface

Current: CRUD for companies, contacts, leads, deals, activities.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/crm/leads/{id}/convert` | POST | `crm.lead.update` | lead → deal (+company/contact) |
| `/crm/deals/{id}/advance` | POST | `crm.deal.update` | stage move with guard |
| `/crm/deals/{id}/win` | POST | `crm.deal.update` | close won → `deal.won` |
| `/crm/deals/{id}/lose` | POST | `crm.deal.update` | close lost + reason |
| `/crm/stages` | CRUD | `crm.deal.update` | pipeline configuration |
| `/crm/leads/{id}/rescore` | POST | `crm.lead.update` | trigger Tier 1 rescoring |
| `/crm/reports/pipeline` | GET | `crm.deal.read` | weighted pipeline by stage/owner |
| `/crm/leads/duplicates` | GET | `crm.lead.read` | duplicate candidate list |
| `/crm/contacts/{id}/opt-in` | POST | `crm.contact.update` | consent capture (DPDP) |

---

## 6. Business rules

- **CR-01** — Customers are owned by Sales; CRM links to `customers` on deal win, never duplicates the table.
- **CR-02** — A `Lead.score` is always computed by the Tier 1 scorer, never edited by hand; `score_features` explains it (A4).
- **CR-03** — Lead conversion creates a Deal and (if absent) Company+Contact atomically.
- **CR-04** — `deal.won` publishes exactly once (idempotent on `won_at`).
- **CR-05** — Probability defaults from the stage; `weighted_amount = amount × probability/100`.
- **CR-06** — A deal cannot be `closed_won` without an amount and at least one activity.
- **CR-07** — WhatsApp sends require `whatsapp_opt_in = true`; the consent capture time and source are stored (DPDP).
- **CR-08** — Duplicate detection on phone/email at lead and contact creation (warn, don't block).
- **CR-09** — Overdue activities appear in a work queue and trigger a reminder event.

---

## 7. Workflows (end-to-end)

### 7.1 WhatsApp lead → deal → customer (the moat path)
1. Inbound WhatsApp message → Integrations `channel_message.received`.
2. CRM subscriber matches phone → creates/updates Lead (source=`whatsapp`), opt-in captured (BR-CR-07).
3. Tier 1 scores the lead; Tier 3 may draft a follow-up (module 14).
4. Rep qualifies → convert → Deal.
5. Deal advances through stages; activities logged.
6. `deal.won` → Sales creates `Customer`, Finance can invoice; Analytics records conversion.

### 7.2 Click-to-WhatsApp ad attribution
1. Ad opens WhatsApp with a pre-filled message containing a campaign tag.
2. Integrations stores `utm_*` in `ChannelMessage.payload`.
3. CRM reads payload → `Lead.source = ctwa`, `utm_campaign` stored → attribution in module 11.

---

## 8. Stock & accounting impact

None directly. On `deal.won` → Sales creates a customer; only Sales/Finance create money documents. CRM never posts journals (I3).

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally + Excel** | Contact list, follow-up reminders | Real pipeline, scoring, WhatsApp-native leads | — |
| **Zoho CRM** | Pipeline, lead source, scoring, workflows | Single-DB link to invoicing/orders — no Zoho CRM→Books sync gap | Zoho's 45-app ecosystem, Zia AI breadth |
| **SAP B1 (CRM)** | Opportunities, activities | Lightweight; WhatsApp-first | SAP's full CRM (C4C) depth |
| **Odoo CRM** | Kanban pipeline, lead scoring | Native channel/opt-in; forecast | Odoo's marketing automation coupling |
| **Dynamics 365 Sales** | Pipeline, forecasting | (n/a v1) | enterprise sales intelligence |

**Differentiator to demo:** a WhatsApp message from a stranger becomes a scored lead → deal → invoice, with no app install and no sync button (Best-Product Plan §2.2).

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Lead scoring** — features: source, engagement count, company size, deal age, past outcomes. Logistic regression / GBM (sklearn), **not** an LLM | rep's call order changes | `score_features` shown (A4) |
| 1 | **Stale-deal flag** — no activity in N days | rep acts or closes | read-only |
| 2 | "Which deals are closing this month?", "leads from WhatsApp last week" | instant answers | read-only |
| 3 | **Auto-draft WhatsApp follow-up** for top-scored/stale leads via Engage | rep approves send | template allow-list + consent (CR-07, A3) |

The scoring model must be tabular and explainable — an LLM here would be slower, costlier and unauditable (A5).

---

## 11. Non-functional & security

- Performance: pipeline board p95 < 300 ms for 10k deals; lead list < 300 ms.
- Concurrency: stage advance uses optimistic lock; `deal.won` idempotent.
- RBAC: `crm.company.*`, `crm.contact.*`, `crm.lead.*`, `crm.deal.*`, `crm.activity.*` (exists) + add `crm.pipeline.configure`.
- **Field security (D4):** contact phone/email are personal data — masked for users without `crm.contact.read`; consent fields immutable except by consent-capture flow.
- DPDP: consent + source + timestamp stored; erasure request deletes/anonymises contact while keeping the deal's financial record.
- Audit: stage changes, conversions, consent changes.

---

## 12. Reporting & analytics

Pipeline value & weighted forecast by stage/owner, conversion rates (lead→deal→won), win/loss reasons, sales-cycle length, activity volume, source attribution (incl. CTWA). Materialised views: `crm_pipeline`, `crm_conversion_funnel`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `deal.won` | out | Sales (create customer), Finance, Analytics |
| `lead.converted` | out | Analytics |
| `channel_message.received` | in | CRM creates/updates lead, captures opt-in |
| `invoice.paid` | in | CRM can close related deal activity |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (pipeline real)** | `crm_stages` table + board ordering + advance guards | CR-05/CR-06 tests |
| **M2 (conversion)** | lead→deal→customer; publish `deal.won`; create Sales customer | CR-03/CR-04 tests |
| **M3 (scoring)** | sklearn scorer + `score_features` + nightly job (starts module 14) | CR-02 tests; scores non-zero & explainable |
| **M4 (consent + WhatsApp lead)** | opt-in capture, inbound lead creation, CTWA attribution | CR-07 tests; end-to-end WhatsApp lead |
| **M5 (duplicates + activities)** | dedupe, overdue queue, reminders via Engage | CR-08/CR-09 tests |

Order: **M1 → M2 → M3 → M4 → M5**.

---

## 15. Test plan

- Stage advance respects order; can't skip won without amount (M1).
- Conversion atomicity; `deal.won` fires once (M2).
- Score is deterministic for fixture input and exposes features (M3).
- WhatsApp inbound → lead with opt-in + source (M4).
- Duplicate phone warns (M5).
- Idempotency: double win.

---

## 16. Migration & rollout

- Tally: customer master → `customers` (Sales), then seed CRM contacts from it (linked).
- Import open opportunities from a CSV; map stages.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Score column stays inert | "AI CRM" claim hollow | M3 before any AI sales claim |
| Sync gap to Sales (two customer lists) | the Zoho failure mode | CR-01 enforced; `deal.won` creates customer in Sales only |
| Opt-in not enforced | Meta bans the number; DPDP breach | CR-07 as a hard gate in Integrations |
| No stage config | forecasts meaningless | M1 before reporting |

---

## 18. Definition of Done

- [ ] M1 configurable pipeline + guards
- [ ] M2 conversion + `deal.won` → Sales customer
- [ ] M3 explainable scoring job
- [ ] M4 consent capture + WhatsApp→lead + CTWA attribution
- [ ] M5 dedupe + activity queue
- [ ] RBAC, field masking, DPDP consent, audit, outbox
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated