# 99 — Implementation Sequence & Master Roadmap

**Purpose:** the single, ordered build plan that sequences all 20 modules (+ master architecture) into shippable milestones. Ties every module doc's `M1..M5` into one dependency-correct roadmap and one Definition of Done.

**Owner:** tech lead
**Date:** 2026-07-17
**Inputs:** `00-MASTER-ARCHITECTURE.md` (invariants, events, template) and modules `01`–`20`.

---

## 1. Reality check — where the codebase is right now

| Dimension | Current state (verified 2026-07-17) |
|---|---|
| Backend framework | ✅ FastAPI 0.128 + SQLAlchemy 2.0 async + asyncpg + Alembic + Pydantic v2 |
| Modules | ✅ 18 routers, 52 tables, CRUD scaffolding in place |
| Migrations | ❌ **0** — schema created ad-hoc; no Alembic history |
| Tests | ❌ **0** — no unit/integration/e2e |
| Workers | ❌ **0** — Celery/Redis configured but no tasks |
| Event subscribers | ❌ **0** — in-process bus with no consumers |
| Frontend | ❌ **0** |
| AI (real) | ❌ regex FAQ only; no LLM, no ML |
| GST returns / e-invoice | ❌ cannot produce a return |
| Tally | ❌ nothing |
| Documents / PDF | ❌ none |
| Assets | ❌ none |

**The honest headline:** this is a **well-shaped skeleton** — good module boundaries, RBAC catalog, tenant scoping, async stack — but **nothing is production-ready**. Zero migrations, zero tests, zero workers, zero frontend means it has never run end-to-end. The roadmap below builds the runnable spine first, then breadth.

---

## 2. Sequencing principles

1. **Spine before breadth.** Foundations (migrations, tests, workers, events, sequences, PDF) unblock *every* module; doing them first makes each later module cheaper.
2. **Legal/audit-critical first.** GST split, numbering atomicity and audit completeness must exist before any live invoice — getting them wrong after go-live is a rewrite.
3. **Reconciliation gates.** Finance/Tally/Inventory can't go live until balances reconcile to zero (module 18 TL-08, module 01 BR-10).
4. **Every milestone is demoable.** Each M ends with a working screen or a passing check — no "foundation only, nothing visible" stretches.
5. **AI acts only after data is trustworthy.** Tier 1 models need clean data; Tier 3 actions need the workflow engine + approvals. Ship Tier 2 (read-only Ask) early, Tier 3 last.

---

## 3. The master roadmap (phases × milestones)

### Phase 0 — Foundation (must exist before anything ships) — ~3 weeks
| # | Deliverable | Module refs | Acceptance |
|---|---|---|---|
| 0.1 | **Alembic baseline** — generated from current models, `alembic upgrade head` on empty DB produces all 52 tables | all | CI runs migration on blank Postgres |
| 0.2 | **Test harness** — pytest + async fixtures, factory-boy, tenant test clients | all | ≥1 test/module harness smoke |
| 0.3 | **Celery worker + beat** running one no-op task | 14, 03 | worker starts in `docker compose up` |
| 0.4 | **Event bus subscribers** — at least one real subscriber per key event (`stock.low`, `invoice.posted`) | 00 §9 | event fired in test reaches subscriber |
| 0.5 | **Atomic number sequences** — module 15 M1/M2 (retire `core/numbering.py`) | 15 | concurrency test 100→100 |
| 0.6 | **Documents/PDF base** — module 19 M1/M2 (invoice PDF at minimum) | 19 | invoice PDF renders with GST fields |
| 0.7 | **CI pipeline** — lint + test + migration check + docker build | — | green on every PR |

**Gate:** a new clone can `docker compose up`, migrate, run tests, start workers, and render an invoice PDF. Nothing else starts until this is green.

### Phase 1 — Correctness spine (financial + compliance integrity) — ~4 weeks
| # | Deliverable | Module refs | Rationale |
|---|---|---|---|
| 1.1 | **GST tax model** (split, place of supply, rate master, GSTIN validation) — module 17 M1 | 17 | cannot invoice legally without it |
| 1.2 | **Numbering on every doc** (module 15 M2 complete) | 15 | audit integrity |
| 1.3 | **Finance invariants** — no double-count of inventory, GRNI accrual, journal-only postings — module 01/02 fixes | 01, 02 | ledger correctness |
| 1.4 | **Audit completeness** — every state change audited — module 16 M3 | 16 | fraud detection baseline |
| 1.5 | **Field-level RBAC** — D4 close — module 16 M1 | 16 | salary/PAN protection |
| 1.6 | **Append-only stock moves** — no generic CRUD on ledger — module 03 fix | 03 | I2 invariant |

