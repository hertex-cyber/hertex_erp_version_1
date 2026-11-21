import importlib.util
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "c15d3e7f8a91_settings_replay_fixes.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("settings_replay_fixes", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _create_legacy_schema(connection, migration):
    connection.execute(
        sa.text(
            "CREATE TABLE tenants (id TEXT PRIMARY KEY, name TEXT)"
        )
    )
    connection.execute(
        sa.text(
            "CREATE TABLE number_sequences ("
            "id TEXT PRIMARY KEY, tenant_id TEXT, key TEXT, branch_id TEXT, "
            "CONSTRAINT uq_number_sequences_tenant_key UNIQUE (tenant_id, key))"
        )
    )
    connection.execute(
        sa.text(
            "CREATE TABLE app_settings ("
            "id TEXT PRIMARY KEY, tenant_id TEXT, key TEXT, scope_type TEXT, scope_id TEXT, "
            "CONSTRAINT uq_app_settings_tenant_key UNIQUE (tenant_id, key))"
        )
    )
    for table, number_column, _name in migration.NUMBERED_DOCUMENTS:
        connection.execute(
            sa.text(
                f"CREATE TABLE {table} ("
                "id TEXT PRIMARY KEY, tenant_id TEXT, "
                f"{number_column} TEXT, created_at TEXT)"
            )
        )
    connection.execute(
        sa.text(
            "INSERT INTO tenants (id, name) VALUES ('tenant-1', 'Tenant One')"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO number_sequences (id, tenant_id, key, branch_id) "
            "VALUES ('seq-1', 'tenant-1', 'invoice', NULL)"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO app_settings (id, tenant_id, key, scope_type, scope_id) "
            "VALUES ('setting-1', 'tenant-1', 'company.profile.name', 'tenant', NULL)"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO sales_orders (id, tenant_id, order_number, created_at) "
            "VALUES ('order-1', 'tenant-1', 'SO/25-26/00001', '2025-06-01')"
        )
    )
    connection.execute(
        sa.text(
            "INSERT INTO hr_payslips (id, tenant_id, payslip_number, created_at) VALUES "
            "('payslip-1', 'tenant-1', NULL, '2025-06-01'), "
            "('payslip-2', 'tenant-1', 'PSL-00007', '2025-06-02')"
        )
    )


def test_migration_is_idempotent_and_backfills_payslips():
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        _create_legacy_schema(connection, migration)
        context = MigrationContext.configure(connection)

        with Operations.context(context):
            migration.upgrade()

        inspector = sa.inspect(connection)
        assert "settings_version" in {
            column["name"] for column in inspector.get_columns("tenants")
        }
        index_names = set()
        for table in ("number_sequences", "app_settings", "sales_orders", "hr_payslips"):
            index_names.update(index["name"] for index in inspector.get_indexes(table))
        for name in (
            "uq_number_sequences_tenant_key_default",
            "uq_number_sequences_tenant_key_branch",
            "uq_app_settings_scope_tenant",
            "uq_app_settings_scope_scoped",
            "uq_sales_orders_tenant_number",
            "uq_hr_payslips_tenant_number",
        ):
            assert name in index_names

        numbers = list(
            connection.execute(
                sa.text("SELECT payslip_number FROM hr_payslips ORDER BY id")
            ).scalars()
        )
        assert numbers == ["PSL-00008", "PSL-00007"]
        assert connection.scalar(
            sa.text("SELECT settings_version FROM tenants WHERE id = 'tenant-1'")
        ) == 1

        with Operations.context(context):
            migration.upgrade()
        numbers_again = list(
            connection.execute(
                sa.text("SELECT payslip_number FROM hr_payslips ORDER BY id")
            ).scalars()
        )
        assert numbers_again == numbers


def test_migration_rejects_duplicate_document_numbers():
    migration = _load_migration()
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        _create_legacy_schema(connection, migration)
        connection.execute(
            sa.text(
                "INSERT INTO sales_orders (id, tenant_id, order_number, created_at) "
                "VALUES ('order-2', 'tenant-1', 'SO/25-26/00001', '2025-06-03')"
            )
        )
        context = MigrationContext.configure(connection)

        with pytest.raises(RuntimeError, match="Duplicate numbers"):
            with Operations.context(context):
                migration.upgrade()
