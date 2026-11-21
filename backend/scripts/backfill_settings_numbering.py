import argparse
import asyncio
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seed import SEQUENCES
from app.modules.settings.models import AppSetting, NumberSequence, NumberSequencePeriod
from app.modules.settings.service import checksum

COMPANY_PROFILE_KEY = "company." + "profile"
LEGACY_PROJECTIONS = {
    COMPANY_PROFILE_KEY: {
        "name": "company.profile.name",
        "legal_name": "company.profile.legal_name",
        "address": "company.profile.address",
        "phone": "company.profile.phone",
        "email": "company.profile.email",
        "gstin": "company.profile.gstin",
        "pan": "company.profile.pan",
        "cin": "company.profile.cin",
        "state_code": "company.profile.state_code",
        "currency": "company.locale.currency",
        "timezone": "company.locale.timezone",
    },
    "finance.defaults": {
        "invoice_due_days": "finance.invoice.due_days",
    },
    "sales.defaults": {
        "quote_validity_days": "sales.quote.validity_days",
    },
    "support.sla": {
        "first_response_hours": "support.sla.first_response_hours",
        "resolution_hours": "support.sla.resolution_hours",
    },
}

SEQUENCE_TABLES = {
    "invoice": ("finance_invoices", "invoice_number", "issue_date"),
    "sales_order": ("sales_orders", "order_number", "order_date"),
    "delivery_challan": ("sales_delivery_challans", "challan_number", "dispatched_date"),
    "journal_entry": ("finance_journal_entries", "entry_number", "entry_date"),
    "purchase_requisition": ("procurement_requisitions", "requisition_number", "created_at"),
    "purchase_order": ("procurement_purchase_orders", "po_number", "order_date"),
    "goods_receipt": ("procurement_goods_receipts", "grn_number", "received_date"),
    "vendor_invoice": ("procurement_vendor_invoices", "invoice_number", "issue_date"),
    "pos_sale": ("pos_sales", "sale_number", "created_at"),
    "ticket": ("support_tickets", "ticket_number", "created_at"),
    "payslip": ("hr_payslips", "payslip_number", "created_at"),
}

SUFFIX = re.compile(r"(\d+)$")


def uuid_key(value: Any) -> str:
    return str(value).replace("-", "") if value is not None else ""


def fiscal_year_label(value: Any, start_month: int = 4) -> str:
    if isinstance(value, datetime):
        value = value.date()
    if isinstance(value, str):
        try:
            value = date.fromisoformat(value[:10])
        except ValueError:
            return "unknown"
    if not isinstance(value, date):
        return "unknown"
    year = value.year if value.month >= start_month else value.year - 1
    return f"{year % 100:02d}-{(year + 1) % 100:02d}"


def fiscal_year_start(label: str) -> date:
    match = re.match(r"^(\d{2})-(\d{2})$", label)
    if match:
        return date(2000 + int(match.group(1)), 4, 1)
    return date.today()


def _coerce_value(value: Any, value_type: str) -> Any:
    if value_type in {"int", "duration"}:
        return int(value)
    if value_type in {"decimal", "currency"}:
        return str(value)
    if value_type == "bool":
        if isinstance(value, bool):
            return value
        return str(value).lower() in {"1", "true", "yes", "on"}
    return value


async def _table_exists(db: AsyncSession, table: str) -> bool:
    connection = await db.connection()
    return bool(await connection.run_sync(lambda conn: sa.inspect(conn).has_table(table)))


async def _column_names(db: AsyncSession, table: str) -> set[str]:
    connection = await db.connection()
    return set(
        await connection.run_sync(
            lambda conn: {column["name"] for column in sa.inspect(conn).get_columns(table)}
        )
    )


async def backfill_settings_version(db: AsyncSession, apply: bool = False) -> dict[str, Any]:
    if not await _table_exists(db, "tenants"):
        return {"changed": 0, "skipped": "tenants table missing"}
    columns = await _column_names(db, "tenants")
    if "settings_version" not in columns:
        return {"changed": 0, "skipped": "tenants.settings_version missing"}
    if not apply:
        count = int(
            await db.scalar(
                sa.text("SELECT COUNT(*) FROM tenants WHERE settings_version IS NULL")
            )
            or 0
        )
        return {"changed": count, "applied": False}
    result = await db.execute(
        sa.text("UPDATE tenants SET settings_version = 1 WHERE settings_version IS NULL")
    )
    return {"changed": int(result.rowcount or 0), "applied": True}


