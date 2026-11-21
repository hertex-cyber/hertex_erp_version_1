# Team split and release plan — 20 Dec 2026

- **Prepared:** 2026-11-21
- **Deadline:** 2026-12-20
- **Team:** Jishnu, Vidhu, Rishab, Jishnu PR, Vishnu
- **Scope:** ERP web platform plus ERP mobile app

---

## 1. Executive decision

- **Jishnu** remains technical lead and owner of the already-finished platform modules: Identity/Auth, Project Management, Finance/Accounting and Settings/Numbering. Those modules move to **hardening/maintenance mode**, not new feature mode.
- **HR is removed from Jishnu’s ownership** and assigned to **Vidhu** with Jishnu as reviewer only.
- Remaining ERP web modules are split between **Vidhu, Rishab and Jishnu PR**.
- **Vishnu owns the ERP mobile app only**. No web module is assigned to Vishnu. If a mobile app repository exists outside this workspace, it must be linked into CI by 2026-11-25.
- The 2026-12-20 target is a **controlled release milestone**, not “everything in every plan is complete”. The module plans describe roughly 24 build-weeks at four engineers; only about four weeks remain. Therefore each owner has a committed Dec 20 slice and an explicit deferred backlog.

---

## 2. Evidence used for the split

### Authoritative documents

Use these as the source of truth:

- `docs/modules/00-MASTER-ARCHITECTURE.md`
- `docs/modules/99-IMPLEMENTATION-SEQUENCE.md`
- `docs/modules/01A-ACCOUNTING-IMPLEMENTATION-PLAN.md`
- `docs/modules/08a-HR-IMPLEMENTATION-PLAN.md`
- `docs/modules/09a-PROJECT-MANAGEMENT-IMPLEMENTATION-PLAN.md`
- `docs/modules/15A-SETTINGS-IMPLEMENTATION-PLAN.md`
- `docs/modules/16-IDENTITY-AUTH-IMPLEMENTATION-PLAN.md`
- `docs/modules/README.md`
- `docs/PLAN-CONFORMANCE-CHECKLIST.md`
- `docs/runbooks/settings-numbering.md`
- `docs/runbooks/project-management.md`

`docs/HERITEX_ERP_AUDIT/` is an archived July snapshot and must not drive this plan.

### Current verification baseline

- Backend: `134 passed`
- Frontend unit tests: `29 passed`
- Playwright settings journeys: `3 passed`
- Alembic blank-DB replay + double seed: green
- Lint, targeted pyright, secret-leak scan, OpenAPI snapshot: green
- Settings gap report: synthetic p95 `162.19 ms`, live endpoint p95 `272.84 ms`
- CI: `.github/workflows/ci.yml`
- Compose: `docker-compose.yml`, `backend/Dockerfile`

### Current module maturity

| Area | Current maturity | Evidence |
|---|---|---|
| Identity/Auth | Strong; residual hardening remains | `backend/app/modules/identity/router.py`, `backend/alembic/versions/ece7476d64c5_auth_hardening.py` |
| Project Management | Strong; residual E2E/performance remains | `backend/app/modules/projects/router.py`, `backend/app/modules/projects/services.py`, `backend/openapi-project-management.json` |
| Finance/Accounting | Strong core; provider integrations simulated | `backend/app/modules/finance/router.py`, `backend/app/modules/finance/compliance_service.py`, `backend/app/modules/finance/control_service.py` |
| Settings/Numbering | Strong; six named acceptance gaps remain | `backend/app/modules/settings/numbering.py`, `backend/app/modules/settings/service.py`, `frontend/e2e/settings.spec.ts` |
| HR/Payroll | Partial; salary exposure and statutory engine gaps | `backend/app/modules/hr/router.py`, `backend/app/modules/hr/schemas.py`, `docs/modules/08a-HR-IMPLEMENTATION-PLAN.md` |
| Procurement | Partial; approval/GRNI/warehouse gaps | `backend/app/modules/procurement/router.py`, `docs/modules/02-PROCUREMENT.md` |
| Inventory/Warehouse | Partial; ledger exists, advanced operations thin | `backend/app/modules/inventory/router.py`, `backend/app/modules/warehouse/router.py` |
| Sales/POS | Partial; order status/tenant/settlement gaps | `backend/app/modules/sales/router.py`, `backend/app/modules/pos/router.py` |
| CRM/Support/Marketing | CRUD plus a few workflows; automation thin | `backend/app/modules/crm/router.py`, `backend/app/modules/support/router.py`, `backend/app/modules/marketing/router.py` |
| Integrations | WhatsApp real; other providers simulated | `backend/app/modules/integrations/service.py`, `backend/app/modules/integrations/external_adapters.py` |
| Analytics/AI | Dashboard and regex assistant only | `backend/app/modules/analytics/service.py`, `backend/app/modules/ai/service.py` |
| Tally | Ledger XML import only; no UI | `backend/app/modules/finance/tally.py` |
| Documents/PDF | No standalone module found | no `backend/app/modules/documents/`; no PDF dependency in `backend/requirements.txt` |
| Mobile app | No mobile source found in this repository | `frontend/` is React web only |

