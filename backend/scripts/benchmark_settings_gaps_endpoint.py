"""Real endpoint gap-report benchmark (100k allocation rows)."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
import urllib.parse
import urllib.request
import uuid
from datetime import date

from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.modules.identity.models import User
from app.modules.settings.models import NumberAllocation, NumberSequence, NumberSequencePeriod


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default=os.getenv("BASE_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--token", default=os.getenv("API_TOKEN", ""))
    parser.add_argument(
        "--tenant-id",
        default=os.getenv("TENANT_ID", ""),
        help="tenant UUID (defaults to the seeded admin's tenant)",
    )
    parser.add_argument("--key", default=os.getenv("SEQUENCE_KEY", "benchmark_gap_report"))
    parser.add_argument("--fiscal-year", default=os.getenv("FISCAL_YEAR", "2025-26"))
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--p95-ms", type=float, default=300.0)
    parser.add_argument("--cleanup", action="store_true")
    return parser.parse_args()


async def seed(args: argparse.Namespace) -> None:
    tenant_id = uuid.UUID(str(args.tenant_id))
    async with AsyncSessionLocal() as db:
        sequence = await db.scalar(
            select(NumberSequence).where(
                NumberSequence.tenant_id == tenant_id,
                NumberSequence.key == args.key,
            )
        )
        if sequence is None:
            sequence = NumberSequence(
                tenant_id=tenant_id,
                key=args.key,
                doc_type="internal",
                owner_module="settings",
                pattern="{seq:05d}",
                prefix="BENCH",
            )
            db.add(sequence)
            await db.flush()

        period = await db.scalar(
            select(NumberSequencePeriod).where(
                NumberSequencePeriod.sequence_id == sequence.id,
                NumberSequencePeriod.fiscal_year == args.fiscal_year,
            )
        )
        start_year = int(args.fiscal_year[:4])
        if period is None:
            period = NumberSequencePeriod(
                tenant_id=tenant_id,
                sequence_id=sequence.id,
                fiscal_year=args.fiscal_year,
                period_start=date(start_year, 4, 1),
                period_end=date(start_year + 1, 3, 31),
                next_number=1,
            )
            db.add(period)
            await db.flush()

        existing_max = await db.scalar(
            select(func.coalesce(func.max(NumberAllocation.number), 0)).where(
                NumberAllocation.sequence_id == sequence.id,
                NumberAllocation.fiscal_year == args.fiscal_year,
            )
        )
        first_number = int(existing_max or 0) + 1
        existing_count = await db.scalar(
            select(func.count(NumberAllocation.id)).where(
                NumberAllocation.sequence_id == sequence.id,
                NumberAllocation.fiscal_year == args.fiscal_year,
                NumberAllocation.document_type == "benchmark",
            )
        )
        missing = args.rows - int(existing_count or 0)
        if missing > 0:
            rows = []
            for offset in range(missing):
                number = first_number + offset
                rows.append(
                    NumberAllocation(
                        tenant_id=tenant_id,
                        sequence_id=sequence.id,
                        period_id=period.id,
                        fiscal_year=args.fiscal_year,
                        number=number,
                        rendered=f"BENCH/{args.fiscal_year}/{number:08d}",
                        status="void" if number % 997 == 0 else "committed",
                        document_type="benchmark",
                        idempotency_key=f"benchmark-{args.key}-{number}",
                        reason_code="benchmark" if number % 997 == 0 else None,
                        reason_text="benchmark" if number % 997 == 0 else None,
                    )
                )
            db.add_all(rows)
            period.next_number = first_number + missing
        await db.commit()


async def cleanup(args: argparse.Namespace) -> None:
    tenant_id = uuid.UUID(str(args.tenant_id))
    async with AsyncSessionLocal() as db:
        sequence = await db.scalar(
            select(NumberSequence).where(
                NumberSequence.tenant_id == tenant_id,
                NumberSequence.key == args.key,
            )
        )
        if sequence is None:
            return
        rows = (
            await db.scalars(
                select(NumberAllocation).where(
                    NumberAllocation.sequence_id == sequence.id,
                    NumberAllocation.document_type == "benchmark",
                )
            )
        ).all()
        for row in rows:
            await db.delete(row)
        await db.commit()


def call_endpoint(args: argparse.Namespace) -> float:
    query = urllib.parse.urlencode({"key": args.key, "fiscal_year": args.fiscal_year})
    url = f"{args.base_url.rstrip('/')}/api/v1/settings/reports/numbering/gaps?{query}"
    headers = {"Accept": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    request = urllib.request.Request(url, headers=headers)
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    if not payload:
        raise RuntimeError("empty gap report response")
    return (time.perf_counter() - started) * 1000


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    index = max(1, int(len(ordered) * fraction)) - 1
    return ordered[index]


async def resolve_tenant_id(tenant_id: str) -> str:
    if tenant_id:
        return tenant_id
    async with AsyncSessionLocal() as db:
        user = await db.scalar(select(User).where(User.email == settings.SEED_ADMIN_EMAIL))
    if user is None:
        raise SystemExit("no tenant id supplied and the seeded admin user was not found")
    return str(user.tenant_id)


async def main() -> int:
    args = parse_args()
    args.tenant_id = await resolve_tenant_id(args.tenant_id)
    await seed(args)
    try:
        for _ in range(3):
            call_endpoint(args)
        samples = [call_endpoint(args) for _ in range(args.samples)]
        result = {
            "endpoint": "/api/v1/settings/reports/numbering/gaps",
            "rows": args.rows,
            "samples": args.samples,
            "p50_ms": round(percentile(samples, 0.5), 2),
            "p95_ms": round(percentile(samples, 0.95), 2),
            "max_ms": round(max(samples), 2),
            "target_ms": args.p95_ms,
            "pass": percentile(samples, 0.95) < args.p95_ms,
        }
        print(json.dumps(result))
        return 0 if result["pass"] else 1
    finally:
        if args.cleanup:
            await cleanup(args)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