async def project_legacy_settings(db: AsyncSession, apply: bool = False) -> dict[str, Any]:
    from app.modules.settings.registry import BY_KEY

    planned: list[dict[str, Any]] = []
    existing_legacy = 0
    skipped = 0
    unmapped: list[str] = []
    rows = list(
        (
            await db.scalars(
                select(AppSetting).where(AppSetting.key.in_(tuple(LEGACY_PROJECTIONS)))
            )
        ).all()
    )
    existing_targets = {
        (str(row.tenant_id), row.key, row.scope_type, str(row.scope_id))
        for row in (
            await db.scalars(
                select(AppSetting).where(
                    AppSetting.key.in_(
                        tuple(
                            key
                            for mapping in LEGACY_PROJECTIONS.values()
                            for key in mapping.values()
                        )
                    )
                )
            )
        ).all()
    }
    for legacy in rows:
        existing_legacy += 1
        mapping = LEGACY_PROJECTIONS.get(legacy.key, {})
        value = legacy.value if isinstance(legacy.value, dict) else {}
        for source_key, target_key in mapping.items():
            descriptor = BY_KEY.get(target_key)
            if descriptor is None or source_key not in value or value[source_key] is None:
                unmapped.append(f"{legacy.key}.{source_key}")
                continue
            identity = (
                str(legacy.tenant_id),
                target_key,
                legacy.scope_type or "tenant",
                str(legacy.scope_id),
            )
            if identity in existing_targets:
                skipped += 1
                continue
            projected = _coerce_value(value[source_key], descriptor.type)
            existing_targets.add(identity)
            planned.append(
                {
                    "tenant_id": legacy.tenant_id,
                    "scope_type": legacy.scope_type or "tenant",
                    "scope_id": legacy.scope_id,
                    "key": target_key,
                    "value": projected,
                    "value_type": descriptor.type,
                    "category": descriptor.module,
                    "source": "migration",
                    "checksum": checksum(projected),
                }
            )
    if apply:
        for entry in planned:
            db.add(AppSetting(**entry))
    return {
        "legacy_rows": existing_legacy,
        "created": len(planned) if apply else 0,
        "planned": len(planned),
        "skipped_existing": skipped,
        "unmapped": sorted(set(unmapped)),
        "projections": [f"{entry['key']}={entry['value']!r}" for entry in planned],
        "applied": apply,
    }


def _series_specs() -> list[tuple[str, str, str, str, int]]:
    specs = []
    for key, _prefix, padding, *_rest in SEQUENCES:
        table_info = SEQUENCE_TABLES.get(key)
        if table_info is None:
            continue
        table, number_column, date_column = table_info
        specs.append((key, table, number_column, date_column, int(padding)))
    return specs


async def numbering_report(db: AsyncSession) -> dict[str, Any]:
    series_rows: list[dict[str, Any]] = []
    render_index: dict[tuple[str, str, str], set[str]] = defaultdict(set)
    findings: list[str] = []
    sequence_ids: dict[tuple[str, str], Any] = {}
    period_next: dict[tuple[str, str], int] = {}
    for sequence in (
        await db.scalars(select(NumberSequence).where(NumberSequence.branch_id.is_(None)))
    ).all():
        sequence_ids[(uuid_key(sequence.tenant_id), sequence.key)] = sequence.id
    for period in (await db.scalars(select(NumberSequencePeriod))).all():
        period_next[(str(period.sequence_id), period.fiscal_year)] = int(period.next_number)
    for key, table, number_column, date_column, padding in _series_specs():
        if not await _table_exists(db, table):
            continue
        columns = await _column_names(db, table)
        if number_column not in columns:
            continue
        date_sql = f'"{date_column}"' if date_column in columns else "NULL"
        rows = list(
            (
                await db.execute(
                    sa.text(
                        f'SELECT tenant_id, "{number_column}" AS number_value, {date_sql} AS document_date '
                        f'FROM "{table}" WHERE "{number_column}" IS NOT NULL'
                    )
                )
            ).all()
        )
        buckets: dict[tuple[str, str], list[tuple[str, int]]] = defaultdict(list)
        local_seen: dict[tuple[str, str, str], list[str]] = defaultdict(list)
        for row in rows:
            rendered = str(row.number_value)
            match = SUFFIX.search(rendered)
            if not match:
                continue
            suffix = int(match.group(1))
            fy = fiscal_year_label(row.document_date)
            tenant_key = uuid_key(row.tenant_id)
            buckets[(tenant_key, fy)].append((rendered, suffix))
            local_seen[(tenant_key, fy, rendered)].append(tenant_key)
            render_index[(tenant_key, fy, rendered)].add(key)
            if suffix >= 10**padding:
                findings.append(
                    f"OVERFLOW {key}/{fy}: {rendered} exceeds padding {padding}"
                )
        for (tenant_key, fy, rendered), table_names in local_seen.items():
            if len(table_names) > 1:
                findings.append(
                    f"DUPLICATE {key}/{fy} tenant={tenant_key or 'null'}: "
                    f"{rendered} appears {len(table_names)} times"
                )
        for (tenant_key, fy), values in sorted(buckets.items()):
            suffixes = [suffix for _rendered, suffix in values]
            proposed_next = max(suffixes) + 1
            sequence_id = sequence_ids.get((tenant_key, key))
            current = period_next.get((str(sequence_id), fy)) if sequence_id else None
            series_rows.append(
                {
                    "series": key,
                    "table": table,
                    "tenant_id": tenant_key or None,
                    "fiscal_year": fy,
                    "max_suffix": max(suffixes),
                    "proposed_next_number": proposed_next,
                    "current_next_number": current,
                }
            )
    for (tenant_key, fy, rendered), series in render_index.items():
        if len(series) > 1:
            findings.append(
                f"COLLISION tenant={tenant_key or 'null'} {fy}: {rendered} used by "
                + ", ".join(sorted(series))
            )
    return {"rows": series_rows, "findings": sorted(set(findings))}


