from __future__ import annotations

import logging
import re
from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import SQLAlchemyError

revision: str = "c15d3e7f8a91"
down_revision: Union[str, None] = "7a3b9c1d5e24"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("hertex.migrations.settings_replay_fixes")

UUID_TYPE = postgresql.UUID(as_uuid=True)

NUMBER_SEQUENCE_PARTIAL_INDEXES = (
    (
        "uq_number_sequences_tenant_key_default",
        "number_sequences",
        ("tenant_id", "key"),
        "branch_id IS NULL",
    ),
    (
        "uq_number_sequences_tenant_key_branch",
        "number_sequences",
        ("tenant_id", "key", "branch_id"),
        "branch_id IS NOT NULL",
    ),
)

APP_SETTING_PARTIAL_INDEXES = (
    (
        "uq_app_settings_scope_tenant",
        "app_settings",
        ("tenant_id", "scope_type", "key"),
        "scope_id IS NULL",
    ),
    (
        "uq_app_settings_scope_scoped",
        "app_settings",
        ("tenant_id", "scope_type", "scope_id", "key"),
        "scope_id IS NOT NULL",
    ),
)

NUMBERED_DOCUMENTS = (
    ("finance_journal_entries", "entry_number", "uq_finance_journal_entries_tenant_number"),
    ("finance_invoices", "invoice_number", "uq_finance_invoices_tenant_number"),
    ("sales_orders", "order_number", "uq_sales_orders_tenant_number"),
    (
        "sales_delivery_challans",
        "challan_number",
        "uq_sales_delivery_challans_tenant_number",
    ),
    ("pos_sales", "sale_number", "uq_pos_sales_tenant_number"),
    (
        "procurement_purchase_orders",
        "po_number",
        "uq_procurement_purchase_orders_tenant_number",
    ),
    (
        "procurement_goods_receipts",
        "grn_number",
        "uq_procurement_goods_receipts_tenant_number",
    ),
    (
        "procurement_requisitions",
        "requisition_number",
        "uq_procurement_requisitions_tenant_number",
    ),
    (
        "procurement_vendor_invoices",
        "invoice_number",
        "uq_procurement_vendor_invoices_tenant_number",
    ),
    ("support_tickets", "ticket_number", "uq_support_tickets_tenant_number"),
    ("hr_payslips", "payslip_number", "uq_hr_payslips_tenant_number"),
)

PAYSLIP_SUFFIX = re.compile(r"(\d+)$")


def _dialect() -> str:
    return op.get_bind().dialect.name


def _inspector():
    return sa.inspect(op.get_bind())


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_exists(table: str) -> bool:
    return bool(_inspector().has_table(table))


def _column_names(table: str) -> set[str]:
    if not _table_exists(table):
        return set()
    return {str(column["name"]) for column in _inspector().get_columns(table)}


def _index_names(table: str) -> set[str]:
    if not _table_exists(table):
        return set()
    return {str(index["name"]) for index in _inspector().get_indexes(table) if index.get("name")}


def _unique_constraint_names(table: str) -> set[str]:
    if not _table_exists(table):
        return set()
    inspector = _inspector()
    names = {
        str(constraint["name"])
        for constraint in inspector.get_unique_constraints(table)
        if constraint.get("name")
    }
    names.update(
        str(constraint["name"])
        for constraint in inspector.get_foreign_keys(table)
        if constraint.get("name")
    )
    return names


def _unique_pairs(table: str) -> set[frozenset[str]]:
    if not _table_exists(table):
        return set()
    inspector = _inspector()
    pairs: set[frozenset[str]] = set()
    for index in inspector.get_indexes(table):
        if index.get("unique"):
            pairs.add(frozenset(str(column).lower() for column in index.get("column_names") or ()))
    for constraint in inspector.get_unique_constraints(table):
        pairs.add(
            frozenset(str(column).lower() for column in constraint.get("column_names") or ())
        )
    return pairs


def _duplicate_rows(table: str, columns: Sequence[str], where: str | None = None) -> list[tuple]:
    if not _table_exists(table):
        return []
    selected_columns = ", ".join(_quote(column) for column in columns)
    where_clause = f" WHERE {where}" if where else None
    sql = (
        f"SELECT {selected_columns}, COUNT(*) AS duplicate_count FROM {_quote(table)}"
        f"{where_clause or ''} GROUP BY {selected_columns} "
        "HAVING COUNT(*) > 1 ORDER BY duplicate_count DESC"
    )
    return list(op.get_bind().execute(sa.text(sql)).fetchall())


def _assert_no_duplicates(
    table: str,
    columns: Sequence[str],
    finding: str,
    where: str | None = None,
) -> None:
    rows = _duplicate_rows(table, columns, where)
    if not rows:
        return
    samples = []
    for row in rows[:5]:
        values = ", ".join(f"{column}={row[index]!r}" for index, column in enumerate(columns))
        samples.append(f"{values} ({row[-1]} rows)")
    raise RuntimeError(
        f"{finding} Blocking duplicates in {table}: " + "; ".join(samples) + ". "
        "Resolve the duplicates manually, then rerun migration c15d3e7f8a91."
    )