**Gate:** GST-compliant invoice + correct journal + audited, with zero double-count and enforced append-only ledger. This is the point where we can *safely* run a pilot on real money.

### Phase 2 — Operational completeness (order-to-cash, procure-to-pay) — ~5 weeks
| # | Deliverable | Module refs |
|---|---|---|
| 2.1 | Inventory valuation + GRNI clean (module 03 M1–M3, module 02 M2) | 03, 02 |
| 2.2 | Sales orders: reservations, fulfilment, returns, credit limits (module 05 M1–M3) | 05 |
| 2.3 | Warehouse: bin stock, picking, cycle counts (module 04 M1–M3) | 04 |
| 2.4 | POS: offline queue, settlement journals, stock check (module 06 M1–M3) | 06 |
| 2.5 | Procurement: approval chains, line-level 3-way match, `approval_limit` enforced (module 02 M3–M4) | 02 |

**Gate:** a full order → reserve → pick → invoice → payment and a PO → GRN → invoice → match run end-to-end with correct stock and journals.

### Phase 3 — Compliance depth + comms/marketing — ~5 weeks
| # | Deliverable | Module refs |
|---|---|---|
| 3.1 | E-invoicing (IRP IRN/QR), e-way bill, GSTR-1/3B/2B + ITC (module 17 M3–M5) | 17 |
| 3.2 | Real outbound WhatsApp/email send + webhook signature verification (module 12 M1–M2) | 12 |
| 3.3 | Support: SLA, WhatsApp→ticket, CSAT (module 10 M1–M3) | 10 |
| 3.4 | Marketing: segment engine, send executor, CTWA attribution (module 11 M1–M3) | 11 |
| 3.5 | CRM: lead scoring wired, `deal.won` published (module 07 fixes) | 07 |

**Gate:** statutory filing artefacts produce valid JSON; inbound/outbound messaging is verified and safe (signature-checked); marketing attribution works.

### Phase 4 — People, projects, analytics — ~4 weeks
| # | Deliverable | Module refs |
|---|---|---|
| 4.1 | HR statutory engine (PF/ESI/TDS correct) + payroll journal (module 08 fixes) | 08 |
| 4.2 | Projects: time, billing, profitability (module 09 M1–M3) | 09 |
| 4.3 | Analytics: materialised views, report registry, exports, AI digest (module 13 M1–M4) | 13 |
| 4.4 | Documents/Assets: full PDF suite + asset register + depreciation (module 19 M3–M4, module 20 M1–M3) | 19, 20 |

**Gate:** payroll run produces correct statutory deductions and posts a journal; project margins accurate; dashboards load from views.

### Phase 5 — AI + Tally (the differentiators) — ~5 weeks
| # | Deliverable | Module refs |
|---|---|---|
| 5.1 | AI Platform Tier 2 (real LLM Ask, safe tool-calling) — module 14 M1 | 14 |
| 5.2 | AI Tier 1 (lead scorer, reorder forecast) — module 14 M2–M3 | 14 |
| 5.3 | Tally coexistence + migration (module 18 M1–M5) | 18 |
| 5.4 | AI Tier 3 (action layer, draft_po approve→execute) — module 14 M4 | 14 |
| 5.5 | Assets disposal + ITC reversal + dual register (module 20 M4–M5) | 20 |

**Gate:** AI changes a decision (buyer approves a pre-filled PO); a real Tally company migrates to zero difference.

### Phase 6 — Hardening & GA — ~3 weeks
| # | Deliverable |
|---|---|
| 6.1 | Performance pass (query plans, N+1 elimination, index audit) |
| 6.2 | Security pass (rate limiting, penetration smoke, secrets rotation) |
| 6.3 | DPDP compliance (erasure, consent, retention jobs) |
| 6.4 | Observability (structured logs, traces, health checks, alerting) |
| 6.5 | Docs convergence (conformance checklist 100% rows statused) |

**Gate:** GA checklist green; pilot clients live.

---

## 4. Dependency graph (what blocks what)

