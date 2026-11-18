# Project Management (09a) Runbook

Scope: the Projects module at `/api/v1/projects` (all paths below are relative to that base). API calls require a bearer token and the permission codes in `backend/app/core/permissions_catalog.py`; all reads and writes are tenant-scoped.

The `pm.*` flags listed in plan §16.2 are not runtime toggles in this build. Gate rollout with RBAC, route availability, and deployment sequencing instead.

## 1. Deploy

1. Freeze direct edits to legacy `actual_hours`; point users at time entries/timesheets.
2. In `backend/`, run: `.venv/bin/ruff check app scripts`, `.venv/bin/python -m pytest -q`, `.venv/bin/python -m alembic upgrade head`, `.venv/bin/python -m alembic check`, `.venv/bin/python scripts/check_openapi_snapshot.py`.
3. Confirm `alembic current` is `f4e2c8a7b913` (head). `alembic check` must report no `project*` drift; the known unrelated `finance_approvals`, `finance_vendor_payments`, `procurement_vendor_invoices`, and `sales_order_lines` drift is tracked separately and does not block PM.
4. In `frontend/`, run `npm run build` and `npm test`.
5. Deploy backend before frontend. Keep legacy project/task CRUD read-only during the pilot; re-enable only after the parallel period reconciles.
6. Smoke checks: `GET /health`, `GET /` (project list), `GET /reports/project-health`, `GET /reports/unbilled-wip`, `GET /outbox/stats`, `POST /outbox/dispatch` with a small limit, and one board/backlog/Gantt/workload screen in the frontend.

## 2. Rollback

1. Stop PM writes first: remove `projects.*` write permissions or take the frontend PM routes out of navigation; leave read routes available.
2. Roll back the application images to the previous version. Do not downgrade Alembic while PM rows exist; the migration is reversible on an empty PM dataset only.
3. Reverse any Finance documents through Finance (void/credit note), not by deleting PM rows. Leave time entries, approvals, billing lines, audit, and activity records in place.
4. Quiesce the outbox worker before rollback. Do not replay `billing.posted` or `invoice.paid` events after a financial reversal; reconcile links first.
5. Reopen the legacy `actual_hours` freeze only after confirming no duplicate billing was created during the pilot.

## 3. Parallel billing

1. Run one full billing period in both legacy and PM mode. During the parallel period, use `GET /billing/preview`, `GET /projects/{project_id}/unbilled`, and `GET /reports/unbilled-wip` only; do not post PM billing runs.
2. Confirm every source is an approved time entry, expense, or accepted milestone. Rejected/draft sources and already-invoiced sources must be absent; `POST /billing-runs` and post enforce the no-double-billing guard.
3. Compare PM preview totals to the legacy invoice by project, currency, tax code, and customer. Investigate gaps with `GET /reports/billing-leakage` and `GET /projects/{project_id}/costs`.
4. After Finance signs off on the tax mapping and invoice-line support, post in a controlled window with an `Idempotency-Key` header on `POST /billing-runs/{id}/post`. A repeat with the same key must not create a second invoice.
5. Verify the Finance invoice reference `PM-BILL:<idempotency_key>`, the `/invoice-links` row, and the profitability report. Record the reconciliation sign-off before enabling live PM billing.

## 4. Import correction

1. Stage with `POST /imports` (dry run), then read `GET /imports/{batch_id}`. Fix mapping/row errors in the source file and restage; never edit committed rows in place.
2. Only after the dry-run report is clean: `POST /imports/{batch_id}/approve`, then `POST /imports/{batch_id}/commit`.
3. Correction of a committed batch: `POST /imports/{batch_id}/rollback`. It marks rows rolled back and deletes only imported work items with no actual hours and no invoice link. Rows already touched by time or billing stay in place.
4. For touched rows, correct via normal transition/approval endpoints or a Finance reversal; never overwrite an audited transition or a Finance-linked record. Re-import only into a fresh batch and record the batch IDs in the incident ticket.

## 5. Finance reconciliation