def _create_unique_index(
    name: str,
    table: str,
    columns: Sequence[str],
    where: str | None = None,
    *,
    skip_if_covered: bool = False,
) -> bool:
    if not _table_exists(table):
        return False
    if name in _index_names(table) or name in _unique_constraint_names(table):
        return False
    if skip_if_covered and frozenset(column.lower() for column in columns) in _unique_pairs(table):
        return False
    column_sql = ", ".join(_quote(column) for column in columns)
    where_sql = f" WHERE {where}" if where else ""
    op.execute(
        f'CREATE UNIQUE INDEX IF NOT EXISTS {_quote(name)} ON {_quote(table)} '
        f"({column_sql}){where_sql}"
    )
    return True


def _drop_named_objects(table: str, names: Sequence[str]) -> None:
    if not _table_exists(table):
        return
    index_names = _index_names(table)
    unique_names = _unique_constraint_names(table)
    for name in names:
        if name in index_names and name not in unique_names:
            op.drop_index(name, table_name=table)
    droppable = [name for name in names if name in unique_names]
    if not droppable:
        return
    if _dialect() == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch_op:
            for name in droppable:
                batch_op.drop_constraint(name, type_="unique")
    else:
        for name in droppable:
            op.execute(
                f"ALTER TABLE {_quote(table)} DROP CONSTRAINT IF EXISTS {_quote(name)}"
            )


def _drop_index_if_exists(name: str, table: str) -> None:
    if name in _index_names(table):
        op.drop_index(name, table_name=table)


def _ensure_settings_version() -> None:
    if not _table_exists("tenants"):
        return
    if "settings_version" not in _column_names("tenants"):
        op.add_column(
            "tenants",
            sa.Column(
                "settings_version",
                sa.Integer(),
                server_default="1",
                nullable=False,
            ),
        )
        return
    op.execute("UPDATE tenants SET settings_version = 1 WHERE settings_version IS NULL")
    if _dialect() == "postgresql":
        op.execute("ALTER TABLE tenants ALTER COLUMN settings_version SET DEFAULT 1")
        op.execute("ALTER TABLE tenants ALTER COLUMN settings_version SET NOT NULL")


def _prepare_number_sequences() -> None:
    if not _table_exists("number_sequences"):
        return
    _assert_no_duplicates(
        "number_sequences",
        ("tenant_id", "key"),
        "Default number-sequence series are duplicated",
        "branch_id IS NULL",
    )
    _assert_no_duplicates(
        "number_sequences",
        ("tenant_id", "key", "branch_id"),
        "Branch number-sequence series are duplicated",
        "branch_id IS NOT NULL",
    )
    _drop_named_objects(
        "number_sequences",
        ("uq_number_sequences_tenant_key", "uq_number_sequences_tenant_key_branch"),
    )
    for name, table, columns, where in NUMBER_SEQUENCE_PARTIAL_INDEXES:
        _create_unique_index(name, table, columns, where)


def _prepare_app_settings() -> None:
    if not _table_exists("app_settings"):
        return
    _assert_no_duplicates(
        "app_settings",
        ("tenant_id", "scope_type", "key"),
        "Tenant-scoped app settings are duplicated",
        "scope_id IS NULL",
    )
    _assert_no_duplicates(
        "app_settings",
        ("tenant_id", "scope_type", "scope_id", "key"),
        "Branch/user-scoped app settings are duplicated",
        "scope_id IS NOT NULL",
    )
    _drop_named_objects(
        "app_settings",
        ("uq_app_settings_tenant_key", "uq_app_settings_scope_key"),
    )
    for name, table, columns, where in APP_SETTING_PARTIAL_INDEXES:
        _create_unique_index(name, table, columns, where)


def _prepare_numbered_documents() -> None:
    for table, column, name in NUMBERED_DOCUMENTS:
        if not _table_exists(table) or column not in _column_names(table):
            continue
        _assert_no_duplicates(
            table,
            ("tenant_id", column),
            f"Duplicate numbers block the {name} constraint",
        )
    _assert_no_duplicates(
        "procurement_vendor_invoices",
        ("tenant_id", "invoice_number"),
        "Duplicate vendor invoice numbers block the tenant-aware unique index",
    )
    for table, column, name in NUMBERED_DOCUMENTS:
        if not _table_exists(table) or column not in _column_names(table):
            continue
        _create_unique_index(name, table, ("tenant_id", column), skip_if_covered=True)