---

## 3. Ownership map

### Dec 20 committed ownership

| Developer | Primary ownership | Reviewer | Dec 20 commitment |
|---|---|---|---|
| **Jishnu** | Platform/cross-cutting infra; Auth; PM; Finance/Accounting; Settings; Integrations | Peer review from all | Stabilise finished modules, land durable outbox contract, real email/WhatsApp send path, shared PDF/storage seam, CI/release gates |
| **Vidhu** | HR/Payroll (`08`, `08a`) | Jishnu | HR statutory engine, payroll correctness, salary field masking, payroll journal, one HR E2E journey |
| **Rishab** | Procurement (`02`), Inventory (`03`), Warehouse (`04`) | Jishnu | Append-only stock, reservations, GRNI/AP corrections, approval chain, bin stock/picking, one supply-chain E2E journey |
| **Jishnu PR** | Sales (`05`), POS (`06`), CRM (`07`), Support (`10`) | Jishnu | Credit limit/reservation, POS tenant safety + settlement, CRM lead→deal→customer, Support SLA + ticket→project handoff, one revenue E2E journey |
| **Vishnu** | ERP mobile app | Jishnu for API contract | Mobile auth/session, dashboard, PM tasks/timesheets, approvals, HR self-service, CRM/support read flows, offline-number-block awareness |

### Assigned but deferred beyond Dec 20

| Module | Assigned owner | Why deferred | Revisit |
|---|---|---|---|
| Marketing (`11`) | Jishnu PR | Depends on Integrations and CRM conversion | 2026-12-21 onwards |
| GST/e-invoicing depth (`17`) | Jishnu | Local GST records exist; real IRP/portal adapters need credentials | After Dec 20 release |
| Tally migration wizard (`18`) | Rishab | Ledger import exists; voucher/coexistence wizard is larger | After Dec 20 release |
| Documents/PDF (`19`) | Jishnu | Shared service; Dec 20 delivers seam only | January 2027 |
| Analytics (`13`) and AI (`14`) | Jishnu | Needs stable data from newly-hardened modules | January 2027 |
| Asset Management (`20`) | Vidhu | Finance has asset register/depreciation; standalone module cleanup follows HR | January 2027 |
| LMS, Manufacturing | Unassigned | No module docs in `docs/modules`; intentionally out of v1 | After roadmap reapproval |

---

## 4. Developer work packages

### 4.1 Jishnu — platform lead and finished-module hardening

**Does not own anymore:** HR implementation.

**Owns:** Identity/Auth, Project Management, Finance/Accounting, Settings, Integrations, shared platform.

**Dec 20 deliverables:**

1. Close residual Settings gaps from `docs/modules/15A-SETTINGS-IMPLEMENTATION-PLAN.md` §0A:
   - 100-way and mixed-module concurrency test.
   - Hypothesis property test for pattern rendering.
   - FY rollover/backdate/closed-period acceptance suite.
   - Pattern collision pre-check.
   - Feature-flag-driven navigation re-audit.
   - Unique `(tenant_id, number)` index re-audit.
