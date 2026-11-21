# 15 — Settings (App Settings & Document Sequences)

**Module owner:** Settings (platform)
**Current state:** typed Settings registry, atomic FY-aware numbering engine, gap ledger, offline blocks, encrypted secrets, typed admin UI, Celery sweeps and CI gates are implemented; local verification is green (134 backend tests, 29 frontend tests, 3 Playwright tests, Alembic replay, 100k-row gap-report p95 272.84 ms)
**Date:** 2026-11-21

---

## 1. Purpose & scope

Owns tenant configuration and the **document-numbering** backbone that every numbered document (invoice, PO, GRN, payslip, sale, ticket) relies on. Small surface, outsize blast radius — a numbering bug corrupts every document trail.

**In scope:** app settings (typed key/value), number sequences (per-tenant, per-doc), sequence allocation API.
**Out of scope (v1):** per-module dynamic config UIs (settings are edited via API/admin), feature flags (part of app_settings), email/SMS transport config (module 12), audit of settings changes.

---

## 2. Current state (verified 2026-11-21)

| Asset | State |
|---|---|
| `AppSetting` (`app_settings`) | ✅ scoped, typed, versioned rows with change history and cache version bumps |
| `NumberSequence` (`number_sequences`) | ✅ series configuration with pattern, FY, branch, lock state and channel profile fields |
| Settings/secrets/numbering routers | ✅ typed values, approvals, masked secrets, allocation, preview, status, blocks, voids and gap reports |
| `POST /settings/sequences/{key}/next` | ✅ deprecated with HTTP 410; callers use `document_number`/`numbering.allocate` |
| **Atomic allocation** | ✅ `UPDATE … RETURNING` engine with allocation ledger; 30-way concurrency test green, 100-way/mixed-module acceptance still pending |
| **`core/numbering.py`** | ✅ deleted; no module imports remain; CI lint gate wired |
| **Migration of modules to `number_sequences`** | ✅ finance, sales, procurement, POS, projects and generic CRUD use the shared engine through `document_number`, with runtime flag rollback; commit/audit wiring is covered by tests |
| **Sweeps and reporting** | ✅ Celery worker/beat wiring, manual sweep CLI, SQL-window gap report and CSV exports verified |
| **Alembic replay** | ✅ blank-DB `upgrade head` + double seed replay green; two replay fixes applied |

**Headline:** the count-derived allocator is gone and modules call the shared engine. Remaining explicit gaps are 100-way/mixed-module concurrency, a Hypothesis property test for patterns, and dedicated FY/backdated/closed-period acceptance tests.

---

## 3. Domain model

### 3.1 Target entities

```
number_sequences
  key, prefix, next_number, padding
  + add: pattern (e.g. "INV-{tenant}-{yy}-{seq:05d}"), suffix, last_allocated_at, owner_module,
          per_fiscal_year (bool) — reset when year changes, fiscal_year_start (MM-DD)

app_settings
  tenant_id+key unique, value (JSON), category, description
  + add: value_type [string|number|boolean|json|secret], is_secret (bool), updated_by, updated_at
```

### 3.2 The atomic allocation design (target)
```
-- single SQL statement, row-locked:
UPDATE number_sequences SET next_number = next_number + 1
  WHERE tenant_id = :t AND key = :k
  RETURNING next_number - 1 AS allocated;
```
This is race-free without application locking. `pattern` renders the final document number. Fiscal-year sequences key on `(tenant, key, fy)` and auto-create the next FY row.

`core/numbering.py` is retired: `next_number()` becomes a thin wrapper over `NumberSequenceService.allocate(tenant_id, key)`.

---

## 4. State machines

Sequences have no lifecycle state, but settings support secrets rotation:

### 4.1 Secret setting rotation
```
active   --rotate-->   pending_replacement   (new value stored, old kept until next N uses)
pending  --commit-->   active                (pointers updated, old value nulled)
pending  --rollback--> active                (revert within window)
```

---

## 5. API surface

Current: settings CRUD, sequences CRUD, `POST /settings/sequences/next`.

**Add / change:**

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `POST /settings/sequences/{key}/allocate` | POST | `system.settings.manage` | atomic allocation (replaces `/next`) |
| `POST /settings/sequences/{key}/preview` | POST | `system.settings.manage` | dry-run the next number without consuming |
| `GET /settings/sequences/{key}/status` | GET | `system.settings.manage` | current, allocated this FY, per-module usage |
| `PATCH /settings/secrets/{key}/rotate` | POST | `system.settings.manage` | rotate with pending window |

`core/numbering.py` is deleted only after every module is migrated.

---

## 6. Business rules

