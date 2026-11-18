# Modules — Design & Implementation Docs

Deep, code-verified module planning for **hertex-erp**. Each doc follows the 18-section master template (purpose, current state, domain model, state machines, API, business rules, workflows, accounting, benchmarks, AI, NFR/security, reporting, integrations, implementation plan, test plan, migration, risks, Definition of Done).

**Grounding:** every "current state" claim is cited to real code (`file:line`). Where a fact could not be verified, it is marked `UNVERIFIED`. See `../PLAN-CONFORMANCE-CHECKLIST.md` for the requirement-by-requirement status.

---

## Read in this order

| # | Doc | Focus | Status | Lines |
|---|---|---|---|---|
| 00 | [MASTER-ARCHITECTURE](00-MASTER-ARCHITECTURE.md) | Invariants I1–I6, 52-table ownership, state-machine standard, 13-event catalogue, benchmark framework, 18-section template, DoD, AI tiers A1–A5, decisions D1–D7 | ✅ | 302 |
| 01 | [FINANCE](01-FINANCE.md) | GL, journals, AR/AP, reconciliations; double-count & GRNI findings | ✅ | 328 |
| 01A | [ACCOUNTING-IMPLEMENTATION-PLAN](01A-ACCOUNTING-IMPLEMENTATION-PLAN.md) | End-to-end accounting blueprint: gap closure, FE/BE design, controls, integrations, and rollout | ✅ | — |
| 02 | [PROCUREMENT](02-PROCUREMENT.md) | PO, GRN, 3-way match, approval chains, GRNI gap | ✅ | 283 |
| 03 | [INVENTORY](03-INVENTORY.md) | StockMove-as-ledger, append-only, valuation | ✅ | 296 |
| 04 | [WAREHOUSE](04-WAREHOUSE.md) | Bin-level stock, picking, cycle counts | ✅ | 245 |
| 05 | [SALES-ORDERS](05-SALES-ORDERS.md) | Quotes, reservations, returns, credit limits | ✅ | 256 |
| 06 | [POS](06-POS.md) | Offline queue, settlement journals, stock checks | ✅ | 252 |
| 07 | [CRM](07-CRM.md) | Pipeline, lead scoring, `deal.won` | ✅ | 267 |
| 08 | [HR](08-HR.md) | Statutory PF/ESI/TDS engine, payroll journal | ✅ | 288 |
| 08a | [HR IMPLEMENTATION PLAN](08a-HR-IMPLEMENTATION-PLAN.md) | Zoho/SAP-style HR build: statutory payroll, ESSL attendance, leave, recruitment pipelines, Meta/WhatsApp/email, AI governance | 🟡 planned | P0–P7 |
| 09 | [PROJECTS](09-PROJECTS.md) | Time entries, billing, milestones, profitability | ✅ | — |
| 09a | [PROJECT MANAGEMENT IMPLEMENTATION PLAN](09a-PROJECT-MANAGEMENT-IMPLEMENTATION-PLAN.md) | Jira-class work management: workflows, boards/backlogs, Gantt, HR-aware capacity, timesheets, billing, risks, automation, and AI | 🟢 implemented / complete | P0–P9 |
| 10 | [SUPPORT](10-SUPPORT.md) | SLA policies, WhatsApp→ticket, CSAT, AI triage | ✅ | — |
| 11 | [MARKETING](11-MARKETING.md) | Segment engine, send executor, CTWA, Conversions API | ✅ | — |
| 12 | [INTEGRATIONS](12-INTEGRATIONS.md) | Adapter abstraction, signature verification, outbound send, payments, Meta | ✅ | — |
| 13 | [ANALYTICS](13-ANALYTICS.md) | Materialised views, report registry, export, AI digest | ✅ | — |
| 14 | [AI](14-AI.md) | Ask Hertex LLM, Tier 1 models, Tier 3 action layer | ✅ | — |
| 15 | [SETTINGS](15-SETTINGS.md) | App settings + atomic document numbering (FY-aware) | ✅ | — |
| 16 | [IDENTITY](16-IDENTITY.md) | Auth, RBAC, field-level security (D4), audit | ✅ | — |
| 16a | [AUTH IMPLEMENTATION PLAN](16-IDENTITY-AUTH-IMPLEMENTATION-PLAN.md) | Zoho/SAP-style auth hardening: password policy, MFA, session rotation, recovery, security headers | 🟢 implemented | P4 deferred |
| 17 | [GST-EINVOICING](17-GST-EINVOICING.md) | GST 2.0 splits, IRN/QR, e-way bill, returns, ITC | ✅ | — |
| 18 | [TALLY-MIGRATION](18-TALLY-MIGRATION.md) | Tally XML integration, migration + coexistence | ✅ | — |
| 19 | [DOCUMENTS](19-DOCUMENTS.md) | Attachments, PDF generation, storage, legal hold | ✅ | — |
| 20 | [ASSETS](20-ASSETS.md) | Fixed assets, depreciation, disposal, ITC reversal | ✅ | — |
| 99 | [IMPLEMENTATION-SEQUENCE](99-IMPLEMENTATION-SEQUENCE.md) | Ordered master roadmap (phases 0–6), dependency graph, MVP slice | ✅ | — |

**24 docs total** (00–20 + 08a + 09a + 99 index/sequence).

---

## The five cross-cutting themes

1. **Correctness spine first** — migrations, tests, workers, events, atomic numbering, GST split. Nothing ships before these (see `99` Phase 0/1).
2. **Append-only ledgers** — StockMove and JournalEntry are immutable; corrections are reversals (invariant I2/I4).
3. **One source of truth** — every module writes only its own tables; cross-module effects go through events + the journal service (I1/I3).
4. **Statutory India-native** — GST 2.0 (0/5/18/40 from 22 Sep 2025), e-invoicing ≥₹5 Cr, 30-day IRP window for ≥₹10 Cr, e-way bill >₹50,000, TDS/PF/ESI.
5. **AI that acts, not charts** — Tier 2 read-only first, Tier 3 through approvals and audit only (A1–A5).

---

## Generated 2026-07-17. Based on verified code inspection + targeted research (GST 2.0 slabs, Tally XML envelope, Odoo 2025 valuation refactor, GRNI). Only SAP B1 table-level detail remains `UNVERIFIED`, and it is not load-bearing.