2. Close PM gaps from `docs/modules/09a-PROJECT-MANAGEMENT-IMPLEMENTATION-PLAN.md`:
   - Playwright happy paths.
   - 100k work-item and 5k Gantt p95 benchmarks.
3. Close Auth/Accounting gaps:
   - Encrypt `mfa_secret`.
   - Enforce MFA for admins where configured.
   - Add email transport for reset/security notifications.
   - Origin validation.
   - Document live provider/credential requirements for GST, bank feed and OCR.
4. Land shared platform contracts:
   - Formal ADR-002 decision on durable outbox/event bus.
   - D4 field-policy helper for sensitive fields, needed by HR.
   - Shared PDF/storage seam used by finance, sales, POS and documents.
   - Mobile API contract review with Vishnu.
5. Keep `.github/workflows/ci.yml` green for every merge.

**Exit condition:** no P0/P1 defect in owned modules; migrations replay from blank DB; CI green; runbooks updated.

---

### 4.2 Vidhu — HR and payroll

**Owns:** `docs/modules/08-HR.md`, `docs/modules/08a-HR-IMPLEMENTATION-PLAN.md`.

**Dec 20 deliverables:**

1. **P0 foundation:** effective-dated employee master, salary components, statutory setup, correct tenant scoping, field-level masking for `EmployeeRead.salary` at `backend/app/modules/hr/schemas.py:79`.
2. **P1 statutory engine:** PF, ESI, PT, TDS, gratuity and bonus with effective dates, ceilings and slabs. Use golden-master cases. Any rule without verified gazette/source text stays behind a flag.
3. **P2 payroll correctness:** generate → review → finalize → pay state machine, immutable finalized payslips, Finance journal posting through the shared journal service.
4. **P3/P4 slice:** leave ledger and attendance import adapter; recruitment pipeline CRUD/workflow.
5. One Playwright journey: employee → payroll run → payslip → finance journal link.
6. Runbook update in `docs/runbooks/hr-payroll.md` or extend the existing runbook set.

**Dependencies:**

- Jishnu delivers D4 field-policy helper by 2026-11-25.
- Finance journal API is owned by Jishnu; changes must be requested by 2026-11-27.
- Legal/statutory sign-off for PF/ESI/PT/TDS values is required by 2026-11-27.

**Deferred:** P5 WhatsApp/email notifications and AI governance, P6 analytics, P7 parallel cutover, standalone Asset Management cleanup.

---

### 4.3 Rishab — procurement, inventory and warehouse

**Owns:** `docs/modules/02-PROCUREMENT.md`, `docs/modules/03-INVENTORY.md`, `docs/modules/04-WAREHOUSE.md`.

**Dec 20 deliverables:**

1. **Inventory append-only ledger:**
   - Disable edits/deletes on `StockMove`.
   - Negative-stock guard.
   - Idempotency on stock movements.
   - Reservations for sales/POS use.
2. **Valuation slice:**
   - FIFO / weighted-average selection from Settings.
   - COGS/inventory valuation posting to Finance.
   - Keep method immutable after first stock movement.
3. **Procurement corrections:**
   - GRNI accrual on goods receipt.
   - AP clearing on vendor invoice.
   - Approval chain including documented high-value second approval.
   - Explicit warehouse selection on GRN instead of first-active fallback.
   - Line-level three-way match report.
4. **Warehouse operations:**
   - Bin-level stock.
   - Putaway.
   - Picking with atomic ship confirmation.
   - Cycle count recording.
5. One Playwright journey: PO → approval → GRN → vendor invoice → AP posting.

**Dependencies:**

- Settings numbering is already live; use `document_number()` via shared entry point.
- Finance journal/AP APIs owned by Jishnu; contract freeze by 2026-11-27.
- Sales/POS reservation calls owned by Jishnu PR; agree request shape by 2026-11-28.

**Deferred:** Tally voucher import wizard, advanced barcode scanning hardware integration, manufacturing.

