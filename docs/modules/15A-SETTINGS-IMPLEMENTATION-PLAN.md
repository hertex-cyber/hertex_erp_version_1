# 15A — Settings & Numbering: Implementation Plan (industry-grade)

**Module owner:** Settings (platform) · **Consumers:** every module
**Status:** locally verified; core registry, resolver, secrets, atomic numbering engine, sweeps and admin UI are green against 134 backend tests, 29 frontend tests, 3 Playwright tests, Alembic replay and both gap-report benchmarks. Remaining acceptance gaps are listed in the audit below. Extends `15-SETTINGS.md`, which stays the canonical design doc.
**Date:** 2026-11-17
**Scope:** two halves of the same platform module —
(A) **App settings** — typed, tenant/org configuration with a governed registry, layered resolution, caching, audit and secrets;
(B) **Number sequences** — one atomic document-numbering engine for every human-facing number in the ERP.
**Benchmarks:** Zoho Books (organization profile · preferences · enable-modules · taxes · currencies · templates), SAP Business One (Administration → System Initialization: company details, posting periods, **numbering series per period indicator**, per-branch series, manual-numbering authorization), Odoo (`res.config.settings` + `ir.config_parameter` + `ir.sequence` standard vs `no_gap`, `use_date_range`), Tally (FY-based voucher numbering).
**Statutory anchors:** CGST **Rule 46(b)** (consecutive serial, ≤16 chars, reserved charset, unique per FY), GSTN **IRP** document-number validation (no lowercase, no leading `0`/`-`/`/`), GSTR-1 cancelled-invoice reporting (gaps must be *explained*, not hidden), DPDP Act 2023 + ISO 27001 A.8/A.9 for secrets and change control.

## 0A. Implementation audit (2026-11-21)

The core platform is implemented and locally verified: typed registry and resolver, scoped values, change history, AES-GCM secret vault with rotation, atomic allocation ledger, period counters, SQL-window gap reports, offline blocks, pattern parser, settings/secrets/numbering endpoints, Celery sweeps, admin UI, CI gates and seed defaults. The 2026-11-20 migration replay blockers were fixed and blank-DB `upgrade head` + double seed replay is green. Verification totals: 134 backend tests, 29 frontend tests, 3 Playwright tests, lint/secret-leak/OpenAPI snapshot gates, synthetic gap p95 162.19 ms and live endpoint gap p95 272.84 ms.

Remaining acceptance gaps:

- 100-way and mixed-module concurrency; the current green test covers 30-way uniqueness.
- Hypothesis property test for pattern rendering is not added.
- Dedicated FY rollover/backdate/closed-period acceptance suite is not added.
- Pattern collision pre-check across active series is not implemented.
- Feature-flag-driven navigation was not re-audited in this pass.
- Local Celery worker requires Redis 7; the local Redis 6.0 instance cannot run the Redis 7 transport helpers. Compose and CI use `redis:7-alpine`.

---

## 0. How this document relates to the others

| Doc | Relationship |
|---|---|
| `15-SETTINGS.md` | The *design* doc: domain model, SE-01…SE-07, M1–M3. **This file is the execution plan** — same rules, expanded into buildable work. |
| `00-MASTER-ARCHITECTURE.md` §5.1 / §5.3 | `number` is a mandatory field on every transactional entity and must come from `number_sequences`. §5.3 explicitly names this module as the blocker. |
| `99-IMPLEMENTATION-SEQUENCE.md` Phase 0.5 / 1.2 | Atomic sequences are a **phase-0 correctness spine** item. Nothing numbered ships before this. |
| `01`, `02`, `05`, `06`, `08`, `10` module docs | Each marks "adopt number_sequences" as a dependency — here is the shared engine they call. |
| `01A`, `08a`, `09a`, `16a` | Sibling implementation plans; same style, same milestone/test discipline. |
| `PLAN-CONFORMANCE-CHECKLIST.md` | Row 192 (`Settings / number sequences`) is updated at the end of every milestone. |

**Non-negotiable framing:** this module is small in surface area and enormous in blast radius. A settings bug silently changes tax treatment for every invoice; a numbering bug corrupts every document trail and every GST return. Both halves therefore get the same treatment: an allow-listed registry (no arbitrary config), atomic primitives, full audit, and tests that fail loudly.

---

## 1. Executive summary

Today the ERP has **three** competing configuration stores and **two** competing numbering mechanisms, and none of them is safe to run a live business on:

| # | Today | Why it cannot ship |
|---|---|---|
| 1 | `AppSetting` — free-form JSON blob per `(tenant_id, key)`; any key, any shape, no type, no validation, no secret handling | An operator can write `finance.defaults.tax_rate = "eighteen"` and nothing rejects it. Tax logic reads whatever it finds. |
| 2 | `NumberSequence` table — correct idea, **used by zero documents** | The one right design is dead code. |
| 3 | `core/numbering.py` — `SELECT count(*) + 1` per document | **24 call sites** across 7 files. Races under concurrency, reuses numbers after a delete, produces duplicates after a rollback, and re-issues numbers when a row is deleted (count goes *down*). |
| 4 | `Tenant.settings` JSON column (`identity/models.py:51`) | A third, untyped, unaudited config surface with no reader. |
| 5 | `POST /settings/sequences/{key}/next` (`settings/router.py:55`) | Read-then-write with no lock → two concurrent calls return the same number. |

**Target state.** One governed settings registry with a typed, allow-listed key catalogue, layered resolution (`code default → env → tenant → branch → user`), write-through validation, read-through cache with version-stamped invalidation, and full change history. One atomic numbering engine: a single `UPDATE … RETURNING` per allocation, per-FY counters, pattern rendering with a token allow-list, per-document-channel constraints (GST ≤16 chars etc.), an allocation ledger with a gap report, offline number blocks for POS, and fiscal-year rollover. `core/numbering.py` is deleted.

**Why this ordering.** Numbering is a phase-0 correctness spine item and blocks five modules; the settings registry is a phase-1 hygiene item. So: numbering first (M1–M3), settings registry second (M4), secrets third (M5), admin UI last (M6).

---

## 2. Current state (verified from code, 2026-11-17)

### 2.1 Assets that exist

| Asset | Evidence | Verdict |
|---|---|---|
| `app_settings` table | `backend/app/modules/settings/models.py:9-16` — `key` (120), `value` JSON, `category` (80), `description`; unique `(tenant_id, key)` | ✅ exists · ❌ untyped |
| `number_sequences` table | `models.py:19-27` — `key` (80), `prefix` (30), `next_number`, `padding`; unique `(tenant_id, key)` | ✅ exists · ❌ never consumed |
| Generic CRUD for both | `settings/router.py:28-61` via `build_crud_router` | ✅ |
| `POST /settings/sequences/{key}/next` | `settings/router.py:64-83` — select → `next_number += 1` → `commit` | ❌ race (no lock, no atomic SQL) |
| Seed defaults | `backend/app/db/seed.py:126-176` — 4 settings (`company.profile`, `finance.defaults`, `sales.defaults`, `support.sla`) + 10 sequences (`SEQUENCES` at `seed.py:33-44`) | ✅ seeded · ❌ sequences unused |
| CRUD auto-numbering | `backend/app/core/crud.py:126-134` — calls `next_number(...)` when `number_field` set | ❌ count-based |
| Audit of CRUD writes | `core/crud.py:267,324,358` → `core/audit.py:38` (`REDACTED_KEYS` masks `secret`-ish names) | 🟡 partial (settings values not diffed) |
| Permission codes | `core/permissions_catalog.py:88` (`settings: setting, sequence`), `:110` (`system.settings.manage`) | ✅ exist |
| Frontend | `frontend/src/pages/resources/settings.jsx` (`SettingsValuesPage`, `SequencesPage`), routes `App.jsx:316-317`, nav `lib/nav.js:254-255` | 🟡 generic `ResourcePage`, JSON textarea editing |

### 2.2 Assets that do not exist

- No settings **registry** — no catalogue of allowed keys, types, defaults, validators or scopes. Any key is accepted; the seed's 4 keys are the de-facto schema, and no code enforces them.
- No settings **resolution layer** — modules do not read settings at all (`grep settings.` in module code: zero consumers), so "configurable" is aspirational. Values like GST rate, currency, FY start are hard-coded (`finance/service.py` `GST_STATE_CODES` and COA constants) or per-request.
- No **cache** and no invalidation; no `SETTINGS_ENCRYPTION_KEY` in `core/config.py`; `core/security.py` has hashing only, **no symmetric encryption utility**.
- No `value_type`, `is_secret`, `updated_by_id`, `scope`, or version on settings; no change-history table; settings updates are audited by the generic CRUD path only when they go through it (`PUT` via `ResourcePage`), not when a service writes directly.
- No sequence `pattern`, `suffix`, per-FY counter, `last_allocated_at`, `owner_module`, `doc_type`, implementation mode, or allocation ledger.
- No tests: `backend/app/tests/` has 16 files, **none for settings or numbering**; no concurrency test anywhere.
- No `docs`-level runbook for sequencing or a rollback path for a bad sequence.

### 2.3 The 24 count-based numbering call sites

All of `next_number(db, Model, field, prefix, parent_tenant)` → `f"{prefix}-{count+1:05d}"` (`core/numbering.py:8-25`):

| File | Call sites | Documents |
|---|---|---|
| `finance/service.py` | 12 (`:464,565,638,685,815,929,1032,1169,1265,1399,1868,1981,2083`) | JournalEntry `JE`, Invoice `INV`, asset/payment/payroll JEs |
| `finance/tally.py` | 1 (`:230`) | JournalEntry from Tally import |
| `sales/router.py` | 3 (`:262,393,403`) | SalesOrder `SO`, DeliveryChallan `DC`, Invoice `INV` |
| `procurement/router.py` | 2 (`:176,269`) | PurchaseOrder `PO`, GoodsReceipt `GRN` |
| `pos/router.py` | 3 (`:205,210,314`) | PosSale `PS`, SalesOrder `SO`, Invoice `INV` |
| `projects/services.py` | 3 (`:563-601`) | `project`, `work_item`, `sprint` — **already row-locked** (`with_for_update`) + max-existing scan, i.e. a second half-built allocator |
| `core/crud.py` | 1 (`:129`) | every `number_field` resource: `PR` requisition, `INV` finance invoice, `TKT` ticket, `DC` challan, `PRJ`/`PRJ-T`/`SPR` |

