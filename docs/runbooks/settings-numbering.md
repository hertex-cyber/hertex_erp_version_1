# Settings & Numbering Runbook

## FY rollover

1. Seven days before period end, run `NumberSequenceService.open_next_periods` or the scheduled worker.
2. Confirm the next period appears in `/api/v1/settings/sequences/{key}/status`.
3. Verify the first allocation uses the document date's fiscal-year label.
4. Close old periods only after reconciliation. Closed periods reject backdated allocations.

## Scheduled sweeps

- `docker compose up -d worker beat` runs the worker and persistent scheduler against Redis 7.
- Beat schedules: `hertex.numbering.periods` daily, `hertex.numbering.abandoned` hourly, `hertex.numbering.blocks` hourly, `hertex.numbering.unreturned` every six hours.
- Manual full sweep: `cd backend && python scripts/run_settings_sweeps.py --all`.
- Manual single sweep: `cd backend && python scripts/run_settings_sweeps.py --task hertex.numbering.periods`.
- Local Redis 6 cannot start the Celery worker with the Redis 7 transport helpers; use Compose/CI Redis 7 for worker or beat validation.

## Series cut-over

1. Add the new active series key and preview the worst-case rendered number.
2. Complete a dry-run allocation on a non-production document type.
3. Enable the new module/series through the rollout procedure.
4. Never change `implementation`, `pattern`, `reset_policy`, or `padding` after the first allocation. Create a new series key instead.

## Secret rotation

1. PUT the secret to create or replace it.
2. POST `/rotate` with the new plaintext and window (default 72 hours).
3. Verify integration consumers work during the dual-read window.
4. POST `/commit` or `/rollback` before the window expires.
5. Never copy ciphertext or plaintext into tickets or audit notes.
6. For encryption-key rotation, deploy `SETTINGS_ENCRYPTION_KEY` with a new `SETTINGS_ENCRYPTION_KEY_VERSION`, keep the previous key available for the rotation window, rewrap active secrets, then retire the old version only after `/commit`.

## Offline block recovery

1. Search `/settings/sequences/{key}/blocks` for issued or partially-used blocks.
2. Confirm device/session identity and used range.
3. Return unused tail with `/blocks/{id}/return`.
4. Run the expiry sweeper and review gap-report reasons.

## Rollback

1. Disable `features.numbering.engine` for the tenant; the shared `allocate()` entry point then routes to the atomic count-derived fallback and still writes a ledger row.
2. Stop module cut-over traffic and preserve existing allocations.
3. Never delete `number_allocations` or period rows.
4. After rollback, reconcile the gap report before retrying the engine.

## Incident checks

- No duplicate rendered numbers on document tables.
- No period with `status=open` for a closed fiscal year.
- No allocation with `status=allocated` older than 24 hours without a document link.
- OpenAPI snapshot remains non-breaking for Settings endpoints.

## Performance checks

- Synthetic 100k-row gate: `cd backend && python scripts/benchmark_settings_gaps.py`.
- Live endpoint gate (100k rows, p95 < 300 ms): `cd backend && python scripts/benchmark_settings_gaps_endpoint.py --token "$TOKEN" --cleanup`.
- Verified 2026-11-21: synthetic p95 162.19 ms, live p95 272.84 ms.