---

### 4.4 Jishnu PR — sales, POS, CRM and support

**Owns:** `docs/modules/05-SALES-ORDERS.md`, `docs/modules/06-POS.md`, `docs/modules/07-CRM.md`, `docs/modules/10-SUPPORT.md`.

**Dec 20 deliverables:**

1. **Sales:**
   - Replace arbitrary `SalesOrderUpdate.status` writes with state-machine transitions.
   - Audit every status change.
   - Credit-limit check before order confirmation.
   - Inventory reservation through Rishab’s reservation API.
   - Returns/credit-note flow using Finance and GST records.
2. **POS:**
   - Fix tenant scoping at checkout and `close_session`.
   - Add checkout idempotency, stock guard, cash variance and settlement journal.
   - Consume Settings offline number blocks for offline sales.
   - Offline queue with idempotent sync.
3. **CRM:**
   - Configurable stages and board guards.
   - Lead → deal → customer conversion.
   - Publish `deal.won` for Sales/customer creation.
   - Explainable lead score fields; no opaque magic score.
4. **Support:**
   - SLA timers, breach and escalation.
   - Keep the existing ticket→project-work handoff.
   - WhatsApp ticket round-trip through Jishnu’s Integrations adapter.
5. One Playwright journey: lead → deal won → sales order → fulfil → invoice; plus a POS checkout smoke at 390 px.

**Dependencies:**

- Inventory reservation contract from Rishab by 2026-11-28.
- Integrations send/consent contract from Jishnu by 2026-11-25.
- GST credit-note record shape from Jishnu by 2026-11-28.

**Deferred:** Marketing segment/send engine, CTWA, Conversions API, advanced AI triage.

---

### 4.5 Vishnu — ERP mobile app

**Owns:** mobile app repository and mobile release.

**Important:** no mobile source exists under this repository. This plan treats the mobile app as a separate repo that consumes the ERP API.

**Dec 20 deliverables:**

1. Mobile auth using the existing refresh-cookie/session contract; no access token stored permanently.
2. Dashboard and KPI cards from `/api/v1/analytics/dashboard` or approved mobile endpoint.
3. Project Management task list, task detail, timesheet entry and approval queue.
4. Finance approval inbox and read-only finance dashboard.
5. HR self-service profile, leave balance and payslip list with masked salary fields.
6. CRM lead/deal read flows and Support ticket creation/read flows.
7. Offline-number-block awareness for POS-oriented mobile checkout, coordinated with Jishnu PR.
8. Mobile API contract document and CI status linked from this plan by 2026-11-25.

**Dependencies:**

- Jishnu freezes mobile auth/approval API contract by 2026-11-25.
- Vidhu freezes HR self-service field policy by 2026-11-27.
- Jishnu PR freezes Sales/POS mobile request shapes by 2026-11-28.

**Not owned:** backend modules, web admin UI, database migrations.

---

## 5. Module-by-module assignment table