**Four defects visible in this table alone:**
1. **Race** — two concurrent creates both read `count = N` and both take `N+1`.
2. **Reuse after delete** — `count` shrinks; the next document re-issues a live number.
3. **Prefix collision** — `SO` is issued by `sales/router.py:262` *and* `pos/router.py:210` against **different tables**, so `SO-00012` can exist twice.
4. **No FY scoping** — GST Rule 46(b) requires uniqueness *for the financial year*; today the series never resets and never records which FY a number belongs to.

`projects/services.py:545-591` is the one place that got it half right — row lock + max-existing scan — and it is exactly the shape the shared engine should generalise, with `UPDATE … RETURNING` replacing the scan.

### 2.4 Gap list (what the benchmark expects vs what we have)

| Capability | Zoho | SAP B1 | Odoo | Hertex today |
|---|---|---|---|---|
| Typed, validated settings | ✅ | ✅ | ✅ | ❌ free JSON |
| Settings scoped per module/company | ✅ per-module preferences | ✅ per-company/per-user | ✅ per-company + per-user (`res.config.settings`) | ❌ tenant only |
| Layered resolution with defaults | ✅ | ✅ | ✅ | ❌ none |
| Module/feature toggles | ✅ Enable Modules | 🟡 | ✅ | ❌ |
| Numbering series per doc type | ✅ | ✅ | ✅ | 🟡 table unused |
| Numbering series per FY / period indicator | ✅ per FY | ✅ **Period Indicator** | ✅ `use_date_range` | ❌ |
| Series per branch/GSTIN | 🟡 per location | ✅ per branch + group auth | 🟡 | ❌ |
| Atomic allocation | ✅ | ✅ | ✅ PG sequence / `no_gap` lock | ❌ (and `/next` racy) |
| Gap explanation / void registry | 🟡 | ✅ gap tracking | 🟡 | ❌ |
| Manual number override + authorization | 🟡 | ✅ `Document Manual Numbering` | 🟡 | ❌ |
| Encrypted secrets + rotation | ✅ (integrations vault) | 🟡 | ❌ | ❌ |
| Settings change audit with old/new + reason | ✅ | ✅ | 🟡 | 🟡 generic only |
| Numbering preview / status | ✅ | ✅ | ✅ | ❌ |
| Offline number blocks (POS) | ❌ n/a | ❌ | ❌ | ❌ → **differentiator** |

---

## 3. Benchmarks in detail — and what we adopt

### 3.1 Zoho Books (the SMB bar we must beat on coherence)

*Observed structure* (`zoho.com/books/help/settings`): Settings splits into **Organization Profile**, **Opening Balances**, **Users**, **Online Payments**, **Preferences** (per module: Quotes, Sales Orders, Invoices, Recurring Invoices, Credit Notes, Delivery Notes, Packing Slips, Purchase Orders), **Currencies**, **Taxes**, **Templates**, **Automation**. Preferences → General holds: **Enable Modules** (module on/off; note their own caveat that the *API still works* when a module is disabled), **first day of work week**, PDF attach/encrypt, **discount level** (line/txn/both, inclusive vs exclusive of tax). Taxes → Tax Settings holds: tax registration number, tax label, reverse-charge toggles, **"track taxes under a single account vs separate Output/Input accounts"**, and **tax override allowed in transactions** toggles.

