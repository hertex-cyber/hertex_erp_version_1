# 15 — Settings (App Settings & Document Sequences)

**Module owner:** Settings (platform)
**Current state:** `AppSetting` + `NumberSequence` tables with CRUD and a `next_sequence_number` endpoint; **sequence allocation is not atomic under concurrency**
**Date:** 2026-07-17

---

## 1. Purpose & scope

Owns tenant configuration and the **document-numbering** backbone that every numbered document (invoice, PO, GRN, payslip, sale, ticket) relies on. Small surface, outsize blast radius — a numbering bug corrupts every document trail.

**In scope:** app settings (typed key/value), number sequences (per-tenant, per-doc), sequence allocation API.
**Out of scope (v1):** per-module dynamic config UIs (settings are edited via API/admin), feature flags (part of app_settings), email/SMS transport config (module 12), audit of settings changes.

---

## 2. Current state (verified 2026-07-17)

| Asset | State |
|---|---|
| `AppSetting` (`app_settings`) | ✅ table — `tenant_id + key` unique, `value` JSON, `category`, `description` |
| `NumberSequence` (`number_sequences`) | ✅ table — `tenant_id + key` unique, `prefix`, `next_number`, `padding` |
| CRUD routers | ✅ `settings.setting.*`, `settings.sequence.*` |
| `POST /settings/sequences/next` | ✅ `router.py:55` — increments and returns `{key, next}` |
| **Atomic allocation** | ❌ **`next_sequence_number` is not concurrency-safe** — two concurrent calls can return the same number (read `next_number`, then write `+1` with no lock) |
| **`core/numbering.py`** | ❌ still used by every module — derives `count+1` (gaps, races, wrong after rollback) |
| **Migration of modules to `number_sequences`** | ❌ `finance`, `sales`, `procurement`, `pos`, `hr`, `support` all call `next_number()` directly |

**Headline:** two sequence mechanisms coexist — the table (`NumberSequence`) and the count-derived `core/numbering.py`. The table is the right design but is **not used by any document**, and even its own `next` endpoint is racy. Every module doc in this set (01, 02, 05, 06, 08…) marks "adopt number_sequences" as a dependency; this is that dependency.

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

- [ ] M1 atomic allocator + FY + pattern (concurrency test)
- [ ] M2 all modules migrated; `core/numbering.py` removed
- [ ] M3 secrets + rotation + audit
- [ ] RBAC, encryption, audit
- [ ] Playwright happy path
- [ ] Conformance row updated