| # | Module | Plan / design | Owner | Reviewer | Dec 20 target | Deferred |
|---|---|---|---|---|---|---|
| 16 | Identity/Auth | `16-IDENTITY-AUTH-IMPLEMENTATION-PLAN.md` | Jishnu | All | Residual hardening | P4 SAML/OIDC/SCIM/FIDO2 |
| 09 | Project Management | `09a-PROJECT-MANAGEMENT-IMPLEMENTATION-PLAN.md` | Jishnu | All | E2E + p95 gaps closed | None major |
| 01 | Finance/Accounting | `01A-ACCOUNTING-IMPLEMENTATION-PLAN.md` | Jishnu | All | Live-provider seams documented, auth/settings gaps closed | Real bank/GST portal transports |
| 15 | Settings/Numbering | `15A-SETTINGS-IMPLEMENTATION-PLAN.md` | Jishnu | All | Six named gaps closed | Cross-worker feature-flag nav audit if blocked |
| 08 | HR/Payroll | `08a-HR-IMPLEMENTATION-PLAN.md` | Vidhu | Jishnu | P0–P3 plus golden-master payroll | P4–P7 full rollout |
| 20 | Assets | `20-ASSETS.md` | Vidhu | Jishnu | Payroll/finance asset links only | Standalone module cleanup |
| 02 | Procurement | `02-PROCUREMENT.md` | Rishab | Jishnu | GRNI/AP, approvals, GRN, match report | Tally vendor import |
| 03 | Inventory | `03-INVENTORY.md` | Rishab | Jishnu | Append-only, reservations, valuation slice | Serial/batch depth |
| 04 | Warehouse | `04-WAREHOUSE.md` | Rishab | Jishnu | Bin stock, picking, cycle counts | Hardware barcode integration |
| 18 | Tally migration | `18-TALLY-MIGRATION.md` | Rishab | Jishnu | Keep existing ledger importer stable | Voucher wizard, coexistence |
| 05 | Sales | `05-SALES-ORDERS.md` | Jishnu PR | Jishnu | State machine, credit limit, returns | Storefront (deferred D6) |
| 06 | POS | `06-POS.md` | Jishnu PR | Jishnu | Tenant safety, settlement, offline queue | Advanced refund UX |
| 07 | CRM | `07-CRM.md` | Jishnu PR | Jishnu | Stages, conversion, `deal.won` | ML scoring |
| 10 | Support | `10-SUPPORT.md` | Jishnu PR | Jishnu | SLA timers, WhatsApp round-trip | AI triage depth |
| 11 | Marketing | `11-MARKETING.md` | Jishnu PR | Jishnu | No Dec 20 commitment | Segment/send engine after Dec 20 |
| 12 | Integrations | `12-INTEGRATIONS.md` | Jishnu | All | Signature, real send path, consent, retry | Gateway/CAPI production onboarding |
| 13 | Analytics | `13-ANALYTICS.md` | Jishnu | All | Dashboard stability only | Materialised views/report registry |
| 14 | AI | `14-AI.md` | Jishnu | All | No Dec 20 commitment | LLM/Tier 3 actions in January |
| 17 | GST/e-invoicing | `17-GST-EINVOICING.md` | Jishnu | Jishnu PR | Reconcile doc status; keep local records green | IRP/portal adapters |
| 19 | Documents/PDF | `19-DOCUMENTS.md` | Jishnu | All | Shared storage/PDF seam | Full document archive/legal hold |
| — | Mobile app | no module doc in repo | Vishnu | Jishnu | Auth, dashboard, PM/approvals, HR/CRM/Support read flows | Deep offline modules |
| — | LMS / Manufacturing | no module doc in repo | Unassigned | — | Out of scope | Roadmap reapproval |

---

## 6. Timeline

### Sprint 0 — 2026-11-21 to 2026-11-27: contracts and unblocking

- Freeze ownership per this document.
- Jishnu publishes D4 field-policy helper, Integrations send contract, mobile auth/approval contract and ADR-002 decision.
- Vidhu gets statutory source sign-off checklist approved or flags rules behind a feature flag.
- Rishab and Jishnu PR agree the inventory reservation / sales-POS request contract.
- Vishnu links the mobile repo and CI status.
- All owners create one branch per module and one tracking issue per Dec 20 deliverable.

### Sprint 1 — 2026-11-28 to 2026-12-06: critical path

- Jishnu: Settings/PM/Auth residual gaps and Integrations core.
- Vidhu: HR P0–P2 statutory and payroll correctness.
- Rishab: append-only inventory, GRNI/AP, approval chain.
- Jishnu PR: Sales state machine, POS tenant safety, CRM conversion.
- Vishnu: mobile auth, dashboard, PM task list.

**Gate:** no merge if Alembic head conflicts, CI red, or a module introduces a cross-module breaking change without contract update.

### Sprint 2 — 2026-12-07 to 2026-12-13: workflows and mobile depth

- Jishnu: documents/PDF seam, GST status reconciliation, analytics stability.
- Vidhu: HR leave/attendance and payroll E2E.
- Rishab: warehouse bin/picking, valuation posting.
- Jishnu PR: POS offline queue, Support SLA/WhatsApp, returns/credit note.
- Vishnu: approvals, HR self-service, CRM/support read flows.