*Adopt:* per-module preference grouping (our `category` becomes `module`); account-mode and override-style **policy switches** as first-class typed settings (they change ledger behaviour → must be audited and immutable-after-first-use); the discount-level switch; the "API unaffected by module toggle" rule as an explicit documented behaviour rather than a surprise.
*Reject:* a settings UI that writes arbitrary free text into a JSON blob (that's exactly our current state).
*Beat it:* typed registry + validation + change history + reason, and numbering that is provably race-free (Zoho's own numbering is not FY-constrained by GST rules the way ours must be).

### 3.2 SAP Business One (the numbering benchmark)

*Observed* (`help.sap.com`, `learning.sap.com`, SAP KBA 3281252):
- Document numbering is per document type, default "Primary" series starting at 1, **uncapped** by default, prefix/suffix **print-only** (not part of the stored number).
- **Multiple series** exist so different teams/branches get different ranges; series are authorised through **groups 1–10** (a user with no series authorisation cannot even open the document window).
- **Period Indicators** (i.e. FY) gate series: an A/R Invoice with posting date in 2019/20 can only use a series defined under that period indicator — even the default series is rejected. If no series exists for that period, document creation is **blocked with a message**.
- With multiple branches, the JE series is chosen as "the first unlocked series for the current period assigned to the selected branch".
- **Manual numbering** is a separate general authorization (`Document Manual Numbering`); table PKs are documented as *not necessarily consecutive*.

*Adopt (all five):* series identity = `(doc_type, branch/GSTIN, fiscal_year)`; hard **block-on-missing-series** (never silently fall back — that is how duplicate numbers happen); separate permission for manual override; explicit "gaps are permitted and recorded" statement; print-only prefix/suffix as a *render* concern, not part of the stored number (we store the rendered string in the document but the *series* remains the source of truth).
*Reject:* 10-series cap and group-based authorisation (we have real RBAC).
*Beat it:* gap ledger mapped to GSTR-1 cancelled invoices; preview/status endpoints; offline blocks for POS.

### 3.3 Odoo (the implementation benchmark)

*Observed* (`ir.sequence`, `ir.sequence` docs/issues): fields `code`, `prefix`/`suffix` with date placeholders, `padding`, `number_next`, `number_increment`, `implementation ∈ {standard, no_gap}`, `use_date_range`.
- `standard` uses a native **PostgreSQL SEQUENCE** (`nextval`) — fast, safe under load, but a number consumed by a rolled-back transaction is **never reused** → permanent gap.
- `no_gap` uses **table-level locking** → truly consecutive, at the cost of serialising concurrency.
- Community-reported defect (odoo#302782): switching `implementation` on an existing sequence can **re-issue already-issued numbers**. A live lesson: *implementation mode must be immutable once the sequence has allocations.*

*Adopt:* the standard/no_gap split **as a per-sequence setting with an immutability rule**; date-range (FY) subsequences; padding; increment; prefix date placeholders (our `pattern`).
*Reject:* silently permitting an implementation switch on a live sequence (we forbid it after first allocation).
*Beat it:* the FY/period counter is a row we control, so preview (`peek`) is exact rather than `_predict_nextval` guesswork.

### 3.4 Tally (the Indian baseline the accountant will compare against)

Voucher numbering is FY-scoped and configurable per voucher type; Tally users expect to see a *numbering series* screen and to be able to say "reset on 1 April". Our engine must therefore expose: reset policy, FY start month, and a per-FY status view — or the Tally migration (`18`) will lose the audit trail on day one.

### 3.5 Industry standards that constrain the design

| Standard | Constraint on this module | Where it lands |
|---|---|---|
| **CGST Rule 46(b)** (verified: `taxinformation.cbic.gov.in`) | Serial must be **consecutive**, **≤16 characters**, characters limited to **alphabets, numerals, `-` and `/`**, **unique for a financial year**; one **or multiple series** allowed | Pattern validator + `max_length` + charset regex per doc channel; `fiscal_year` on every allocation |
| **GSTN IRP** validation | Document number limited to 16 alphanumeric + `/`/`-`; **rejects lowercase**, and numbers **beginning with `0`, `/`, `-`** | `irp_safe` flag on the pattern; leading-token validator; uppercase-only rendering for `invoice` |
| **GSTR-1** | Cancelled invoices are reported as cancelled; a missing serial is a query point | Gap ledger with reason codes (`void`, `cancelled`, `abandoned`, `manual_skip`) + report export |
| **ISO 27001 A.8.24 / A.9.4** | Secrets encrypted at rest, key rotation, privileged-access restriction | `setting_secrets` vault, `SETTINGS_ENCRYPTION_KEY`, masked reads, rotation window |
| **Change control (SOX-style / four-eyes)** | Financial-policy settings need approver + reason + before/after | `is_critical` flag → approval state machine + reason required |
| **12-factor / deploy vs runtime config** | Deploy-time config stays in env; runtime config is data | `SOURCE_DEPLOY_ONLY` flag: such keys are readable but not writable via API |
| **DPDP 2023 / GDPR** | Settings that change retention, consent or data residency are themselves personal-data-relevant | `data_impact` tag on the setting descriptor → forces audit + approval |

---

## 4. Target architecture — Settings (half A)

### 4.1 The registry: code is the schema, the database is only the values

A **settings registry** is a code-declared, allow-listed catalogue. Requests may only touch registered keys. Every descriptor carries type, default, scope order, validation, mutability and classification.

```python
# backend/app/modules/settings/registry.py  (new)
@dataclass(frozen=True)
class SettingDescriptor:
    key: str                      # "finance.rounding.policy" (dot namespace: module.entity.attribute)
    type: SettingType             # string|int|decimal|bool|enum|json|date|currency|duration|secret
    default: Any
    scopes: tuple[str, ...] = ("tenant", "branch", "user")   # ordered: first scope with a value wins
    module: str = "general"       # groups the UI
    label: str = ""
    help: str = ""
    choices: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None
    regex: str | None = None
    json_schema: dict | None = None
    critical: bool = False        # change requires reason + approval (+ re-auth)
    deploy_only: bool = False     # readable, never writable through the API
    immutable_after: str | None = None   # e.g. "finance_first_posting"
    data_impact: str | None = None       # dpdp|retention|residency → forces approval & audit
    deprecated_alias: str | None = None  # legacy key that still reads through
```

**Key namespace convention:** `{module}.{entity}.{attribute}` in dot notation (`finance.invoice.due_days`, `sales.quote.validity_days`, `company.locale.currency`, `security.session.timeout_minutes`). The existing seed keys (`company.profile`, `finance.defaults`, …) become **grouped objects** under registered aggregate keys, not free blobs.

**Registry size:** ~45 keys at v1, in 9 groups (`company`, `localization`, `finance`, `sales`, `procurement`, `inventory`, `hr`, `support`, `security`, `features`, `notifications`, `documents`). The catalogue table lives in §4.4.

**Invariant S-REG-1:** *A write to an unregistered key is a 422, never a 201.* Today it is a 201. This single rule removes an entire class of silent misconfiguration.

### 4.2 Layered resolution with declared precedence

```
code default (registry descriptor)
   ↑ overridden by  deploy env / core/config.py      (deploy_only keys stop here)
   ↑ overridden by  tenant row    (scope_type='tenant')
   ↑ overridden by  branch row    (scope_type='branch', scope_id=branch)
   ↑ overridden by  user row      (scope_type='user',   scope_id=user.id)
```

Precedence is **not** a global rank; it is the descriptor's `scopes` order (this mirrors the "scope order declared per setting" pattern used in mature multi-tenant settings libraries). Policy settings declare `("tenant",)` — a user cannot override a tax policy. Personal preferences declare `("user", "tenant")` — the user's own value wins. A write to a scope the descriptor does not declare is rejected, so read and write authority can never diverge.

```python
# backend/app/modules/settings/service.py  (new — the only sanctioned reader/writer)
class SettingsService:
    async def get(self, db, *, tenant_id, key, branch_id=None, user_id=None, default=_UNSET) -> Any
    async def get_many(self, db, *, tenant_id, keys, branch_id=None, user_id=None) -> dict[str, Any]
    async def set(self, db, user, *, key, value, scope="tenant", scope_id=None,
                  reason: str | None = None, request_id: str | None = None) -> AppSetting
    async def unset(self, db, user, *, key, scope="tenant", scope_id=None) -> None  # revert to inherited
    async def resolve_all(self, db, *, tenant_id) -> dict[str, Any]              # effective config payload
    async def history(self, db, *, key, limit=50) -> list[SettingChange]
```

**Fail-closed rule (S-REG-2):** a missing/invalid value at read time returns the **registry default**, never `None`, never an exception inside a tax/posting path — and logs a `settings.invalid_value` warning once per key per hour. A tax posting must never fail because an admin typed a bad string; it must run on the documented default and scream in the audit trail.

### 4.3 Caching and invalidation

- Process-local LRU keyed `(tenant_id, scope_type, scope_id)` holding the **fully resolved** config dict, TTL 300 s default.
- Every `set`/`unset` bumps a per-tenant `config_version` (a `settings_version` column on `tenants`, or a Redis `INCR` when available). Cached entries carry the version they were built from; a version mismatch is a miss.
- Redis is optional (already in `core/config.py` `REDIS_URL`): when present, publish `settings.changed` so peer workers invalidate without waiting for TTL. When absent, TTL is the guarantee — documented, not accidental.
- No settings read path is allowed to do its own `select`. A lint test greps for `AppSetting` imports outside `modules/settings/` and fails the build.

### 4.4 Data model and migration

**`app_settings` — extend (migration `0015a_settings_registry`)**

| Column | Type | Notes |
|---|---|---|
| `scope_type` | enum `tenant|branch|user` | default `tenant` |
| `scope_id` | UUID nullable | null for tenant scope; branch id / user id otherwise |
| `value_type` | varchar(16) | mirrors descriptor type at write time (defence against registry drift) |
| `is_secret` | bool | secret rows live in `setting_secrets`, this is a pointer flag |
| `version` | int | optimistic concurrency; stale write → 409 `settings.conflict` |
| `updated_by_id` | UUID FK users | who last changed it |
| `source` | enum `admin|seed|migration|api` | provenance for forensics |
| `checksum` | varchar(64) | sha256 of canonical JSON value; detects out-of-band edits |

Index change: `uq_app_settings_tenant_key (tenant_id, key)` → `uq_app_settings_scope_key (tenant_id, scope_type, scope_id, key)` (nullable `scope_id` handled with `NULLS NOT DISTINCT` on PG15+, otherwise a `COALESCE(scope_id, '00000000-…')` expression index).

**`setting_changes` — new**

```
id, tenant_id, key, scope_type, scope_id,
old_value JSONB, new_value JSONB,      -- secrets stored as {"__redacted__": "sha256:…"}
change_type enum(set|unset|rotate|approve|reject|migrate),
reason TEXT,                           -- required when descriptor.critical
actor_id, actor_email, approved_by_id, approval_state enum(none|pending|approved|rejected),
request_id, correlation_id, created_at
```
Purpose: the settings UI history drawer, the critical-change approval queue, and drift investigation. `record_audit()` is still called (single audit trail of record); this table adds *diffing and reason*, which `AuditLog.changes` cannot carry losslessly for nested JSON.

**`setting_secrets` — new (M5)**

```
id, tenant_id, key,
ciphertext BYTEA, nonce BYTEA, key_version INT, algo varchar(32),  -- AES-256-GCM
previous_ciphertext BYTEA, previous_nonce BYTEA, previous_expires_at TIMESTAMPTZ,
status enum(active|pending|retired), rotated_at, rotated_by_id, last_used_at
```
Never selected by any list endpoint. API returns `{"key": "...", "configured": true, "masked": "sk_••••4f2a", "rotated_at": ...}`.

### 4.5 The v1 settings catalogue (registered keys, grouped as the UI will show them)

| Group | Key | Type | Default | Critical | Notes / consumer |
|---|---|---|---|---|---|
| company | `company.profile.name` | string | tenant name | ✅ | invoice header, PDF |
| company | `company.profile.legal_name`, `.address`, `.phone`, `.email` | string/json | `""` | ✅ | Rule 46(a) invoice particulars |
| company | `company.profile.gstin`, `.pan`, `.cin` | string (regex) | `""` | ✅ | GSTIN regex `^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$` |
| company | `company.profile.state_code` | enum(01–38,96,97,99) | `""` | ✅ | intra/inter-state GST split (`17`) |
| localization | `company.locale.currency` | currency | `INR` | ✅ immutable after first posting | journal/document currency |
| localization | `company.locale.timezone` | string | `Asia/Kolkata` | 🟡 | timestamps, payroll cut-off |
| localization | `company.locale.date_format` | enum | `DD-MM-YYYY` | ❌ | UI/report rendering |
| localization | `company.locale.number_format` | enum | `1,23,456.78` (Indian) | ❌ | amounts |
| localization | `company.fiscal.start_month` | int 1–12 | `4` | ✅ immutable after first FY close | numbering + periods |
| finance | `finance.invoice.due_days` | int 0–365 | `15` | ❌ | replaces `finance.defaults` |
| finance | `finance.invoice.rounding` | enum `line|document` | `document` | ✅ | matches IRP validation (`00 §5.4`) |
| finance | `finance.tax.tracking_mode` | enum `single|separate` | `separate` | ✅ | Zoho-style output/input accounts |
| finance | `finance.tax.override_allowed` | bool | `false` | ✅ | Zoho "tax override" toggle |
| finance | `finance.journal.manual_allowed` | bool | `true` | ✅ | blocks ad-hoc JEs for non-accountants |
| finance | `finance.period.lock_policy` | enum `hard|soft` | `hard` | ✅ | period close (`01`) |
| finance | `finance.default_currency_rate_source` | enum | `manual` | ❌ | (`12`) |
| sales | `sales.quote.validity_days` | int | `14` | ❌ | replaces `sales.defaults` |
| sales | `sales.price.tax_inclusive` | bool | `false` | ✅ | pricing display + math |
| sales | `sales.discount.level` | enum `none|line|document|both` | `line` | ✅ | Zoho parity |
| sales | `sales.credit_limit.enforced` | bool | `true` | ✅ | (`05`) |
| procurement | `procurement.approval.threshold` | decimal | `50000` | ✅ | (`02`) |
| procurement | `procurement.match.tolerance_pct` | decimal 0–5 | `0` | ✅ | 3-way match |
| inventory | `inventory.valuation_method` | enum `fifo|weighted_avg` | `weighted_avg` | ✅ immutable after stock exists | (`03`) |
| inventory | `inventory.negative_stock_allowed` | bool | `false` | ✅ | |
| hr | `hr.payroll.cutoff_day` | int 1–31 | `25` | ✅ | (`08`) |
| hr | `hr.statutory.pf_rate`, `.esi_rate`, `.pt_state` | decimal/enum | statutory | ✅ | rate changes are legal events |
| pos | `pos.offline.block_size` | int 20–500 | `100` | ❌ | number-block reservation (§5.9) |
| pos | `pos.receipt.footer_text` | string | `""` | ❌ | |
| support | `support.sla.first_response_hours` | int | `4` | ❌ | (`10`) |
| support | `support.sla.resolution_hours` | int | `48` | ❌ | |
| support | `support.business_hours` | json | 09:00–18:00 Mon–Sat | ❌ | SLA clock |
| security | `security.session.timeout_minutes` | int | `60` | ✅ | mirrors `config.py` |
| security | `security.mfa.required_for_admins` | bool | `false` | ✅ | (`16a`) |
| security | `security.password.min_length` | int | `12` | ✅ | (`16a`) |
| notifications | `notifications.email.from_address` | string | `""` | ❌ | (`12`) |
| documents | `documents.pdf.show_gstin`, `.terms_text`, `.signature_required` | bool/string | — | 🟡 | (`19`) |
| features | `features.module.<name>.enabled` | bool | `true` | 🟡 | Zoho "Enable Modules"; **API stays live** (documented) |
| features | `features.beta.<name>` | bool | `false` | ❌ | staged rollout |

**Migration of existing values:** `company.profile` → the `company.profile.*` keys; `finance.defaults` → `finance.invoice.due_days` + `finance.tax.*`; `sales.defaults` → `sales.quote.validity_days`; `support.sla` → `support.sla.*`. Old aggregate rows are kept read-only for one release via `deprecated_alias` so nothing breaks mid-rollout.

---

## 5. Target architecture — Numbering engine (half B)

### 5.1 Data model (config / counter / ledger separation)

The single most important structural decision: **separate the series *configuration* from the per-FY *counter* and from the *allocation ledger*.** Config changes must never be able to reset a counter; counters must be the only lock target; the ledger is what makes gaps explainable.

**`number_sequences` — the series definition (extends existing table)**

| Column | Type | Notes |
|---|---|---|
| `key` | varchar(80) | stable engine key: `invoice`, `sales_order`, `journal_entry`, `pos_sale`, `payslip`, `ticket`, `project` … (existing) |
| `doc_type` | varchar(40) | maps to the constraint profile in §5.5 (`gst_invoice`, `internal`, `pos`) |
| `owner_module` | varchar(40) | procurement / sales / finance / pos / hr / support / projects |
| `pattern` | varchar(120) | `INV/{fy}/{seq:05}` — token allow-list, §5.4 |
| `prefix`, `suffix` | varchar(30) | print-only fallback when `pattern` is null (keeps today's UI honest) |
| `padding` | int | zero-pad width for `{seq}` |
| `start_number` | int | first number of every period (default 1) |
| `increment` | int | default 1 (Odoo parity) |
| `implementation` | enum `standard|nogap` | `standard` = gapped+fast (default); `nogap` = serialised+consecutive |
| `reset_policy` | enum `never|fiscal_year|calendar_year|monthly` | Tally/Zoho expectation |
| `branch_id` | UUID nullable | per-branch / per-GSTIN series (SAP parity) |
| `gstin` | varchar(15) nullable | series identity when a tenant files from multiple GSTINs |
| `max_length` | int nullable | hard cap; **16** for GST documents |
| `allowed_chars_regex` | varchar(120) | default `^[A-Z0-9\-/]+$` for GST docs |
| `irp_safe` | bool | enable IRP rules (uppercase, no leading `0`/`-`/`/`) |
| `manual_allowed` | bool | SAP's `Document Manual Numbering` equivalent |
| `advance_on_manual` | bool | whether a manual number above the counter advances it |
| `status` | enum `draft|active|locked` | `locked` after first allocation for `implementation`/`pattern`/`reset_policy` |
| `last_allocated_at` | timestamptz | feeder for the sequence status view |
| `next_number` | int | **deprecated** — kept only until M4 cleanup; the period row is the counter |

Unique: `(tenant_id, key, branch_id)` with `NULLS NOT DISTINCT`; index on `(tenant_id, owner_module)`.

**`number_sequence_periods` — the counter (one row per series × period)**

```
id, sequence_id FK, tenant_id,
fiscal_year varchar(9),           -- '2025-26'; '2025' for calendar; '2025-11' for monthly; '' for never
period_start DATE, period_end DATE,
next_number INT NOT NULL,         -- the ONLY field that is incremented
allocated_count INT DEFAULT 0,    -- for status/report without scanning the ledger
status enum(open|closed),         -- closing blocks backdated allocation
last_allocated_at, last_allocated_by_id, created_at, updated_at
UNIQUE (sequence_id, fiscal_year)
```

**`number_allocations` — the ledger (every number ever handed out)**

```
id, tenant_id, sequence_id, period_id, fiscal_year,
number BIGINT,                    -- numeric part only
rendered varchar(64),             -- what the document shows
status enum(allocated|committed|void|manual|block),
document_type varchar(40), document_id UUID nullable,
branch_id UUID nullable, device_id varchar(80) nullable,   -- POS blocks
idempotency_key varchar(120) nullable,
reason_code enum(abandoned|cancelled|void|manual_skip|block_unused) nullable,
reason_text varchar(200) nullable,
allocated_at, committed_at, voided_at, allocated_by_id
UNIQUE (sequence_id, fiscal_year, number)          -- the real duplicate guard
UNIQUE (tenant_id, idempotency_key) WHERE idempotency_key IS NOT NULL
INDEX (tenant_id, status, allocated_at)            -- gap report
INDEX (tenant_id, document_type, document_id)
```

**`number_sequence_blocks` — offline reservation (POS, module 06)**

```
id, tenant_id, sequence_id, period_id, fiscal_year,
range_start BIGINT, range_end BIGINT, size INT,
device_id varchar(80), session_id UUID nullable,
status enum(issued|partially_used|exhausted|returned|expired),
issued_at, expires_at, used_count INT DEFAULT 0, returned_from BIGINT nullable
```

**Document-side guarantees (per module, added in M4):** a unique index on the rendered number, so even a bug in the engine cannot produce a duplicate document:

| Table | Constraint |
|---|---|
| `finance_journal_entries` | `uq_finance_journal_entries_tenant_number (tenant_id, entry_number)` |
| `finance_invoices` | `uq_finance_invoices_tenant_number (tenant_id, invoice_number)` |
| `sales_orders` / `sales_delivery_challans` | `(tenant_id, order_number)` / `(tenant_id, challan_number)` |
| `procurement_purchase_orders` / `goods_receipts` / `requisitions` | `(tenant_id, <number>)` |
| `pos_sales` | `(tenant_id, sale_number)` |
| `support_tickets` | `(tenant_id, ticket_number)` |
| `hr_payslips` | `(tenant_id, payslip_number)` |

### 5.2 The allocation primitive (the concurrency contract)

**Standard mode (`implementation='standard'`, default) — gapped, lock-free, fast**

```sql
-- executed and COMMITTED before the document insert; one statement, no read-modify-write
UPDATE number_sequence_periods
   SET next_number      = next_number + :increment,
       allocated_count  = allocated_count + 1,
       last_allocated_at = now(),
       last_allocated_by_id = :actor_id
 WHERE id = :period_id
   AND status = 'open'
RETURNING next_number - :increment AS allocated;
```

*Why this is race-free:* the row lock is taken by the `UPDATE` itself, the `RETURNING` returns the post-image, and two concurrent statements serialise on the row — no window between read and write exists. This is the mechanism named in `15-SETTINGS.md` §3.2 and it needs no advisory locks, no `SELECT … FOR UPDATE`, no application mutex.

*Why it commits immediately:* the counter must be independent of the caller's transaction; a rollback of the business document must not rewind the counter (this is Odoo `standard` semantics, and it is what makes POS and import paths safe). The cost is a gap — recorded in the ledger, explained in the gap report (§5.8).

**No-gap mode (`implementation='nogap'`, opt-in) — consecutive, serialised**

Same SQL, but executed **inside the caller's transaction** and never committed by the engine. The row lock persists until the business transaction ends; a rollback rolls the counter back with it, so no number is consumed. Concurrency collapses to one allocation at a time for that series. Recommended only for low-volume, legally-serialised documents.

**Mode immutability (lesson from odoo#302782):** once `number_allocations` has a row for a series, `implementation`, `pattern`, `reset_policy` and `padding` become read-only (422 `numbering.sequence_locked`). Changing them silently re-issues numbers in every system that allows it; we forbid it and require a *new* series key (with a documented cut-over) instead.

**Retry and failure semantics**

| Failure | Engine behaviour | Caller sees |
|---|---|---|
| Row lock timeout / deadlock | retry ×3 with jittered backoff | then `409 numbering.busy` (retryable) |
| Period row missing/closed | refuse (no silent fallback — SAP parity) | `422 numbering.series_missing` / `409 numbering.period_closed` |
| Unique violation on ledger | treated as duplicate → new attempt (max 3) | `409 numbering.duplicate` |
| Repeated request with same `idempotency_key` | returns the **same** number, `replayed=true` | `200` |

### 5.3 The public engine API (single entry point for all modules)

```python
# backend/app/modules/settings/numbering.py  (new — replaces core/numbering.py)
class NumberSequenceService:
    async def allocate(
        self, db, *, tenant_id: UUID, key: str, user: User | None = None,
        branch_id: UUID | None = None, on_date: date | None = None,
        idempotency_key: str | None = None,
        document_type: str | None = None, document_id: UUID | None = None,
    ) -> AllocatedNumber          # .number (int) .rendered (str) .fiscal_year .period_id

    async def peek(self, db, *, tenant_id, key, branch_id=None, on_date=None) -> str
    async def status(self, db, *, tenant_id, key, fiscal_year=None) -> SequenceStatus
    async def void(self, db, *, user, rendered: str, key: str, reason_code: str, reason_text: str) -> None
    async def commit(self, db, *, allocation_id, document_type, document_id) -> None
    async def reserve_block(self, db, *, tenant_id, key, size, device_id, session_id=None) -> SequenceBlock
    async def return_block(self, db, *, block_id, used_up_to: int | None) -> BlockReturn
    async def ensure_period(self, db, *, tenant_id, key, on_date) -> Period
    async def validate_pattern(self, descriptor: NumberSequence, sample_fy: str) -> list[str]  # config-time
```

**Caller ergonomics** — the migration is mechanical (`grep`-provable):

```python
# before (finance/service.py:464)
number = await next_number(db, JournalEntry, "entry_number", "JE", user.tenant_id)
# after
number = (await numbering.allocate(db, tenant_id=user.tenant_id, key="journal_entry",
                                   user=user, on_date=entry_date)).rendered
```

`on_date` matters: the number's FY comes from the **document date**, not `now()` (SAP's posting-date/period-indicator rule). A backdated invoice in FY 2025-26 must draw from the 2025-26 series.

### 5.4 Pattern grammar (allow-listed tokens, validated at config time)

```
pattern  := (literal | token)*
token    := '{' name (':' '0'? width 'd')? '}'
name     := seq | prefix | suffix | fy | yy | yyyy | mm | dd | branch | state | tenant_code | doc
literal  := [A-Z0-9\-/_ .]*
```

| Token | Renders | Example |
|---|---|---|
| `{seq}` / `{seq:05}` | period counter, zero-padded to `width` (falls back to `padding`) | `00042` |
| `{fy}` | fiscal year label from `fiscal_year` | `25-26` |
| `{yy}` / `{yyyy}` | 2/4-digit year of the document date | `25` / `2025` |
| `{mm}` | month (period-based series) | `04` |
| `{branch}` | branch/location code (from branch master, uppercased) | `BLR` |
| `{state}` | GST state code of the issuing GSTIN | `29` |
| `{tenant_code}` | short tenant alias | `HRT` |
| `{doc}` | doc-type tag (`INV`, `CN`, `JE`) | `INV` |
| `{prefix}`/`{suffix}` | legacy columns, for compatibility | `INV` |

**Rejected tokens (security/integrity):** `{random}`, `{uuid}`, `{user}`, `{now}`, `{env}`, nested braces, Python format specs beyond `0Nd`, `%` strings. Rationale: any token that can't be predicted breaks `peek` and the gap report, and template injection is a real class of bug — hence SE-06's allow-list, enforced by a real parser (never `str.format` on user input; render by token substitution only).

**Config-time validation (the anti-timebomb rule).** On save, the engine renders the *worst case* — `seq = 10**padding - 1`, next FY label, longest branch code — and rejects the pattern if:

1. `len(worst_case) > max_length` (§5.5) → `422 numbering.pattern_too_long`,
2. the rendered value violates `allowed_chars_regex`,
3. `irp_safe` and it starts with `0`, `-` or `/`, or contains lowercase,
4. an unknown/unbalanced token is present,
5. two active series for the same `(doc_type, branch)` would render into the same namespace (collision pre-check).

Without rule 1 the system works perfectly until document 100001, then breaks in production. This is the single most valuable cheap test in the module.

### 5.5 Document-channel constraint profiles

| `doc_type` | `max_length` | charset | uppercase | reset | mandated by |
|---|---|---|---|---|---|
| `gst_invoice`, `gst_credit_note`, `gst_debit_note` | **16** | `A-Z0-9-/` | ✅ | `fiscal_year` | CGST Rule 46(b) + IRP validation |
| `gst_bill_of_supply` | 16 | `A-Z0-9-/` | ✅ | `fiscal_year` | Rule 49 |
| `pos_sale` | 24 | `A-Z0-9-` | ✅ | `fiscal_year` | internal + offline blocks |
| `internal` (SO, PO, GRN, DC, payment, JE, payslip, ticket, project, sprint) | 32 | `A-Z0-9-/` | ❌ | `never` or `fiscal_year` | house convention (`00 §5.1`) |
| `journal_entry` | 32 | `A-Z0-9-/` | ❌ | `fiscal_year` | SAP JE-per-period parity |

**Rule 46 caveat we must encode, not paper over:** GST requires a *consecutive* serial within a series, but cancelling an invoice legitimately creates a gap. The compliance answer is not "gapless numbering", it is **every gap is attributable** — which is exactly what `number_allocations` + `reason_code` gives us, and what the GSTR-1 cancelled-invoice report consumes. This is why `standard` (gapped) is the default even for invoices, and `nogap` is offered for tenants whose auditors insist.

### 5.6 Fiscal-year rollover

```
first allocation of the day
   -> ensure_period(tenant, key, fy_of(on_date))
        INSERT INTO number_sequence_periods (...) VALUES (..., start_number, 'open')
        ON CONFLICT (sequence_id, fiscal_year) DO NOTHING
        -> SELECT ... (returns existing or new row)
```

- New period starts at `start_number` (default 1) and is **independent** of last year's counter — so `INV/25-26/001` and `INV/26-27/001` coexist and both stay unique *per FY*, satisfying Rule 46's "unique for a financial year".
- A beat job (added with the existing worker scaffolding in `99` Phase 1) pre-creates the next period 7 days before `period_end`, emits `numbering.period_opened`, and posts an advisory to the settings UI ("FY 2026-27 series ready, starts at INV/26-27/001").
- Closing last year's period (`status='closed'`) makes backdated allocation into it a hard `409 numbering.period_closed` — the numbering-safe twin of the finance period lock (`01`, `finance.period.lock_policy`).
- Reports and reconciliation always carry `fiscal_year` on the allocation, so a document is re-discoverable by (series, FY, number) — the auditable triple.

### 5.7 Manual override (SAP parity, permission-gated)

Allowed only when `number_sequences.manual_allowed` and the user holds `settings.sequence.manual`:
- the supplied number must satisfy the §5.5 profile (length/charset/uppercase) and be unique for `(series, FY)`;
- it is written to the ledger with `status='manual'` and `reason_code='manual_skip'`;
- if `advance_on_manual` is on and the manual number ≥ counter, the counter advances past it (preventing a later collision);
- a manual entry that *skips* numbers implicitly creates gaps — the gap report lists them under `manual_skip` so month-end has a story.

### 5.8 Void / cancel and the gap report

`void()` never deletes a ledger row; it sets `status='void'` with a reason, and the document side (sales/finance cancel flows) calls it. The gap report is a query over the ledger, grouped by series/FY/reason:

| Report | Definition | Consumer |
|---|---|---|
| Allocated per period | `COUNT(*)` by fiscal_year | settings status view, capacity planning |
| Gap list | numbers in `[min,max]` with no ledger row, or ledger rows `status='void'` | audit, GSTR-1 cancelled-invoice reconciliation |
| Unreturned blocks | `status IN (issued, partially_used)` past `expires_at` | POS fleet ops |
| Manual overrides | `status='manual'` in last 90 days | audit/controls review |
| Series coverage | doc types with no active series | provisioning checklist |

### 5.9 Offline number blocks (POS / warehouse guns) — our differentiator

A device that must issue bills offline cannot call the allocator. It reserves a block:

1. `reserve_block(size=N)` — one atomic `UPDATE … next_number + N … RETURNING`, and the block `[start, start+N-1]` is inserted with `status='issued'`, `device_id`, `expires_at = now() + 7 days`.
2. The device numbers sales locally inside the block, migrating them on sync with `document_id` set on the ledger rows (`status='committed'`).
3. `return_block(used_up_to=k)` marks the unused tail `void`/`block_unused` — a *declared* gap rather than an invisible one.
4. Expired unreturned blocks are surfaced by the report and by a "POS devices with open blocks" counter on the settings screen.

No benchmark system (Zoho/SAP B1/Odoo) does this; it is a genuine differentiator and it is the only correct way to keep POS offline numbering unique.

---

## 6. API surface

All endpoints under `/api/v1`, tenant-scoped from the JWT (`core/deps.py`), `Page[T]` pagination where a list is possible, and OpenAPI tags matching the existing `Settings · …` convention.

### 6.1 Settings

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/settings/registry` | GET | `settings.setting.read` | descriptors for the UI (key, type, module, label, help, choices, critical, scopes, default) — **no values** |
| `/settings/values` | GET | `settings.setting.read` | **effective** config for the caller, each entry with `value`, `source` (`default|env|tenant|branch|user`), `scope_id` |
| `/settings/values/{key}` | PUT | `settings.setting.update` | typed write; body `{value, scope, scope_id, reason, version}`; critical keys → `approval_state='pending'` unless the caller is an approver |
| `/settings/values/{key}` | DELETE | `settings.setting.update` | unset → fall back to inherited/default |
| `/settings/values/{key}/history` | GET | `settings.setting.read` `+ system.audit.read` | change history with old/new/reason/actor |
| `/settings/changes` | GET | `system.settings.manage` | pending critical changes |
| `/settings/changes/{id}/approve` \| `/reject` | POST | `system.settings.manage` | four-eyes approval; self-approval blocked |
| `/settings/secrets` | GET | `system.settings.manage` | **masked** list (`configured`, `mask`, `rotated_at`) — never ciphertext or plaintext |
| `/settings/secrets/{key}` | PUT | `system.settings.manage` | write secret (validated, encrypted, audited as `__redacted__`) |
| `/settings/secrets/{key}/rotate` | POST | `system.settings.manage` | start rotation window (`pending`) |
| `/settings/secrets/{key}/commit` \| `/rollback` | POST | `system.settings.manage` | close/revert the rotation window |
| `/settings/features` | GET | `settings.setting.read` | module/feature flags resolved for the caller (drives nav) |

Compatibility: the existing generic CRUD at `/settings/values` (`settings/router.py:28-61`) stays for one release behind a `deprecated=true` flag, then returns `410` with a `Link` header to the typed endpoints. The `ResourcePage` UI keeps working during M4.

### 6.2 Sequences & numbering

| Endpoint | Verb | Permission | Purpose |
|---|---|---|---|
| `/settings/sequences` | GET/POST/PATCH/DELETE | `settings.sequence.*` | CRUD (now with pattern/FY/quota fields + config-time validation) |
| `/settings/sequences/{key}/preview` | POST | `settings.sequence.read` | `peek` — next rendered number, **non-consuming** |
| `/settings/sequences/{key}/status` | GET | `settings.sequence.read` | current FY, next number, allocated this period, open blocks, last allocated at |
| `/settings/sequences/{key}/allocate` | POST | `settings.sequence.allocate` | atomic allocation (internal callers; replaces `/next`) |
| `/settings/sequences/{key}/blocks` | POST | `settings.sequence.allocate` | reserve offline block |
| `/settings/blocks/{id}/return` | POST | `settings.sequence.allocate` | return unused tail |
| `/settings/allocations/{id}/void` | POST | `settings.sequence.update` | void with reason code (feeds GSTR-1 reconciliation) |
| `/settings/sequences/{key}/next` | POST | — | **deprecated** → `410` after M3; was `router.py:64` |
| `/settings/reports/numbering/gaps` | GET | `system.audit.read` | gap report (series, FY, reason) + CSV export |
| `/settings/reports/numbering/usage` | GET | `system.audit.read` | allocated per series/FY, manual overrides, block usage |

### 6.3 Error taxonomy (stable codes, so the UI can act)

| HTTP | Code | When |
|---|---|---|
| 422 | `settings.unknown_key` | key not in registry (S-REG-1) |
| 422 | `settings.type_mismatch` / `settings.validation_failed` | value fails the descriptor's type/min/max/regex/choices |
| 409 | `settings.conflict` | `version` mismatch (concurrent edit) |
| 409 | `settings.immutable` | key locked by `immutable_after` |
| 403 | `settings.approval_required` | critical key, caller not an approver |
| 422 | `settings.deploy_only` | attempt to write an env-owned key |
| 403 | `settings.secret_plaintext_read` | any attempt to read a secret value |
| 422 | `numbering.series_missing` | no active series for `(doc_type, branch, period)` — SAP parity, hard block |
| 409 | `numbering.period_closed` | FY period closed |
| 409 | `numbering.duplicate` | rendered number already allocated |
| 409 | `numbering.sequence_locked` | config change after first allocation |
| 422 | `numbering.pattern_invalid` / `pattern_too_long` | config-time validation (§5.4) |
| 409 | `numbering.busy` | lock timeout after retries (safe to retry) |
| 403 | `numbering.manual_forbidden` | manual number without `settings.sequence.manual` |

---

## 7. Business rules (extends `15-SETTINGS.md` SE-01…07)

| ID | Rule | Test |
|---|---|---|
| **SE-01** | Allocation is atomic: one `UPDATE … RETURNING`; no two allocations ever return the same number | 100-concurrent test → 100 distinct |
| **SE-02** | Gaps are permitted but **never unexplained**: every consumed number has a ledger row, and every unused number is either absent (future) or void with a reason | gap report reconciles ledger ↔ documents |
| **SE-03** | Every human-facing document number comes from `NumberSequenceService`; `core/numbering.py` is deleted and cannot be re-imported (lint gate) | grep test in CI |
| **SE-04** | Series reset per `reset_policy`; every allocation carries `fiscal_year`; backdated documents draw from **their own** FY series | FY rollover + backdate tests |
| **SE-05** | Secrets are AES-256-GCM encrypted at rest, never returned by any endpoint, masked (`sk_••••4f2a`) in UI, `__redacted__` in audit, and rotated inside a window | secret-leak test scans all responses + audit rows |
| **SE-06** | `pattern` uses an allow-listed token grammar rendered by substitution (never `str.format`); unknown tokens and oversized worst cases are rejected at save | parser fuzz + property test |
| **SE-07** | Every settings change is audited with actor, time, before, after and reason (reason mandatory for `critical`) | audit assertion per write |
| **SE-08** | Only registry keys are writable; writes to unregistered keys are 422 | `POST` unknown key → 422 |
| **SE-09** | Reads never fail the business path: invalid/missing values resolve to the descriptor default and log once per hour | corrupt value + post invoice → succeeds on default |
| **SE-10** | Precedence is the descriptor's declared scope order; a given `(key, scope)` has exactly one row | resolution matrix test |
| **SE-11** | `critical` settings require reason + approver ≠ actor; approval is itself audited | self-approval → 403 |
| **SE-12** | `deploy_only` keys are readable and never API-writable | write → 422 |
| **SE-13** | `immutable_after` keys (`currency`, `fiscal.start_month`, `valuation_method`) reject changes once the named milestone is reached; changing them needs a new legal entity, not a setting | change after first posting → 409 |
| **SE-14** | A series configuration is frozen after its first allocation (`implementation`, `pattern`, `reset_policy`, `padding`) | edit → 409 `sequence_locked` |
| **SE-15** | No active series for `(doc_type, branch, period)` blocks document creation with a clear error — never a silent fallback | missing series → 422 |
| **SE-16** | Document numbers are computed from the **document date**'s FY, not server time | backdated create |
| **SE-17** | GST document numbers satisfy ≤16 chars, `^[A-Z0-9\-/]+$`, uppercase, and (when `irp_safe`) no leading `0`/`-`/`/` — enforced at save **and** at render | profile tests per doc_type |
| **SE-18** | A rendered number is unique per `(tenant, doc_type, fiscal_year)` and additionally unique on the document table itself | duplicate attempt → 409, DB index asserts |
| **SE-19** | Manual numbers need `settings.sequence.manual`, satisfy the channel profile, and are ledgered as `manual` with a reason | manual duplicate → 409 |
| **SE-20** | Offline blocks are reserved by advancing the counter; unused tails are returned as declared gaps | block reserve/return round trip |
| **SE-21** | `idempotency_key` replays return the same number with `replayed=true`; the same key with different params is a 409 | double-submit test |
| **SE-22** | Settings reads are served from the resolved config cache and invalidated by `config_version`; no module performs its own `select(AppSetting)` | lint + cache-invalidation test |

---

## 8. Workflows

### 8.1 A document gets its number (happy path, standard mode)

```
POST /sales/orders
  └─ NumberSequenceService.allocate(key="sales_order", on_date=order.date)
       ├─ ensure_period(tenant, sales_order, fy(order.date))        [INSERT … ON CONFLICT]
       ├─ UPDATE number_sequence_periods SET next_number += 1 … RETURNING   [autonomous commit]
       ├─ render pattern "SO/{fy}/{seq:05}" → "SO/25-26/00042"
       ├─ INSERT number_allocations(status='allocated', document_type='sales_order')
       └─ return AllocatedNumber
  └─ SalesOrder(number="SO/25-26/00042", …) inserted in the business transaction
  └─ after flush: allocations.commit(allocation_id, document_id)      → status='committed'
  └─ publish sales_order.created
```

If the business transaction fails after allocation: the ledger row stays `allocated/uncommitted`, the number is a declared gap, and a sweeper (M5) marks rows older than 24 h with no document as `void / abandoned`. Nothing is reused — no duplicates, ever.

### 8.2 Fiscal-year rollover (1 April)

1. Beat job (7 days out) creates the next period at `start_number`, emits `numbering.period_opened`, notifies admins ("FY 2026-27 series ready: INV/26-27/001").
2. Finance closes the old period (`01` period close) → `number_sequence_periods.status='closed'`.
3. First April invoice resolves `fy = 2026-27`, `ensure_period` finds the pre-created row, allocates `1`.
4. Any attempt to post a March-dated invoice from that series now returns `409 numbering.period_closed` (the numbering twin of the period lock).
5. Reports show both FY numbers side by side; the FY label is inside the rendered number, so it is self-documenting.

### 8.3 Cancel / void

```
sales cancel invoice INV/25-26/00042
  → NumberSequenceService.void(rendered, key='invoice', reason_code='cancelled',
                               reason_text='customer rejected; credit note INV/25-26/00051')
  → allocation.status='void', document link retained
  → gap report shows 00042 as declared/cancelled → GSTR-1 cancelled-invoice export
```
Gap without a reason is what triggers a GST query; gap with a reason + credit-note reference is a closed book.

### 8.4 Critical setting change (four eyes)

```
PUT /settings/values/procurement.approval.threshold {value: 500000, reason: "board resolution 2026-11"}
  → descriptor.critical = true, actor is not approver → 202 {approval_state: 'pending', id}
  → approver (different user, holds system.settings.manage) → POST /settings/changes/{id}/approve
  → value applied, config_version bumped, two audit rows (request + approval)
```

### 8.5 Secret rotation window

```
PUT  /settings/secrets/razorpay.key_secret        → active(v1)
POST /settings/secrets/razorpay.key_secret/rotate → pending(v2); previous = v1, expires +72 h
integrations read both for N hours (dual-read window; outbound calls use v2)
POST /settings/secrets/razorpay.key_secret/commit → active(v2), previous wiped
   or /rollback within the window              → active(v1), pending discarded
```
Matches `15-SETTINGS.md` §4.1 exactly and gives the integrations module (`12`) a safe credential cut-over. Any read of a secret in an API response is a 403 (§6.3), so a leaked response cannot carry ciphertext.

### 8.6 New tenant provisioning

`seed.py` gains `provision_tenant_defaults(tenant)`:
- writes the ~45 registry defaults as **explicit tenant rows** (so a later registry default change does not silently retune a live tenant),
- creates active series for the 12 v1 doc types with GST-safe patterns (`INV/{fy}/{seq:05}`, `PO/{fy}/{seq:05}`, `JE/{fy}/{seq:05}`, …) — note the pattern must be ≤16 chars worst case for invoices,
- creates the current FY period,
- stages the tenant for the "complete your organisation profile" checklist shown on first login (GSTIN, state code, FY start, currency).

### 8.7 Branch / multi-GSTIN series setup (SAP "series per branch")

1. Admin creates a series with `branch_id`/`gstin` and pattern including `{branch}` (e.g. `BLR/{fy}/{seq:04}`).
2. The allocator selects the series by `(key, branch_id)` of the document's branch, falling back to the tenant-wide series (`branch_id IS NULL`) only if `settings.sequence.allow_branch_fallback` is true (default **false**, per SE-15's no-silent-fallback stance).
3. Per-series status shows each branch's consumption, so a branch running out of a 4-digit range is visible before it fails.

---

## 9. RBAC, audit and reporting

### 9.1 Permission codes to add (`core/permissions_catalog.py`)

| Code | Group | Used by |
|---|---|---|
| `settings.sequence.allocate` | settings | internal API/engine; not granted to human roles by default |
| `settings.sequence.manual` | settings | SAP `Document Manual Numbering` equivalent — accountant only |
| `settings.secret.manage` | system | secret write/rotate (existing `system.settings.manage` also accepted) |
| `settings.change.approve` | system | approver for critical settings |

Existing and reused: `settings.setting.{read,create,update,delete}`, `settings.sequence.{read,create,update,delete}`, `system.settings.manage`, `system.audit.read`. Role templates: `admin` gets everything; `accountant` gets `settings.setting.read/update` (non-critical), `settings.sequence.read`, `settings.sequence.manual`; `manager` gets `settings.setting.read` only; nothing else gets write access — a `sales` role must not be able to change tax behaviour.

### 9.2 Audit points (all through `core/audit.py::record_audit`)

| Event | `action` | `entity` | Notes |
|---|---|---|---|
| Setting written | `settings.setting.update` | `AppSetting` | `changes` carries `{key, old, new, scope, reason}` (sanitised) |
| Setting unset | `settings.setting.unset` | `AppSetting` | |
| Critical change requested/approved/rejected | `settings.change.request/approve/reject` | `SettingChange` | approver ≠ actor |
| Secret written/rotated/committed/rolled back | `settings.secret.rotate` | `SettingSecret` | value always `__redacted__` |
| Sequence config changed | `settings.sequence.update` | `NumberSequence` | before/after pattern |
| Manual number used | `numbering.manual` | `NumberAllocation` | who, which number, why |
| Number voided | `numbering.void` | `NumberAllocation` | reason code |
| Block issued/returned | `numbering.block.*` | `SequenceBlock` | device attribution |
| Missing series blocked a document | `numbering.blocked` | — | diagnostics for support |

### 9.3 Reports (module `13` consumes, we serve)

1. **Settings coverage** — % of registry keys carrying an explicit tenant value (target: 100 % of `critical` keys before go-live).
2. **Critical-change log** — every approved financial-policy change, for the auditor.
3. **Numbering usage** — per series/FY: allocated, void, manual, open blocks.
4. **Gap report** — declared vs unexplained gaps (the GSTR-1 reconciliation input).
5. **Secret age** — days since rotation per secret (warn > 90).
6. **Drift detector** — settings rows whose `checksum` no longer matches `canonical_json(value)` (out-of-band SQL edits).

---

## 10. Frontend / UX plan (`frontend/src/pages/settings/` — directory currently empty)

Current state: `pages/resources/settings.jsx` renders two generic `ResourcePage`s (a key/value JSON textarea and a sequence table). That is a developer tool, not an admin product. Target: a real settings hub, and it is the *only* place a customer experiences "configuration" — so it carries a lot of the product's perceived quality.

```
/settings                       → hub: Organisation · Localisation · Modules & features ·
                                  Numbering · Notifications · Security · Secrets · Change history
/settings/organisation          → company profile form (name, legal name, address, GSTIN/PAN/CIN,
                                  state code select with GST state list) + "complete your profile" checklist
/settings/localisation          → currency, timezone, date/number format, FY start month (locked badge
                                  once first posting exists), live preview of formatted amount/date
/settings/modules               → feature/module toggles with a note that the API stays live (Zoho parity)
/settings/numbering             → series list (key, pattern, next, FY, status) with:
                                    · inline pattern builder (token chips, live preview: "SO/25-26/00042")
                                    · warning banner when worst-case > max_length for the doc type
                                    · preview button (non-consuming), status drawer (allocated this FY)
                                    · locked state after first allocation (SE-14) with an explanation
                                    · per-branch / per-GSTIN tab
/settings/numbering/gaps        → gap report + CSV export + void-with-reason dialog
/settings/numbering/blocks      → POS device blocks, expiry, return action
/settings/secrets               → list with mask + last rotated; rotate dialog explains the window
/settings/history               → change history table (key, old → new, actor, reason, time) with filters
```

UX rules that matter:
- **Typed editors, not JSON.** Each descriptor renders its native control (toggle, number, select, currency, regex-validated text, masked secret). No free-form JSON anywhere except `type=json` keys with a schema.
- **Explain the blast radius.** Critical settings show a persistent inline note ("this changes tax treatment for every new invoice from now on") and require a reason; the save button is disabled until one is typed.
- **Show provenance.** Every field shows where its current value came from (default / env / tenant / branch / user) — this kills the "why is it 18 % here and 12 % there" support class.
- **Preview before commit** for numbering (peek) and for formats (live sample).
- **Locked states are explained**, never greyed-out mysteries ("locked because INV/25-26/00042 was issued — create a new series to change the format").
- **Mobile-first**: this is where SAP-class products lose the SMB; the numbering preview and toggles must work at 390 px.
- Reuse existing shell components (`ResourcePage`, `cells`, `lib/format`) so the module looks native; add only the pattern builder and the diff drawer as new components.

---

## 11. Implementation milestones

Ordered by dependency and by blast radius. **Numbering first** — it is `99` Phase 0.5 and five modules are blocked on it; the settings registry is Phase 1 hygiene.

Mapping to the design doc: 15A **M1 → `15-SETTINGS` M1**, 15A **M2 → M1/SE-04 extension**, 15A **M3 → `15-SETTINGS` M2**, 15A **M5 → `15-SETTINGS` M3**.

### M1 — Atomic allocator, pattern engine, channels (must, ~5–7 days)

| # | Work | Files |
|---|---|---|
| 1 | Migration `0015a_numbering_engine`: `number_sequence_periods`, `number_allocations`, `number_sequences` new columns, deprecated `next_number`, indexes | `backend/alembic/versions/` |
| 2 | Models + enums for the three tables; `SequencePeriod`, `NumberAllocation` | `backend/app/modules/settings/models.py` |
| 3 | `NumberSequenceService.allocate/peek/status/ensure_period` with `UPDATE … RETURNING`, retry policy, idempotency | `backend/app/modules/settings/numbering.py` |
| 4 | Pattern parser + renderer + worst-case validator + doc-type profiles | `backend/app/modules/settings/patterns.py` |
| 5 | `POST /sequences/{key}/preview`, `/status`, `/allocate`; deprecate `/next` | `settings/router.py`, `schemas.py` |
| 6 | Permission codes + catalog entries | `core/permissions_catalog.py` |
| 7 | Tests: 100-concurrent, idempotency, channel profiles, pattern fuzz | `backend/app/tests/test_settings_numbering.py` (new) |

**Acceptance:** 100 concurrent `allocate()` → 100 distinct numbers; preview does not consume; a 17-char invoice pattern is rejected at save; `/next` marked deprecated; allocation p95 < 20 ms locally.

### M2 — FY rollover, branches, voids, blocks (~4–5 days)

- `ensure_period` + beat job `open_next_periods` (7 days ahead), `closing` on finance period close, `409 numbering.period_closed`.
- Branch/GSTIN series selection + `allow_branch_fallback` (default false).
- `void()` + `reason_code` enum + gap report endpoints.
- `reserve_block` / `return_block` + block expiry sweeper + `numbering.block.*` audit.
- **Acceptance:** FY rollover test (Mar 31 → Apr 1 resets at `start_number`, both FY unique); backdated doc draws its own FY; closed period blocks; block reserve/return leaves declared gaps only.

### M3 — Migrate every module, delete `core/numbering.py` (~4–6 days)

| Order | Module | Call sites |
|---|---|---|
| 1 | Finance (`service.py` 12 sites, `tally.py` 1) | JE, INV, payroll/assets/payment JEs |
| 2 | Sales (`router.py:262,393,403`) | SO, DC, INV |
| 3 | POS (`router.py:205,210,314`) + block reservation | PS, SO, INV |
| 4 | Procurement (`router.py:176,269`) | PO, GRN |
| 5 | Support/Projects via `core/crud.py` `number_field` — replace the `crud.py:126-134` hook with the engine; delete `projects/services.py:545-591` bespoke allocator | TKT, PRJ, PRJ-T, SPR, PR, DC, INV |
| 6 | Add per-table unique `(tenant_id, number)` constraints + indexes | module models + migration |

Then: delete `backend/app/core/numbering.py`, add the CI lint (`grep -r "core.numbering" backend/app` must be empty), and update `core/crud.py` to call `NumberSequenceService` via the `number_prefix`→`key` mapping table.

**Acceptance:** SE-03 grep test green; no duplicate numbers under a 100-way mixed-module concurrency test; prefix collision (`SO` from sales vs POS) resolved by distinct keys.

### M4 — Settings registry, typed values, resolution, cache, audit (~6–8 days)

- `registry.py` with the §4.5 catalogue (~45 descriptors), `service.py` resolver/cache/provenance, `config_version` on tenant + `settings.changed` event.
- Migration `0015b_settings_registry`: `app_settings` columns, `setting_changes`, scope-aware unique index, backfill of the 4 legacy keys into the new keys with `deprecated_alias`.
- Typed endpoints (§6.1), critical-change approval, immutable-after rules, `deploy_only`.
- Wire the consumers: `finance` (rounding, tax tracking mode, override), `sales` (tax-inclusive, discount level, credit limit), `procurement` (approval threshold, match tolerance), `hr` (statutory rates, cut-off), `support` (SLA clocks), `inventory` (valuation, negative stock), `localization` (currency/timezone/format), `features.*` → nav.
- **Acceptance:** unknown key → 422; bad type → 422; critical without approver → 403; corrupted row → posting succeeds on default (SE-09); cache invalidates within 1 s of write; no `AppSetting` import outside `modules/settings`; effective-config endpoint returns provenance for all 45 keys.

### M5 — Secrets vault + rotation window (~3–4 days)

- `SETTINGS_ENCRYPTION_KEY` (+ `SETTINGS_ENCRYPTION_KEY_VERSION`) in `core/config.py`; AES-256-GCM helper `core/crypto.py` (new; `core/security.py` has hashing only).
- `setting_secrets` table, masked read API, `rotate/commit/rollback` state machine (§4.1/§8.5), dual-read window for consumers (`12`), `REDACTED_KEYS` extension, secret-leak test that scans every response body and every audit row for plaintext.
- **Acceptance:** ciphertext never leaves the DB; rotation window works; rollback within window restores; audit redacted; key-version rotation documented in a runbook.

### M6 — Admin UX, provisioning, reporting (~5–7 days)

- Settings hub + 8 sub-pages (§10), pattern builder with live preview and worst-case warning, gap report + CSV, block console, history drawer, completion checklist.
- `provision_tenant_defaults()` in `db/seed.py`; per-branch series setup; reports §9.3.
- Playwright: create invoice → see the number → change the due-days setting → new invoice reflects it → rotation of a secret → history shows both.
- **Acceptance:** the DoD checklist below is fully ticked; two Playwright journeys green; numbering screen usable at 390 px.

### Critical path and effort

```
M1 ──> M2 ──> M3 ──┬──> M4 ──> M5 ──> M6
 (5-7) (4-5) (4-6)     (6-8)   (3-4)   (5-7)
```
`M4` can start in parallel with `M3` once `M1` is merged (different files, no migration conflict if `0015a`/`0015b` are separate revisions). Total ≈ 28–37 engineer-days; M1 alone (~1 week) removes the single largest correctness risk in the product.

---

## 12. Test plan

| Layer | Test | File |
|---|---|---|
| Unit | Pattern parse/render for every token; unknown token rejected; unbalanced braces; worst-case length; lowercase/leading-zero IRP rules | `tests/test_settings_patterns.py` |
| Property | Hypothesis: for random patterns + numbers, `render()` always matches `allowed_chars_regex` and never exceeds `max_length`, or raises at config time | same |
| Unit | Resolution precedence matrix (default → env → tenant → branch → user), scope-not-declared rejection, deploy_only, immutable_after | `tests/test_settings_registry.py` |
| Unit | Type coercion + validation for all 9 value types; corrupted value falls back to default (SE-09) | same |
| Integration | `allocate` → document insert → `commit` → ledger status; void with reason; gap report output | `tests/test_settings_numbering.py` |
| **Concurrency** | `asyncio.gather(*[allocate() × 100])` → 100 unique; mixed-module 100-way; same-key contention with `timeout` | same |
| Concurrency | `nogap` mode: parallel allocations are consecutive with **no** duplicates across 50 attempts | same |
| Idempotency | Same `idempotency_key` twice → same number, `replayed=true`; different payload same key → 409 | same |
| FY | Boundary 31 Mar/1 Apr; backdated doc; closed-period block; pre-created period used; two FY numbers both unique | `tests/test_settings_fy.py` |
| Blocks | Reserve → partial use → return; expiry sweeper; gap attribution to device | same |
| Security | Secret never in any response/audit/log; masked list; rotation window; commit/rollback; ciphertext not decryptable without key version | `tests/test_settings_secrets.py` |
| Compliance | For every `gst_*` doc type: rendered length ≤ 16, charset match, uppercase, no leading zero (IRP) | `tests/test_settings_compliance.py` |
| Static | CI gate: `grep -r "core.numbering" backend/app` empty; no `AppSetting` import outside `modules/settings` | `scripts/lint_settings.sh` |
| API | All new endpoints return the documented error codes for the negative cases in §6.3 | `tests/test_settings_api.py` |
| E2E | Playwright: numbering preview → invoice created with that number → settings change → effect visible → history row | `frontend/e2e/settings.spec.ts` |
| Perf | 100k-row gap report < 300 ms (matches `00 §9` list-endpoint p95) | benchmark script |

**Verified 2026-11-21:** backend 134 passed, frontend 29 passed, Playwright 3 passed, Alembic replay passed, lint/secret-leak/OpenAPI snapshot gates passed, synthetic gap p95 162.19 ms and live endpoint gap p95 272.84 ms.

---

## 13. Migration & rollout

1. **Additive migration only.** `0015a` and `0015b` add tables/columns and backfill; nothing is dropped. `number_sequences.next_number` stays as a deprecated mirror until M3 is fully rolled out.
2. **Backfill (dry-run first):** for each existing series key, compute `max(existing suffix)` across the owning tables for that prefix, set the current-FY period `next_number = max + 1`, and assert `max < 10**padding`. Report any collision (e.g. two `SO-00012` from sales and POS) as a **blocking** finding with the offending rows — deduplication is a business decision, not a script decision.
3. **Feature flag:** `features.numbering.engine` (default *on* in dev, *off* in prod for one release). When off, the legacy path is untouched; when on, all migrated modules use the engine. This makes M3 reversible per module.
4. **Rollout order:** Finance → Sales → POS → Procurement → Support/Projects. Finance first because numbering underpins the ledger and reversals (`01` I4).
5. **Backfill of settings:** the 4 legacy keys are re-projected onto registry keys with `deprecated_alias` reads for one release; `provision_tenant_defaults` runs for new tenants only (existing tenants get explicit rows via a one-off `settings:backfill` command so later default changes don't silently retune them).
6. **Rollback:** disable the flag → legacy allocation resumes (numbers already issued stay valid; the ledger keeps them). Never roll back by deleting ledger rows.
7. **Communication:** an in-app note to accountants before FY rollover and before the first `sequence_locked` state appears.

---

## 14. Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Duplicate document numbers ship | audit chaos, GST exposure, wrong credit notes | M1 before any concurrency; unique index on documents (§5.1); 100-way concurrency test in CI |
| Sequential migration done partially | two mechanisms live, silent divergence | flag per module + CI lint gate + `99` Phase 1.2 acceptance |
| FY rollover missed | numbers wrong after 1 April | lazy `ensure_period` (never depends on the job) + pre-created periods + rollover test + admin notice |
| Pattern change on a live series re-issues numbers | duplicates retroactively (the odoo#302782 class of bug) | `status='locked'` after first allocation (SE-14) + new-series cut-over procedure |
| Settings read path becomes a hidden tax engine | "why is the invoice 12 %?" support load | provenance in every response, single resolver, no direct `AppSetting` reads (SE-22) |
| Free-JSON registry entries creep back | untyped config returns | S-REG-1 (422 on unknown key) + `type=json` requires a schema |
| Secret in logs/audit | credential leak | ciphertext-only storage, masked reads, redaction test, `403` on plaintext read |
| POS offline blocks never returned | invisible large gaps | block expiry sweeper + unreturned-block report + device attribution |
| Backfill finds an existing duplicate | cannot migrate cleanly | dry-run report as a blocking finding, dedupe decision by finance before M3 |
| Approval workflow becomes friction | admins bypass it by SQL | approvals only for `critical` keys (~14 of 45), self-service for the rest; drift detector catches SQL edits |

---

## 15. Definition of Done

- [x] Alembic blank-DB `upgrade head` + double seed replay green; two replay fixes applied (downgrade/reversibility not part of this gate)
- [x] Core SE-01…SE-22 behavior covered by the full 134-test backend suite; remaining named gaps are listed in §0A
- [ ] 100-concurrent allocation test green; mixed-module concurrency green (30-way uniqueness test is green)
- [ ] Pattern parser has a Hypothesis property test; worst-case-length guard rejects the 17-char invoice case
- [x] GST channel profiles verified for every `gst_*` doc type (≤16, charset, uppercase, IRP leading rules)
- [ ] Dedicated FY rollover + backdated + closed-period acceptance tests green
- [x] No module imports `core/numbering.py`; file deleted; CI lint gate enforced
- [ ] Unique `(tenant_id, number)` index on every numbered table was not re-audited in this pass
- [x] Registry rejects unknown keys and bad types; corrupted value falls back with a warning
- [x] Critical-change approval with self-approval block; audit rows asserted
- [x] Secrets encrypted, masked, rotatable with window; global leak scan green
- [ ] Permission codes registered in `permissions_catalog.py` and nav gated by `settings.secret.manage`; feature-flag-driven navigation not re-audited
- [x] Settings hub + numbering console usable at 390 px; pattern live preview; locked-state explanations
- [x] Two Playwright journeys green (numbering + settings change), plus settings smoke (3 tests total)
- [x] Gap report p95 < 300 ms at 100k rows verified against the real endpoint (272.84 ms)
- [x] Runbook: FY rollover, sweeps, series cut-over, secret rotation, block recovery, rollback via flag and performance checks
- [x] `15-SETTINGS.md` §2/§18, `PLAN-CONFORMANCE-CHECKLIST.md` row 192 and `docs/modules/README.md` are consistent with the verification status

---

## 16. Open questions

| # | Question | Owner-type | Default if unanswered |
|---|---|---|---|
| Q1 | Should GST invoices default to `standard` (gapped, fast) or `nogap` (consecutive, slow)? | finance/statutory | `standard` + declared-gap ledger (Rule 46 requires *consecutive serial in a series*, and legislation itself contemplates cancellation gaps) |
| Q2 | Is a per-GSTIN series mandatory at go-live, or is one tenant-wide series acceptable for v1? | finance | tenant-wide series in v1, schema supports per-branch from day one |
| Q3 | Do we allow backdated allocation into a *closed but un-locked* FY period? | finance | no — closing the period closes numbering with it |
| Q4 | What is the default offline block size for POS? | POS/ops | 100 (configurable `pos.offline.block_size`) |
| Q5 | Where do legal-entity-level overrides live (multi-entity): a second tenant or a `branch` scope? | architecture | `branch` scope now; a real `legal_entity` scope is a future enum value, no schema change |
| Q6 | Should settings support per-role *views* (hide a key from a role even if readable)? | product | no in v1 — permissions gate writes; all reads are tenant-consistent |
| Q7 | Does the auditor want a signed/exportable numbering register (series, ranges, voids) per FY? | audit | yes — the gap report CSV is the v1 artefact; a signed export is M6+ if demanded |

---

## 17. Appendix — the "why" behind the four decisions that matter most

1. **Registry over free-form keys.** Every benchmark product that survives customer support at scale constrains configuration to declared, typed, validated keys. Unconstrained JSON config is the single most common source of "it works on my tenant" bugs. S-REG-1 is the cheapest possible insurance.
2. **Config / counter / ledger separation.** SAP's period indicators, Odoo's date ranges and Zoho's FY numbering all reduce to "the counter is per period, not per series". Without the ledger nothing can distinguish "gap because cancelled" from "gap because lost number" — which is exactly the question a GST auditor asks.
3. **`UPDATE … RETURNING` as the only primitive.** Not `SELECT FOR UPDATE` + Python increment (two round-trips, accidentally-racy if the transaction isolation is ever changed), not an advisory lock (leaks on crash), not an application mutex (breaks with N workers). One statement, one lock, one truth.
4. **Immutability after first use.** Sequences and financial-policy settings are *structural* state. Both Odoo's public bug and SAP's "cannot raise the starting number after posting" rule exist because changing structure under live data corrupts history. Locking is a feature.