```
Phase 0 ─┬─> 15 sequences ─┬─> every numbered module
         ├─> 19 PDF ───────┼─> 17 e-invoice print, 12 send, 10 tickets
         ├─> events/workers─┼─> 03, 11, 14 (batch), 18 (sync)
         └─> tests ────────┴─> (all — enables verification)

1.1 GST ─> 05 sales invoicing, 06 POS, 17 returns, 01 finance
1.6 append-only ─> 03 valuation ─> 04 warehouse ─> 05 fulfilment
02 GRNI ─> 01 triple reconciliation (order/stock/ledger)
16 field-RBAC ─> 08 HR payroll exposure (confidential data)
13 analytics ─> after modules produce stable data
14 AI Tier-3 ─> after 02 approval chains + workflow engine exist
18 Tally ─> after 01 COA + 15 sequences stable
```

**Critical path:** Phase 0 → GST (1.1) → append-only stock (1.6) → valuation (2.1) → fulfilment (2.2) → returns/credit (2.2) → payroll (4.1) → AI/Tally (5).

---

## 5. What ships *first* to a real user (MVP slice)

A credible first pilot does **not** need all 20 modules. The thinnest slice that lets a real SMB run a day:

1. Login + RBAC (module 16, exists + field RBAC).
2. GST-correct invoice (modules 17 M1, 01).
3. Stock + basic purchase/sale (modules 02, 03 minimal).
4. Number sequence atomicity (15 M1).
5. Invoice PDF (19 M2).
6. Ask Hertex read-only (14 M1 fallback is fine initially).

That is **Phase 0 + a slice of Phase 1/2**. Everything else (POS, projects, marketing, assets, AI Tier 3, Tally) extends this slice; none of them are prerequisites for a first paying customer.

---

## 6. Sizing (rough, no calendar dates)

| Phase | Focus | Relative effort |
|---|---|---|
| 0 | Foundation | large (unblocks all) |
| 1 | Correctness spine | large |
| 2 | Order-to-cash/procure-to-pay | large |
| 3 | Compliance + comms | medium |
| 4 | People/projects/analytics | medium |
| 5 | AI + Tally (moat) | large |
| 6 | Hardening/GA | medium |

Total ≈ **24 build-weeks** for the full set (~4 engineers); a demoable MVP slice ≈ Phase 0 + parts of 1/2 ≈ 8 weeks.

---

## 7. Cross-module Definition of Done (applies to every module)

A module is *done* only when **all** hold (per master §11):

- [ ] All `BR/PR/IV/SO/PS/CR/HR/GT/TL/DC/AS/PJ/SP/MK/IN/AN/ID/SE/AI` rules implemented
- [ ] Migrations exist; `alembic upgrade head` clean
- [ ] Unit + integration tests (happy + guard + tenant-isolation)
- [ ] RBAC codes registered in `permissions_catalog.py`
- [ ] Audit writes on every state change
- [ ] Domain events published/subscribed (outbox where outbound)
- [ ] No hardcoded ₹/state/tax; settings-driven
- [ ] Reports + AI capability (if Tier ≥1) shipped
- [ ] Playwright happy path passes
- [ ] No breaking of invariants I1–I6
- [ ] Conformance checklist row statused

---

## 8. Open decisions carried forward

From master §12: D2 (workflow engine — build vs adopt), D3 (offline POS sync protocol), D6 (DPDP data-residency/retention fine print), D7 (fair usage / plan gating). **D1** (POS/SalesOrder merge) is **closed** — POS wraps `SalesOrder(channel="pos")`; no merge. **D2** is now **resolved (proposed ADR)** — build a minimal in-house engine on Celery+Postgres, no sidecar service; see `docs/adr/ADR-002-workflow-engine.md`. Pending formal accept, it unblocks Phase 0.3/0.4 and Phase 1.6.

Recommend accepting **ADR-002 (D2)** before Phase 1.6 (append-only stock touches the workflow engine) and closing **D7** before any hosted pilot.

---

## 9. The one-line summary

**Build the runnable spine (Phase 0) → make money-and-tax correct (Phase 1) → make operations complete (Phase 2–4) → make it smart and Tally-compatible (Phase 5) → harden (Phase 6).** Nothing in the roadmap is a rewrite; every phase extends a module that already has a doc specifying exactly what to change and how to prove it.