# 12 — Integrations (Engage / WhatsApp / Meta / Payments)

**Module owner:** Integrations
**Rank:** the transport layer behind `Best-Product-Plan §2.2` (WhatsApp as a *transactional* channel) — if this is weak, the whole conversational product story is weak
**Current state:** webhook + channel-message store exist; **no real outbound send, no signature verification, no adapter abstraction, no consent enforcement**
**Date:** 2026-07-17

---

## 1. Purpose & scope

The single gateway between Hertex and the outside world's channels: WhatsApp (Cloud API), future Instagram/Messenger, voice (Engage), payments (Razorpay/PayU), Meta (Ads/CAPI, Commerce catalog). Every other module talks to the world **only through this module** — never by importing a vendor SDK. That is the anti-fragmentation rule (Technical Plan §4, §7; MA §12 D2).

**In scope:** channel abstraction (`ChannelMessage`, adapters), WhatsApp webhook (verify + inbound), outbound send with consent, template/flow management, Meta Conversions API + Catalog sync, payment gateway integration.
**Out of scope (v1):** voice agent runtime (Engage's Pipecap/Gemini — separate service), Instagram/Messenger adapters (v1.5, but the abstraction must make them thin), OAuth flows beyond Meta.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `ChannelMessage` (`channel_messages`) | ✅ table with `channel, direction, external_id, contact_name, contact_phone, module, related_id, payload, status, sent_at` |
| Webhook GET (verify token) | ✅ `router.py:31-41` |
| Webhook POST (inbound) | ✅ `router.py:42-66` — parses Meta payload → `ChannelMessage(status=received)`, publishes `channel_message.received` |
| `POST /send` | ✅ `router.py:103` — creates `ChannelMessage(status=queued)` via `engage_bridge.send_message`, publishes `channel_message.queued` |
| **Real outbound send** | ❌ **nothing calls the Meta Graph API** — `send_message` only inserts a queued row. No HTTP client, no token use |
| **Webhook signature verification** | ❌ **no `X-Hub-Signature-256` check** despite `META_APP_SECRET` in config |
| **Adapter abstraction** | ❌ no `ChannelAdapter`/`WhatsAppCloudAdapter` interface (plan's `ChannelAdapter` never materialised) |
| **Consent enforcement** | ❌ nothing reads `whatsapp_opt_in` before outbound |
| **Template/flow management** | ❌ no template CRUD, no Meta approval tracking, no Flows |
| **Conversions API / Catalog sync** | ❌ |
| **Payment gateway** | ❌ Razorpay keys in config, no integration code |

**Headline:** the *shape* of the channel is right (webhook + message store + event), but **nothing is connected**. Outbound messages are rows that never leave the server; inbound messages aren't signature-verified, so a forged webhook can inject records. This module is the single biggest gap against the product's #2 differentiator.

---

## 3. Domain model

### 3.1 Target entities

```
channel_messages
  + add: status [queued|sending|sent|delivered|read|failed|received], provider_message_id,
          retry_count, last_error, template_id, media_url, expires_at, consent_check (bool),
          contact_id (link to CRM Contact), tenant opt-out state

NEW:
channel_adapters_registry   name, channel_type [whatsapp|instagram|messenger], config (encrypted JSON),
                            is_active, last_health_check, webhook_secret_rotated_at
channel_templates           name, channel, template_type, body, params (JSON), media_url,
                            meta_template_id, category, language, approval_status [draft|pending|approved|rejected],
                            rejection_reason, submitted_at
channel_flows               name, flow_type [survey|order|leave|feedback], meta_flow_id,
                            form_schema (JSON), status, published_at
channel_payments            gateway [razorpay|payu], order_id, amount, currency, status,
                            gateway_reference, payload, captured_at, linked_document_type/id
meta_capi_events            (see module 11 — shared)
```

### 3.2 Adapter interface (plan-mandated)
```
interface ChannelAdapter:
    verify_webhook(params) -> bool
    parse_webhook(payload) -> list[ChannelMessage]
    send(message) -> provider_message_id     # real HTTP call
    get_status(provider_message_id) -> status
WhatsAppCloudAdapter(ChannelAdapter):   # only concrete impl in v1
    endpoint = https://graph.facebook.com/v21.0/{phone_number_id}/messages
```
Every module calls `engage_bridge.send_message(...)` (already exists in `integrations/service.py`) and never touches the adapter directly.

---

## 4. State machines

### 4.1 Outbound message
```
draft  --enqueue-->  queued        guard: consent verified, template approved (if template)
queued --send-->     sending       (worker calls adapter)
sending --ack-->     sent          (provider accepted)
sent   --delivery--> delivered
sent   --failed-->   failed        guard: retries < N → requeue; else terminal
delivered --read-->  read          (optional)
```
### 4.2 Template
```
draft  --submit-->  pending   (submitted to Meta)
pending --approve--> approved
pending --reject-->  rejected  guard: reason recorded
rejected --resubmit--> pending
```

---

## 5. API surface

Current: `GET/POST /whatsapp/webhook`, `GET /messages`, `POST /send`.

**Add:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `POST /integrations/templates` | POST | `integrations.channel.manage` | create + submit template |
| `POST /integrations/templates/{id}/resubmit` | POST | `integrations.channel.manage` | resubmit rejected |
| `POST /integrations/flows` | POST | `integrations.channel.manage` | WhatsApp Flow CRUD |
| `POST /integrations/payments/razorpay` | POST | `system.integration.manage` | payment intent/create order |
| `POST /integrations/payments/{id}/verify` | POST | `system.integration.manage` | capture/verify (webhook-driven) |
| `POST /integrations/meta/capi` | POST | `system.integration.manage` | server-side event |
| `POST /integrations/meta/catalog-sync` | POST | `system.integration.manage` | product → Meta Catalog |
| `POST /integrations/adapters/{name}/health` | POST | `system.integration.manage` | health check |

---

## 6. Business rules

- **IN-01** — **Webhook signature is verified** (`X-Hub-Signature-256` over raw body with `META_APP_SECRET`) before any row is written. *(Missing — must be #1 fix.)*
- **IN-02** — Outbound is impossible without consent: `Contact.whatsapp_opt_in=true` (or a verified opt-in) or the message fails with `CONSENT_REQUIRED`.
- **IN-03** — Business (template) messages require an approved template; only utility/service messages may use free text.
- **IN-04** — All outbound goes through `engage_bridge.send_message`; modules never import the Meta SDK (anti-fragmentation).
- **IN-05** — Retry with backoff; terminal failure writes `last_error` for diagnosis.
- **IN-06** — Inbound messages are idempotent by `external_id` (Meta may redeliver).
- **IN-07** — Sensitive config (tokens, secrets) is encrypted at rest; keys live in `channel_adapters_registry`, not code.
- **IN-08** — Payment webhooks are signature-verified; `linked_document_type/id` ties the payment to the invoice/order.

---

## 7. Workflows (end-to-end)

### 7.1 Inbound WhatsApp → business action
1. Meta POSTs → `X-Hub-Signature-256` verified (IN-01).
2. Payload normalised → `ChannelMessage(received)` (idempotent by `external_id`).
3. `channel_message.received` published → CRM (lead), Support (ticket), Sales (order status query).
4. Any module reply routes back through `engage_bridge` with consent + approved template.

### 7.2 Outbound transactional (invoice, order, leave)
1. Module calls `engage_bridge.send_message(contact, template, module_context)`.
2. Consent checked (IN-02); template resolved + approved (IN-03).
3. Worker calls adapter → provider ack → status transitions → delivery/read events.

### 7.3 Payment (Razorpay/PayU)
1. Invoice → create payment order (gateway).
2. Customer pays (UPI/card/WhatsApp payment link) → gateway webhook verified (IN-08).
3. Payment recorded → Finance posts AR settlement → `invoice.paid` → CRM/Analytics.

---

## 8. Accounting impact

Indirect — payment capture is the trigger for `invoice.paid` (module 01). The gateway reconciliation report must tie payment captures to Finance payments.

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Meta API directly** | webhook, send, templates | Abstra a single gateway so Instagram/Messenger are thin add-ons | — |
| **BSPs (Ozonetel/Wati/Gupshup)** | template handling, approval, routing | We own the channel + data; no per-message BSP fees | BSP support/SLA, pre-approved templates |
| **Zoho (Zoho SalesIQ/Conversations)** | WhatsApp via BSP, flows | Transactional (order/pay in-chat) | Zoho's conversation analytics |
| **SAP (CPI)/Odoo (WhatsApp)** | Odoo's WhatsApp bridge | Same-DB transactional context | Odoo/partner connectors' breadth |

**Differentiator (plan §2.2):** WhatsApp must transact — check order, resolve ticket, place repeat order — not just notify. That requires the outbound path (IN-01..03) and payment-in-chat (IN-08).

---

## 10. AI capabilities

| Tier | Capability | Decision it changes | Guardrail |
|---|---|---|---|
| 1 | **Inbound intent routing** (order-status vs support vs sales) | routes to the right module | classifier with confidence + fallback to human |
| 3 | **Auto-reply drafts** (order status, simple FAQ) for agent approval | agent sends faster | agent approves every send (A3) |
| 3 | **Reorder flow in-chat** (WhatsApp Flows → order → payment) | customer completes order in WhatsApp | consent + approval chain intact |

---

## 11. Non-functional & security

- **Security (critical):** signature verification on webhooks; token encryption at rest; webhook replay protection; rate-limit inbound.
- **Reliability:** outbox + retry worker; exactly-once inbound by `external_id`; dead-letter on repeated failure.
- Performance: inbound handling p95 < 200 ms; outbound enqueue < 100 ms (send happens in worker).
- RBAC: `integrations.channel.manage` (exists) + add `system.integration.manage` for payments/catalog.
- DPDP: WhatsApp consent is a Meta compliance requirement; store consent provenance (contact, source, timestamp).
- Audit: every send/receive/template approval/payment.

---

## 12. Reporting & analytics

Channel message volume, delivery/read rates, failure + retry rate, template approval status, payment capture vs Finance reconciliation, per-channel cost. Materialised views: `integrations_message_metrics`.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `channel_message.received` | out | CRM, Support, Sales, Analytics |
| `channel_message.queued` | out | Analytics |
| `channel_message.delivered/read/failed` | out | Analytics, Marketing (module 11) |
| `payment.captured` | out | Finance (`invoice.paid`), CRM, Analytics |
| `order.completed` | in | Meta Conversions API |

External: Meta Graph API (WhatsApp Cloud, Catalog, CAPI), Razorpay/PayU webhooks, (v1.5) Instagram/Messenger.

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (secure inbound)** | signature verification; idempotent inbound; encrypted config | IN-01/06 tests; forged payload rejected |
| **M2 (real outbound)** | adapter interface + WhatsAppCloudAdapter; Celery worker; consent gate; retry | IN-02..05; a real sandbox send succeeds |
| **M3 (templates + flows)** | template CRUD + Meta approval tracking; first WhatsApp Flow (feedback survey) | IN-03 tests; approved template send |
| **M4 (payments)** | Razorpay/PayU create + verify + capture → Finance | IN-08 tests; payment lands as `invoice.paid` |
| **M5 (Meta business)** | CAPI events + Catalog sync | events deduped, visible in Ads Manager |

Order: **M1 (must) → M2 (must) → M3 → M4 → M5**. M1+M2 are the release blockers for the entire conversational product.

---

## 15. Test plan

- Signature: wrong secret → 403, no row written (M1).
- Idempotent inbound: redelivered `external_id` doesn't duplicate (M1).
- Consent: opt-out contact → send returns `CONSENT_REQUIRED` (M2).
- Retry: transient failure retries, permanent fails after N (M2).
- Template: rejected can't send (M3).
- Payment: webhook replay blocked; capture → `invoice.paid` (M4).

---

## 16. Migration & rollout

- Point existing WhatsApp Business account at the new webhook (test number first — Meta sandbox).
- Enable one channel (WhatsApp) before adding Instagram/Messenger.
- Pilot on 1 client with opt-in-verified contacts before scaling.

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| No signature check ships | forged messages, legal exposure | M1 blocker |
| Outbound stays fake (queued rows only) | entire product story false | M2 blocker |
| Consent not enforced | Meta ban + DPDP | IN-02 hard gate |
| Template rejected at launch | campaign stalls | approval tracking + fallback |

---

## 18. Definition of Done

- [ ] M1 signature-verified, idempotent inbound
- [ ] M2 real outbound via adapter + consent + retry (sandbox send verified)
- [ ] M3 templates + approval tracking + first Flow
- [ ] M4 payments captured → Finance
- [ ] M5 CAPI + Catalog sync
- [ ] RBAC, encryption, audit, outbox
- [ ] Playwright happy path + demo screen
- [ ] Conformance row updated