- **SE-01** — Sequence allocation is atomic (row-locked UPDATE … RETURNING); no two allocations return the same number.
- **SE-02** — Gaps are acceptable (rollback/abort leaves gaps) — numbering is *unique + sequential*, not gapless.
- **SE-03** — Every module uses `NumberSequence` for human-facing document numbers; `core/numbering.py` is removed.
- **SE-04** — Fiscal-year sequences reset automatically at the configured FY start and are keyed by FY.
- **SE-05** — Secret settings are encrypted at rest, never returned in API responses, masked in audit.
- **SE-06** — Sequence `pattern` tokens are validated (allow-list) — no template injection.
- **SE-07** — Settings changes are audited (who, when, old value).

---

## 7. Workflows (end-to-end)

### 7.1 A document gets its number
1. `SalesOrder` created → `NumberSequenceService.allocate(tenant, "sales_order")`.
2. Row-lock → number N returned → `SO-{fy}-000N` rendered from pattern.
3. On transaction rollback, N is consumed (gap) — fine (SE-02).

### 7.2 Fiscal-year rollover
1. Beat job (or lazy on first allocation) detects FY change.
2. Creates/activates the next FY sequence row (reset to 1), old FY row frozen.
3. Reports keep both FY numbers.

---

## 8. Accounting impact

Numbering is the audit backbone: a document's number must be stable, unique and re-discoverable in the ledger. No journal here; correctness of numbering underpins BR-10 (reports reconstructible from journals) and every reversal reference (module 01 I4).

---

## 9. Benchmarks

| Benchmark | Table stakes | Differentiators | Not competing |
|---|---|---|---|
| **Tally** | Voucher numbering (sometimes gapless) | FY-aware, race-free | Tally's on-screen numbering config |
| **Zoho** | Auto-numbering per module | One engine, all modules | — |
| **SAP B1** | Number ranges with FY periods | Simpler, tenant-scoped | SAP's range-control UI |
| **Odoo** | Sequences per doc, FY | race-free allocation | Odoo's sequence designer |

---

## 10. AI capabilities

None needed — this is infrastructure; keep AI out (the plan's "adequate" principle, and adding AI here would be gold-plating).

---

## 11. Non-functional & security

- **Concurrency:** the allocation SQL is the concurrency primitive; benchmark at 100 concurrent allocations → 100 distinct numbers.
- Performance: allocation < 20 ms (one UPDATE).
- **Security:** secret settings encrypted, masked, rotated with window (SE-05).
- RBAC: `settings.setting.*`, `settings.sequence.*`, plus `system.settings.manage`.
- Audit: every settings change and rotation.

---

## 12. Reporting & analytics

Sequence allocation stats (allocated/FY, gaps, per-module), settings coverage, secrets rotation history.

---

## 13. Integrations

| Event | Direction | Target |
|---|---|---|
| `sequence.allocated` | out (optional, low-volume) | Audit/Analytics |
| (in) module document-creation calls | in | allocate() |

---

## 14. Implementation plan

| Milestone | Scope | Acceptance |
|---|---|---|
| **M1 (atomic allocator)** | row-locked `allocate()`; FY support; pattern rendering; preview | SE-01/02/04/06 tests; 100-concurrent test |
| **M2 (migration off core/numbering.py)** | all modules call the service; `core/numbering.py` deleted | SE-03; no `next_number` import remains |
| **M3 (secrets + audit)** | secret settings, rotation window, masked responses | SE-05/07 tests |

Order: **M1 → M2 (must, unblocks every numbered module) → M3**.

---

## 15. Test plan

- Concurrency: 100 parallel allocations → 100 unique numbers (M1).
- FY rollover resets correctly; reports show both FVs (M1).
- No module imports `core/numbering.py` after M2 (grep test).
- Secret never leaks in API/audit (M3).

**Verified 2026-11-21:** `backend/.venv/bin/python -m pytest -q` → 134 passed; `frontend npm test` → 29 passed; `npm run test:e2e` → 3 passed; `npm run build` green; lint/secret-leak/OpenAPI snapshot gates green; `alembic upgrade head` + double seed replay green; synthetic/live gap-report p95 162.19 ms / 272.84 ms.

---

## 16. Migration & rollout

- Seed `number_sequences` rows for every existing document type with `next_number` set above the current max (dedupe check).
- Roll out M2 per module (feature flag), starting with Finance (most audit-critical).

---

## 17. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Sequence races ship | duplicate document numbers → audit chaos | M1 before any concurrency |
| Count-based numbering stays | gaps/dups on rollback | M2 removal |
| FY reset missed | wrong numbering after Apr | SE-04 + beat job |

---

## 18. Definition of Done

- [x] M1 atomic allocator + FY + pattern implemented; 30-way concurrency test green (100-way/property test pending)
- [x] M2 modules migrated and `core/numbering.py` removed; commit/audit, sweeps and POS blocks verified
- [x] M3 secrets, masking, rotation and audit implemented; global secret-leak scan green
- [x] RBAC, encryption and audit wired; feature-flag rollback verified via `features.numbering.engine`
- [x] Playwright journeys and 390 px smoke green (3 tests)
- [x] Conformance row updated