1. Daily: compare `GET /reports/unbilled-wip` and `GET /reports/billing-leakage` against Finance AR openings; totals must match approved, uninvoiced sources.
2. After each post: confirm one `/invoice-links` row per billing run, matching gross, tax, total, and currency; confirm the Finance invoice and its journal are posted.
3. `invoice.paid` events update the invoice-link status and profitability. If a link remains open after payment, check outbox dispatch and the `invoice.paid` payload before editing the link.
4. Weekly: compare `GET /reports/profitability` and `GET /reports/budget-vs-actual` with Finance revenue/cost postings. WIP or margin drift means a missing invoice link or an unposted expense, not a ledger correction in Projects.
5. Corrections: reverse in Finance, leave PM audit rows, open a new billing run for the corrected amount, and document old/new invoice IDs. Do not reuse a source that is already linked to an invoice.

## 6. HR capacity cutover

1. Resolve the employee-to-user mapping queue first. No auto-assignment for unresolved records; capacity is only trustworthy when the HR employee/user map and leave ledger are live.
2. Refresh with `POST /resources/capacity/refresh`, then review `GET /resources/capacity` and `GET /resources/workload` for leave-adjusted availability and over-allocation signals.
3. Approve bookings through `POST /resource-bookings/{id}/approve`; overrides must have a named approver. Unapproved over-allocation is advisory only.
4. Confirm `employee.onboarded` creates the resource placeholder and `leave.approved` changes capacity; confirm `employee.exited` releases future bookings and routes open work through a human reassignment.
5. Verify cost-rate masking: roles without `projects.finance.read` see restricted values, not salary/cost rates, in workload and reports.

## 7. AI governance

1. Signals are read-only: `POST /ai/signals/refresh`, `GET /ai/signals`, `POST /ai/signals/{id}/review`. Each signal must expose its top features.
2. Actions follow propose -> review/reject -> execute -> reverse (`/ai/actions`, `/ai/actions/{id}/review`, `/reject`, `/execute`, `/reverse`). No autonomous execution; the approver and `on_behalf_of` are recorded.
3. Prohibited actions (auto-closing work, approving time, posting invoices, changing baselines, exposing masked fields) must be rejected by the API and the frontend controls.
4. Check `GET /reports/ai-review-queue` weekly for unreviewed signals/actions and reversals; archive or escalate anything older than one review cycle.
5. Confirm prompts and reports use project-scoped, permission-scoped data and that no provider receives restricted fields.

## 8. Outbox dispatch

1. Events are written transactionally with the PM change. Check `GET /outbox/stats` and `GET /outbox` (filter `event_name`, `status`) for `pending`, `failed`, and `published` counts.
2. Dispatch a bounded batch manually with `POST /outbox/dispatch?limit=50` (`limit` is a query parameter), or let the Celery task `hertex.dispatch_project_outbox(tenant_id, limit)` run. Dispatch is idempotent per key and injects `correlation_id` into the published payload.
3. A failed event increments `attempts` and stores `error`; it is not retried automatically. Fix the subscriber/transport, then reset the failed row to `pending` via `PATCH /outbox/{id}` and dispatch again.
4. Never dispatch events for a tenant whose Finance documents were reversed until links are reconciled. Keep the outbox table and its audit rows for retention.

## 9. Incident checks

- `GET /health`; `alembic current` still at `f4e2c8a7b913`; no new PM drift from `alembic check`.
- `GET /outbox/stats`: sustained pending growth or any failed events; correlation IDs present on published rows.
- Billing runs stuck in `review`/`approved`, posts without an invoice link, duplicate invoice references, or no-double-billing conflicts.
- Timesheets/approvals with unexpected status, direct edits to approved time entries or baselines, and missing audit/activity rows.
- Cross-tenant leakage: a project/work item/time/billing query from another tenant must return not found.
- D4 masking on cost/rate fields in reports, AI actions, and frontend project money surfaces.
- After any deploy: rerun `scripts/check_openapi_snapshot.py`; a failure means a PM contract changed and clients must be reviewed before continuing.