**Gate:** each owned module has at least one backend test file and one frontend/E2E happy path or a written waiver approved by Jishnu.

### Sprint 3 — 2026-12-14 to 2026-12-20: hardening and release

- Code freeze for new features: 2026-12-18.
- Only P0/P1 fixes after freeze.
- Every owner runs:
  - backend module tests
  - frontend tests + build
  - Alembic blank-DB replay + double seed
  - lint/typecheck/secret-leak scan
  - one module E2E journey
- Jishnu performs final integration review and signs off release notes.

---

## 7. Cross-module dependency order

Work must follow this order where dependencies exist:

1. **Jishnu:** D4 field policy + durable outbox + Integrations contracts.
2. **Rishab:** append-only stock + reservations.
3. **Vidhu:** HR field masking + statutory engine + payroll journal.
4. **Jishnu PR:** Sales/POS reservation consumption + CRM `deal.won` + Support SLA.
5. **Vishnu:** mobile screens against frozen contracts.
6. **Jishnu:** final accounting/GST/document/analytics integration.

Hard rule: no developer changes another owner’s module directly. Send a contract change request; the owning developer implements or approves the patch.

---

## 8. Shared Definition of Done

A module is “done” for Dec 20 only when all of these are true:

- [ ] One named owner and one reviewer recorded in this document.
- [ ] Alembic upgrade from blank DB and double seed replay pass.
- [ ] Backend tests for the module pass.
- [ ] Frontend tests and production build pass.
- [ ] At least one happy-path E2E journey passes.
- [ ] No secret, plaintext credential or token in code, logs, audit rows or API responses.
- [ ] OpenAPI snapshot has no breaking change, or the change is explicitly approved.
- [ ] Settings numbering is called through `document_number()` / shared allocation entry point; no direct counter writes.
- [ ] Sensitive fields use the D4 field-policy helper.
- [ ] Runbook or module doc status updated to reflect reality.
- [ ] Deferred items are written down, not silently dropped.

---

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Four-week window vs documented 24-week roadmap | Scope failure | Keep the deferred table; Dec 20 is a controlled slice, not full GA |
| Stale July docs contradict November implementation docs | Wrong status decisions | Treat implementation plans and November addenda as authoritative; `docs/HERITEX_ERP_AUDIT/` is archive only |
| HR statutory rules unverified | Legal/payroll errors | Vidhu uses golden masters; unverified rules stay feature-flagged pending sign-off |
| Shared migration conflicts | Broken replay | One migration head owner per sprint; Jishnu approves every new revision |
| D4 field policy delayed | HR salary exposure and mobile masking blocked | Jishnu delivers helper by 2026-11-25 |
| External provider credentials unavailable | GST/bank/payment/OCR stay simulated | Keep adapters behind explicit simulated status; do not claim production integration |
| Weak E2E coverage outside Settings | Regressions slip through | Each owner adds one module journey by 2026-12-18 |
| Mobile repo outside this repo | Contract drift | Vishnu links mobile CI and API contract by 2026-11-25 |
| Redis 6 local worker incompatibility | Local Celery validation fails | Use Compose/CI Redis 7; documented in `docs/runbooks/settings-numbering.md` |

---

## 10. Immediate next actions

| Owner | Action | Due |
|---|---|---|
| Jishnu | Publish D4 helper contract, Integrations contract, ADR-002 decision and mobile API contract | 2026-11-25 |
| Vidhu | Confirm HR statutory source checklist and create HR P0/P1/P2 tasks | 2026-11-25 |
| Rishab | Publish reservation and valuation request/response contract | 2026-11-25 |
| Jishnu PR | Publish Sales/POS state-machine and mobile request contract | 2026-11-25 |
| Vishnu | Link mobile repo, CI status and API contract location | 2026-11-25 |
| All | Create module branches/issues from this table and update status in standup | 2026-11-25 |
| Jishnu | First integration gate: Alembic head + CI green | 2026-11-27 |
