# 10 — Support / Helpdesk (Ticketing)

**Module owner:** Support
**Current state:** Ticket + TicketMessage with SLA fields exist; SLA timers and WhatsApp-channel routing unbuilt
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns customer support: tickets, threaded messages, priorities, assignment, SLAs, resolution. Per the strategic plan (§2 «Customer Support»), this formalises as a module what Engage's Ticket Agent already does conceptually over WhatsApp — the ticket becomes the *work record*, WhatsApp becomes the *transport*.

**In scope:** ticket lifecycle, channels (web/WhatsApp/email), SLA timers, assignment, escalation, satisfaction feedback, knowledge-base link (module 19-docs).
**Out of scope (v1):** Omni-agent routing across voice, form builder, advanced CSAT workflows, ITSM (assets/incident/change).

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `Ticket` (`support_tickets`), `TicketMessage` (`support_ticket_messages`) | ✅ 2 tables (`support/models.py`) |
| Ticket fields | `ticket_number, subject, description, customer_id, requester_name/email, channel [web|whatsapp|...], priority, status [open|...], assignee_id, sla_due_at, resolved_at` |
| Message fields | `ticket_id, author_id, author_name, body, is_internal, channel` |
| Add-message + publish `ticket.message.created` | ✅ `router.py:50-94` |
| Resolve endpoint | ✅ `router.py:98` |
| **SLA computation** | 🟡 `sla_due_at` exists but **nothing computes or enforces it** (no timer, no breach check, no escalation) |
| **Priority → SLA mapping** | ❌ |
| **Assignment/triage rules** | ❌ auto-assign absent |
| **WhatsApp round-trip** | ❌ inbound `channel_message.received` is published by Integrations but **no subscriber creates/updates a Ticket** |
| **Escalation** | ❌ |
| **CSAT/satisfaction** | ❌ |
| **Reopen** | ❌ |

**Headline:** a ticket form that can store a due-at time nobody ever sets. SLA fields are inert because nothing computes them and no event listener ties WhatsApp→Ticket.

---

## 3. Domain model

### 3.1 Target entities

```
support_tickets
  + add: sla_policy_id, sla_started_at, breached_at, escalated_at, escalated_to_id,
          first_response_at, resolution_window_minutes, reopened_count, csat_rating,
          linked_customer_id, linked_lead_id, tags, is_closed_via_channel

support_ticket_messages
  + add: message_type [text|note|system], attachment_ids, channel_message_id (link to Integrations)

NEW:
support_sla_policies      name, priority, first_response_minutes, resolution_minutes,
                          business_hours_only (bool), channel, is_active
support_ticket_events     ticket_id, event_type [created|assigned|replied|breached|escalated|resolved|reopened],
                          at, actor_id, note
support_csat              ticket_id, rating (1-5), comment, asked_at, answered_at
support_kb_articles       title, body, category_id, tags, views, helpful_count (linked from module 19)
```

### 3.2 SLA design
`support_sla_policies` maps (priority × channel) → first-response and resolution windows. On ticket create the policy is looked up, `sla_due_at` computed (business-hours-aware), and a scheduled job checks breaches hourly. Breach → event + escalation + notification via Integrations.

---

## 4. State machines

### 4.1 Ticket
```
open        --assign-->   assigned     (auto-assign by round-robin/queue or manual)
assigned    --reply-->    awaiting_customer   (agent replied, ball in customer court)
awaiting_customer --reply--> in_progress  (customer replied)
in_progress --resolve-->  resolved     guard: resolution note present   → CSAT request
resolved    --reopen-->   open         guard: within reopen policy, count++   → timers restart
any         --breach-->   breached     (sla_due_at passed, job-detected) → escalate
breached    --resolve-->  resolved
assigned/in_progress --escalate-->  escalated   → notify manager, priority up
```

---

## 5. API surface