async def apply_numbering_report(db: AsyncSession, report: dict[str, Any]) -> dict[str, Any]:
    from app.modules.settings.numbering import numbering

    changed = 0
    skipped: list[str] = []
    for row in report["rows"]:
        prefix = f"{row['series']}/{row['fiscal_year']}"
        sequence = await db.scalar(
            select(NumberSequence).where(
                NumberSequence.key == row["series"],
                NumberSequence.tenant_id == UUID(row["tenant_id"]),
                NumberSequence.branch_id.is_(None),
            )
        )
        if sequence is None:
            skipped.append(f"{prefix}: no default series")
            continue
        period = await db.scalar(
            select(NumberSequencePeriod).where(
                NumberSequencePeriod.sequence_id == sequence.id,
                NumberSequencePeriod.fiscal_year == row["fiscal_year"],
            )
        )
        if period is None:
            period = await numbering.ensure_period(
                db, sequence, fiscal_year_start(row["fiscal_year"])
            )
        proposed = int(row["proposed_next_number"])
        if period.next_number < proposed:
            period.next_number = proposed
            changed += 1
    return {"changed": changed, "skipped": skipped}


def print_report(version: dict, projections: dict, numbering: dict, apply: bool) -> None:
    print("Settings numbering backfill report")
    print(
        f"tenants.settings_version: {version['changed']} row(s) to set"
        + (" (applied)" if version.get("applied") else "")
    )
    print(
        f"legacy settings: {projections['legacy_rows']} row(s), "
        f"{projections['planned']} projection(s) planned, "
        f"{projections['skipped_existing']} skipped"
    )
    for projection in projections.get("projections", []):
        print(f"  PROJECT {projection}")
    for key in projections.get("unmapped", []):
        print(f"  UNMAPPED {key}")
    for row in numbering["rows"]:
        current = row["current_next_number"]
        print(
            f"  SERIES {row['series']} tenant={row['tenant_id'] or 'null'} "
            f"fy={row['fiscal_year']} table={row['table']} "
            f"max_suffix={row['max_suffix']} current={current} "
            f"proposed_next_number={row['proposed_next_number']}"
        )
    for finding in numbering["findings"]:
        print(f"  BLOCKING {finding}")
    if not apply:
        print("Dry run only. Re-run with --apply to write changes.")
    if numbering["findings"]:
        print("Blocking numbering findings present; numbering counters were not written.")


async def run(apply: bool) -> int:
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        version = await backfill_settings_version(db, apply=apply)
        projections = await project_legacy_settings(db, apply=apply)
        numbering = await numbering_report(db)
        numbering_apply: dict[str, Any] = {"changed": 0, "skipped": []}
        if apply and not numbering["findings"]:
            numbering_apply = await apply_numbering_report(db, numbering)
        print_report(version, projections, numbering, apply)
        if apply:
            print(
                f"Applied settings_version rows: {version['changed']}; "
                f"projections: {projections['created']}; "
                f"numbering counters: {numbering_apply['changed']}"
            )
            await db.commit()
        return 2 if numbering["findings"] else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill settings version and numbering series")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry run)")
    args = parser.parse_args()
    raise SystemExit(asyncio.run(run(apply=args.apply)))


if __name__ == "__main__":
    main()
