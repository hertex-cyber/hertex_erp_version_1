"""Synthetic gap-report benchmark (100k allocation rows)."""
from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
import time


def percentile(samples: list[float], fraction: float) -> float:
    ordered = sorted(samples)
    return ordered[max(1, int(len(ordered) * fraction)) - 1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--p95-ms", type=float, default=300.0)
    args = parser.parse_args()

    with tempfile.NamedTemporaryFile(suffix=".db") as handle:
        db = sqlite3.connect(handle.name)
        db.execute(
            "create table allocations ("
            "tenant text, sequence_id text, fiscal_year text, number integer, "
            "status text, allocated_at text, rendered text, reason_code text, reason_text text)"
        )
        db.execute(
            "create index allocations_gap_report on allocations(tenant, fiscal_year, number)"
        )
        db.executemany(
            "insert into allocations values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    "tenant",
                    "sequence",
                    "2025-26",
                    index + 1,
                    "void" if index % 997 == 0 else "committed",
                    "2026-11-20",
                    f"INV/25-26/{index + 1:05d}",
                    "benchmark" if index % 997 == 0 else None,
                    "benchmark" if index % 997 == 0 else None,
                )
                for index in range(args.rows)
            ],
        )
        db.commit()

        samples = []
        for _ in range(args.samples):
            started = time.perf_counter()
            rows = db.execute(
                "select number, status, rendered, reason_code, reason_text "
                "from allocations where tenant=? and fiscal_year=? order by number",
                ("tenant", "2025-26"),
            ).fetchall()
            numbers = {row[0]: row for row in rows}
            highest = max(numbers)
            voids = sum(
                1
                for number in range(1, highest + 1)
                if number in numbers and numbers[number][1] == "void"
            )
            if voids == 0:
                raise RuntimeError("benchmark seed produced no voids")
            samples.append((time.perf_counter() - started) * 1000)
        db.close()

    result = {
        "endpoint": "synthetic gap report (match numbering.gap_report shape)",
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


if __name__ == "__main__":
    raise SystemExit(main())