Current: tickets CRUD, add message, resolve.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/support/tickets/{id}/assign` | POST | `support.ticket.update` | assign |
| `/support/tickets/{id}/escalate` | POST | `support.ticket.update` | escalate |
| `/support/tickets/{id}/reopen` | POST | `support.ticket.update` | reopen |
| `/support/tickets/{id}/csat` | POST | `support.ticket.read` | customer feedback |
| `/support/sla-policies` | CRUD | `support.ticket.update` | policy admin |
| `/support/reports/sla` | GET | `support.ticket.read` | SLA compliance rate |
| `/support/reports/queue` | GET | `support.ticket.read` | current workload |
| `/support/webhooks/engate-inbound` | POST | — | **subscriber** for `channel_message.received` |

---

## 6. Business rules

- **SP-01** — A ticket's `sla_due_at` is set from its policy on create; changing priority recomputes it.
- **SP-02** — Breach check runs on a schedule and on every state change; breach emits `ticket.sla_breached`.
- **SP-03** — Reopen increments `reopened_count`; > N reopens flags the ticket for review (AI).
- **SP-04** — Resolution requires a resolution note and closes with `resolved_at`.
- **SP-05** — Inbound WhatsApp from a known contact auto-creates or re-attaches a ticket via the `channel_message.received` subscriber (module 12).
- **SP-06** — Internal notes (`is_internal`) never go out to the customer channel.
- **SP-07** — First response is measured from `sla_started_at` to first non-internal agent message.
- **SP-08** — Ticket messages store the `channel_message_id` so the full WhatsApp thread survives channel changes.

---

## 7. Workflows (end-to-end)

### 7.1 WhatsApp → ticket → resolution (the moat path)
1. Customer WhatsApps support → Integrations webhook → `channel_message.received`.
2. Support subscriber matches contact → creates ticket (or reopens) with channel=`whatsapp`, source payload.
3. SLA timer starts; policy applies; queue assigns.
4. Agent replies in the console → outbound via Engage (consent checked) → `ticket.message.created`.
5. Resolve with note → CSAT request via Engage.
6. `ticket.resolved` → marketing/Analytics.

### 7.2 SLA breach escalation
1. `sla_due_at` passes (scheduled job).
2. Event `ticket.sla_breached` → mark breached, escalate to manager, notify via Engage.
3. Manager reassigns/prioritises → timers reset per policy.

---

## 8. Accounting impact

None — support has no journal entries. (Optional v2: billable support hours → module 09.)

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally + Excel** | Ticket list | SLA + WhatsApp round-trip | — |
| **Zoho Desk** | Ticketing, SLA, assignment rules | Same-ticket-as-ERP: tickets share customer/order context, WhatsApp-native | Zoho's automations/field-sets breadth |
| **Freshdesk/Zendesk** | Omnichannel, SLA, CSAT | Single DB with the order/invoice context behind the ticket | Freshdesk's workforce/AI breadth |
| **SAP (Service)** | Service orders, SLA | (lightweight n/a) | SAP's service management depth |

**Differentiator:** a ticket is not a silo — with one DB, an agent sees the customer's orders, invoices and stock in the same screen, and the whole thread runs in WhatsApp.

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Auto-triage** — priority + category + suggested assignee from subject/body/contact history (classifier, not LLM) | routing decision | suggestion with confidence; human override |
| 1 | **Escalation-risk flag** — ticket likely to breach (age, reopens, customer sentiment from messages) | agent prioritises queue | read-only |
| 2 | "Which tickets are at risk of breaching SLA?" | instant queue view | read-only |
| 3 | **Draft reply** suggestions from KB articles (LLM) for the agent to edit | agent sends faster | agent approves every send; never auto-send to customer (A3) |
| 3 | **Auto-close** duplicate/solved-pattern tickets with a confirmation | agent confirms single action | human confirm, audit |

---

## 11. Non-functional & security

- Performance: ticket list < 300 ms; message thread < 300 ms.
- SLA job: hourly or on a minute cadence; must not miss breaches (idempotent per ticket).
- RBAC: `support.ticket.*` (exists) + add `support.sla.manage`.
- Field security: internal notes restricted; customer PII masked for non-support roles (D4).
- DPDP: customer PII in tickets — retention policy, erasure respects financial holds.

---

## 12. Reporting & analytics

SLA compliance %, MTTR (mean time to resolve), first-response time, tickets by channel/priority, reopen rate, CSAT trend, queue depth by assignee. Materialised views: `support_sla_compliance`, `support_queue`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `channel_message.received` | in | Support creates/updates ticket (subscriber) |
| `ticket.message.created` | out | Integrations (outbound WhatsApp), Analytics |
| `ticket.sla_breached` | out | Integrations (notify manager), Analytics |
| `ticket.resolved` | out | Marketing (CSAT), Analytics |
| `ticket.escalated` | out | Integrations |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (timers)** | SLA policies + computation + breach job + escalation | SP-01/02 tests; breach fires |
| **M2 (WhatsApp round-trip)** | subscriber on `channel_message.received`; ticket thread via Engage | customer WhatsApp → ticket → reply → WhatsApp (end-to-end) |
| **M3 (lifecycle + CSAT)** | reopen, resolve-with-note, CSAT flow | SP-03/04 tests |
| **M4 (AI triage)** | classifier triage + breach risk | SP-AI tests; human override works |

Order: **M1 → M2 → M3 → M4**.

---

## 15. Test plan

- SLA: priority-1 ticket due at X; breach detected; escalate notified (M1).
- WhatsApp: inbound creates ticket; reply goes out with consent; internal note stays internal (M2).
- Reopen count; resolve requires note (M3).
- Triage suggestion confidence + override (M4).

---

## 16. Migration & rollout

- Import existing tickets/messages from a CSV; backfill `channel=web`.
- Cutover: point Engage webhook at the new subscriber; keep old console read-only for one week.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| SLA timers never enforced | support credibility gone | M1 blocker |
| WhatsApp double-ticket (web + WhatsApp) | duplicate queue | contact-match + dedupe by phone |

---

## 18. Definition of Done

- [ ] M1 SLA policies + breach + escalation
- [ ] M2 WhatsApp round-trip end-to-end
- [ ] M3 lifecycle + CSAT
- [ ] M4 AI triage + risk flag
- [ ] RBAC, audit, outbox, idempotency
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated