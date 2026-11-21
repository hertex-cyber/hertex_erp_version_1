from datetime import date
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.session import AsyncSessionLocal
from app.modules.finance.models import Invoice
from app.modules.identity.models import Tenant
from app.modules.settings.models import (
    AppSetting,
    NumberSequence,
    NumberSequencePeriod,
)
from scripts.backfill_settings_numbering import (
    apply_numbering_report,
    backfill_settings_version,
    numbering_report,
    project_legacy_settings,
    uuid_key,
)


@pytest.mark.asyncio
async def test_backfill_settings_version_sets_legacy_nulls():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.execute(
            text("CREATE TABLE tenants (id TEXT PRIMARY KEY, settings_version INTEGER)")
        )
        await connection.execute(
            text("INSERT INTO tenants (id, settings_version) VALUES ('tenant-1', NULL)")
        )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as db:
        version = await backfill_settings_version(db, apply=True)
        await db.commit()
        assert version["changed"] == 1
        assert await db.scalar(text("SELECT settings_version FROM tenants")) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_backfill_projects_legacy_values_without_deleting_originals():
    async with AsyncSessionLocal() as db:
        marker = uuid4().hex[:8]
        tenant = Tenant(name=f"Backfill {marker}", slug=f"backfill-{marker}")
        db.add(tenant)
        await db.flush()
        db.add(
            AppSetting(
                tenant_id=tenant.id,
                key="company.profile",
                value={"name": "Legacy Co", "currency": "INR"},
                category="company",
                value_type="json",
                source="seed",
                checksum="legacy",
                scope_type="tenant",
            )
        )
        await db.commit()

        projections = await project_legacy_settings(db, apply=True)
        await db.commit()

        assert projections["planned"] == 2
        assert projections["created"] == 2
        legacy = await db.scalar(
            select(AppSetting).where(
                AppSetting.tenant_id == tenant.id,
                AppSetting.key == "company.profile",
            )
        )
        assert legacy is not None
        name = await db.scalar(
            select(AppSetting).where(
                AppSetting.tenant_id == tenant.id,
                AppSetting.key == "company.profile.name",
            )
        )
        assert name is not None
        assert name.value == "Legacy Co"
        currency = await db.scalar(
            select(AppSetting).where(
                AppSetting.tenant_id == tenant.id,
                AppSetting.key == "company.locale.currency",
            )
        )
        assert currency is not None
        assert currency.value == "INR"


@pytest.mark.asyncio
async def test_numbering_report_proposes_safe_next_number_and_applies_it():
    async with AsyncSessionLocal() as db:
        tenant = await db.scalar(select(Tenant).limit(1))
        assert tenant is not None
        sequence = await db.scalar(
            select(NumberSequence).where(
                NumberSequence.tenant_id == tenant.id,
                NumberSequence.key == "invoice",
            )
        )
        assert sequence is not None
        db.add(
            NumberSequencePeriod(
                tenant_id=tenant.id,
                sequence_id=sequence.id,
                fiscal_year="25-26",
                period_start=date(2025, 4, 1),
                period_end=date(2026, 3, 31),
                next_number=1,
            )
        )
        db.add(
            Invoice(
                tenant_id=tenant.id,
                invoice_number="INV/25-26/00042",
                issue_date=date(2025, 6, 1),
            )
        )
        await db.commit()

        report = await numbering_report(db)
        entry = next(
            row
            for row in report["rows"]
            if row["series"] == "invoice"
            and row["fiscal_year"] == "25-26"
            and row["tenant_id"] == uuid_key(tenant.id)
        )
        assert entry["max_suffix"] == 42
        assert entry["current_next_number"] == 1
        assert entry["proposed_next_number"] == 43
        assert not any("invoice/25-26" in finding for finding in report["findings"])

        applied = await apply_numbering_report(
            db, {"rows": [entry], "findings": []}
        )
        await db.commit()
        assert applied["changed"] >= 1
        period = await db.scalar(
            select(NumberSequencePeriod).where(
                NumberSequencePeriod.sequence_id == sequence.id,
                NumberSequencePeriod.fiscal_year == "25-26",
            )
        )
        assert period is not None
        assert period.next_number == 43
