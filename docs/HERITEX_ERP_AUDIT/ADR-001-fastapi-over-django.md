# ADR-001 — Build the Hertex ERP backend on FastAPI + SQLAlchemy 2.0 instead of Django 5.2

- **Status:** Proposed (needs sign-off — see "Decision required")
- **Date:** 2026-07-17
- **Deciders:** CTO, backend owners of `bytehive_business_backend`, `tzahu_crm`, `hertex-erp`
- **Supersedes:** Ground rule #1 of `Hertex-ERP-Technical-Implementation-Plan.md` §0 ("One PostgreSQL database, one Django project")
- **Related:** `Hertex-ERP-End-to-End-Implementation-Plan.md` §7 (architecture), §12 risk 3 (stack fragmentation); `Hertex-Best-Product-Plan.md` §2.1 (single-database proof)

---

## Context

The technical implementation plan is explicit and repeated: build every new ERP module as a new **Django app inside the existing ByteHive Django monolith** (`bytehive_business_backend`), because the product's only structural moat is *one database, one project* — the thing Zoho cannot copy (§7 "Keep the single shared PostgreSQL database as sacred", §12 risk 3 "Stack fragmentation").

In practice, `hertex-erp/` has been started as a **greenfield FastAPI + SQLAlchemy 2.0 (async) + Alembic + Pydantic v2** service. It preserves the one-Postgres rule but breaks the one-project rule. The repository already contains three ERP/CRM backends:

| Backend | Stack | Size | Role today |
|---|---|---|---|
| `bytehive_business_backend` | Django 5.2 + DRF | ~64k LOC | Live-ish product (CRM, GST invoicing, inventory, HR Phase 1) |
| `tzahu_crm` | Django 5.1 + DRF + Celery + OTel | ~18k LOC | Separate AI-first CRM product |
| `hertex-erp` | FastAPI + SQLAlchemy 2.0 async | ~6.7k LOC | This decision |

So the plan's warning has already materialised: the stack question was not resolved explicitly, and drift decided it. This ADR exists to make the drift an explicit, reversible decision rather than an accident.

---

## Decision

**Adopt FastAPI + SQLAlchemy 2.0 as the forward stack for `hertex-erp`, and treat `hertex-erp` as the target backend for the *new* modules** (Finance GL, Procurement, Warehouse, Sales, POS, Integrations, AI, Analytics), while `bytehive_business_backend` stays the system of record for the modules already shipped there (CRM, GST invoicing, Inventory, HR) until an explicit cutover.

The single-Postgres principle is **kept and treated as non-negotiable**; the "one Django project" rule is **retired** in favour of "one database, one deployable API surface per domain."

### Conditions attached to this decision (all are release blockers, not nice-to-haves)

1. **One schema, one migration owner.** `hertex-erp` must not create a second copy of any table that ByteHive already owns. Shared entities (`products`, `customers`, `users`) are either raw-table-mapped or exposed via a single canonical service. Alembic is the migration owner for all `hertex-erp`-owned tables, and a written table-ownership map must exist before the second module goes to production.
2. **The moat demo must still work.** Best-Product Plan §2.1 requires a live demo where one number updates in three screens with no refresh. This is a UI/invalidation promise; it is stack-independent, but it must be demonstrated end-to-end before this ADR is treated as validated.
3. **RBAC and audit become cross-stack.** Two ORMs means two implementations of tenancy and audit. `hertex-erp`'s `permissions_catalog.py` is currently the only single source of truth for permission codes; it must be adopted as the canonical catalog, or duplicated deliberately and versioned.
4. **No third stack.** `HertexFlow`'s NestJS/Prisma question (Strategic Plan §12 risk 3) must be resolved *toward a stack already in this table*. Adding a fourth backend would void this ADR.

---

## Rationale (what FastAPI actually buys here)

- **Async-first fit.** Real-time voice/WhatsApp (Engage) and POS checkout are latency-sensitive; async SQLAlchemy avoids the sync-Django/FastAPI bridge that would otherwise appear at the boundary.
- **Typed contracts.** Pydantic v2 + FastAPI gives request/response schemas that double as the OpenAPI contract the plan requires (`Technical Plan §0 rule 3`), with less boilerplate than DRF serializers + drf-spectacular.
- **The scaffolding is already generic.** `app/core/crud.py::build_crud_router` gives every module tenant scoping, pagination, search, filters, soft delete and audit in one call; `app/db/base.py::TenantBaseModel` enforces the shared-field rule structurally. Rebuilding this in DRF would cost weeks for no product gain.
- **Greenfield freedom.** The plan's Phase 0 asks for a schema freeze *before* Phase 1 code. Doing that on a clean schema avoids the migration gymnastics the plan itself warns about (§9 Phase 0).

## Rationale against (what this costs)

- **The plan says not to.** Ground rule #1 is a deliberate architectural choice, and the plan's competitive thesis is framed around Zoho's fragmentation. Two ORMs is a smaller version of the same failure mode; the burden of proof is on this ADR, not on the plan.
- **Duplicated platform work.** RBAC, audit hooks, eventing and document numbering now exist twice (Django apps + `app/core/`). Any policy change must land twice.
- **No event bus in practice.** `app/core/events.py` is an in-process `defaultdict` of asyncio handlers with **zero subscribers** in the codebase; the plan wanted Celery/Redis fan-out (§6, §7). Django+`celery` would have given this for free.
- **Alembic is empty.** `alembic/versions/` contains no migrations, so the "clean schema" advantage is currently unrealised — nothing has been exercised against a database at all.
- **Sunk cost in the alternative.** ~64k LOC of Django already contains working GST invoicing and inventory. Anything in `hertex-erp` that re-implements those is pure duplication.

---

## Alternatives considered

| Option | Outcome |
|---|---|
| **A. Follow the plan literally** — new Django apps in `bytehive_business_backend` | Lowest architectural risk; reuses RBAC, audit, Celery, admin, and GST work. Loses: async ergonomics, Pydantic contracts, and the greenfield schema window. **Recommended if the team's Django capacity is real.** |
| **B. FastAPI under strict conditions (this ADR, as proposed)** | Keeps the async/typed advantages and the existing ~6.7k LOC of scaffolding; accepts duplicated platform code and a table-ownership burden. |
| **C. Keep `hertex-erp` as a spike/thin vertical slice only** (e.g. Finance GL + Procurement + POS), never a full ERP | Lowest cost, bounded risk, tests whether FastAPI actually pays off. Does **not** require retiring ground rule #1. |
| **D. Fold `hertex-erp` into `tzahu_crm` (already Django + Celery + OTel)** | Consolidates to two backends instead of three; inherits observability. Largely option A with a different host project. |

---

## Decision required

This ADR is **Proposed**, not Accepted. Three questions must be answered by a human, in this order:

1. **Is `hertex-erp` the target stack, or a spike?** (Options A/B vs C.) If it is a spike, this ADR should be rejected and `hertex-erp` scoped down to a vertical slice.
2. **Is `bytehive_business_backend` frozen, migrated, or run in parallel?** Nothing in the repo answers this, and it determines whether the table-ownership map is a documentation task or a data-migration project.
3. **Does FastAPI actually pay for itself here?** The evidence so far is a good scaffolding layer, zero migrations, zero tests, and zero event consumers. The honest test is one module taken to the plan's full DoD (migrations + DRF-equivalent endpoints + RBAC + Playwright happy-path + demo screen) on this stack before committing the remaining 17.

---

## Consequences if accepted

- `Hertex-ERP-Technical-Implementation-Plan.md` §0 rule 1 must be amended (that document is owned elsewhere; this ADR does not edit it).
- A `TABLE-OWNERSHIP.md` becomes a mandatory artefact before the second `hertex-erp` module reaches production.
- `permissions_catalog.py` is promoted to the canonical permission catalogue, or explicitly forked with a version marker.
- `HertexFlow`'s NestJS question must be answered with "no fourth stack".

## Consequences if rejected

- `hertex-erp` is reclassified as a bounded spike; only Option C's slice may continue.
- New module work returns to `bytehive_business_backend` as Django apps, per the plan.
- The 6.7k LOC of scaffolding becomes reference material rather than product code.

---

## References

- `Hertex-ERP-Technical-Implementation-Plan.md` §0 (ground rules 1–5), §7 (event bus), §12 (risk 3: stack fragmentation)
- `Hertex-ERP-End-to-End-Implementation-Plan.md` §7 (architecture), §12 risks 1–4
- `Hertex-Best-Product-Plan.md` §2.1 (single-database proof), §2.3 (Tally migration), §5 (how you'll know)
- `hertex-erp/docs/PLAN-CONFORMANCE-CHECKLIST.md` (current conformance state)