def _backfill_payslip_numbers() -> None:
    if not _table_exists("hr_payslips"):
        return
    columns = _column_names("hr_payslips")
    if "payslip_number" not in columns:
        op.add_column("hr_payslips", sa.Column("payslip_number", sa.String(50), nullable=True))
    bind = op.get_bind()
    rows = list(
        bind.execute(
            sa.text("SELECT id, tenant_id, payslip_number FROM hr_payslips ORDER BY tenant_id, id")
        ).fetchall()
    )
    used: dict[str, set[int]] = {}
    next_by_tenant: dict[str, int] = {}
    updates: list[tuple[str, str]] = []
    for row in rows:
        tenant_key = str(row.tenant_id) if row.tenant_id is not None else ""
        values = used.setdefault(tenant_key, set())
        value = row.payslip_number
        if value:
            match = PAYSLIP_SUFFIX.search(str(value))
            if match:
                values.add(int(match.group(1)))
    for row in rows:
        if row.payslip_number:
            continue
        tenant_key = str(row.tenant_id) if row.tenant_id is not None else ""
        values = used.setdefault(tenant_key, set())
        candidate = next_by_tenant.get(tenant_key, max(values, default=0) + 1)
        while candidate in values:
            candidate += 1
        values.add(candidate)
        next_by_tenant[tenant_key] = candidate + 1
        updates.append((f"PSL-{candidate:05d}", str(row.id)))
    if updates:
        id_type = UUID_TYPE if _dialect() == "postgresql" else sa.String(50)
        statement = sa.text(
            "UPDATE hr_payslips SET payslip_number = :number WHERE id = :id"
        ).bindparams(
            sa.bindparam("number", type_=sa.String(50)),
            sa.bindparam("id", type_=id_type),
        )
        bind.execute(statement, [{"number": number, "id": row_id} for number, row_id in updates])
    _assert_no_duplicates(
        "hr_payslips",
        ("tenant_id", "payslip_number"),
        "Duplicate payslip numbers block the tenant-aware unique index",
        "payslip_number IS NOT NULL",
    )
    null_count = int(
        bind.execute(
            sa.text("SELECT COUNT(*) FROM hr_payslips WHERE payslip_number IS NULL")
        ).scalar_one()
    )
    if null_count == 0:
        if _dialect() == "sqlite":
            with op.batch_alter_table("hr_payslips", recreate="always") as batch_op:
                batch_op.alter_column(
                    "payslip_number",
                    existing_type=sa.String(50),
                    nullable=False,
                )
        else:
            op.execute("ALTER TABLE hr_payslips ALTER COLUMN payslip_number SET NOT NULL")
    else:
        logger.warning(
            "hr_payslips.payslip_number remains nullable for %s legacy rows; "
            "the unique index still enforces uniqueness for non-null numbers",
            null_count,
        )
    _create_unique_index(
        "uq_hr_payslips_tenant_number",
        "hr_payslips",
        ("tenant_id", "payslip_number"),
        skip_if_covered=True,
    )


def upgrade() -> None:
    _ensure_settings_version()
    _prepare_number_sequences()
    _prepare_app_settings()
    _prepare_numbered_documents()
    _backfill_payslip_numbers()


def _restore_legacy_unique(
    table: str,
    name: str,
    columns: Sequence[str],
    *,
    nulls_not_distinct: bool = False,
) -> None:
    if not _table_exists(table) or name in _unique_constraint_names(table):
        return
    if _duplicate_rows(table, columns):
        logger.warning("Skipping legacy constraint %s because duplicate rows remain", name)
        return
    if _dialect() == "sqlite":
        with op.batch_alter_table(table, recreate="always") as batch_op:
            batch_op.create_unique_constraint(name, list(columns))
        return
    column_sql = ", ".join(_quote(column) for column in columns)
    distinct_sql = "NULLS NOT DISTINCT " if nulls_not_distinct else ""
    op.execute(
        f"ALTER TABLE {_quote(table)} ADD CONSTRAINT {_quote(name)} "
        f"UNIQUE {distinct_sql}({column_sql})"
    )


def downgrade() -> None:
    for name, table, _columns, _where in (
        *NUMBER_SEQUENCE_PARTIAL_INDEXES,
        *APP_SETTING_PARTIAL_INDEXES,
    ):
        _drop_index_if_exists(name, table)
    for _table, _column, name in NUMBERED_DOCUMENTS:
        _drop_index_if_exists(name, _table)
    if _table_exists("hr_payslips"):
        _drop_index_if_exists("uq_hr_payslips_tenant_number", "hr_payslips")
        if "payslip_number" in _column_names("hr_payslips"):
            if _dialect() == "sqlite":
                with op.batch_alter_table("hr_payslips", recreate="always") as batch_op:
                    batch_op.drop_column("payslip_number")
            else:
                op.drop_column("hr_payslips", "payslip_number")
    _restore_legacy_unique("number_sequences", "uq_number_sequences_tenant_key", ("tenant_id", "key"))
    _restore_legacy_unique(
        "app_settings",
        "uq_app_settings_tenant_key",
        ("tenant_id", "key"),
    )
    if _dialect() == "postgresql":
        _restore_legacy_unique(
            "app_settings",
            "uq_app_settings_scope_key",
            ("tenant_id", "scope_type", "scope_id", "key"),
            nulls_not_distinct=True,
        )
    if _table_exists("tenants") and "settings_version" in _column_names("tenants"):
        try:
            if _dialect() == "sqlite":
                with op.batch_alter_table("tenants", recreate="always") as batch_op:
                    batch_op.drop_column("settings_version")
            else:
                op.drop_column("tenants", "settings_version")
        except SQLAlchemyError as exc:
            logger.warning("Could not remove tenants.settings_version during downgrade: %s", exc)
