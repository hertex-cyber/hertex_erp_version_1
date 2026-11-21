from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select, update

from app.db.session import AsyncSessionLocal
from app.modules.identity.models import User
from app.modules.settings.models import (
    NumberAllocation,
    NumberSequence,
)
from app.modules.settings.numbering import (
    ENGINE_FLAG,
    allocate_document,
    consume_block,
    numbering,
    validate_gst_renderable,
)
from app.tasks.settings_sweeps import (
    BEAT_SCHEDULE,
    SOFT_TIME_LIMIT_SECONDS,
    TASKS,
    TIME_LIMIT_SECONDS,
    _unreturned,
    run_sweep,
)


async def _user_and_sequence(db, key):
    user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
    sequence = NumberSequence(
        tenant_id=user.tenant_id,
        key=key,
        doc_type="internal",
        owner_module="test",
        pattern="RUN/{seq:05}",
        prefix="RUN",
        padding=5,
        start_number=1,
        increment=1,
        implementation="standard",
        reset_policy="never",
        status="active",
    )
    db.add(sequence)
    await db.flush()
    await db.commit()
    return user, sequence


@pytest.mark.asyncio
async def test_gst_render_validation_rejects_invalid_identifiers():
    validate_gst_renderable("INV/25-26/00001", doc_type="gst_invoice")
    with pytest.raises(Exception) as exc:
        validate_gst_renderable("inv/25-26/00001", doc_type="gst_invoice")
    assert exc.value.code == "numbering.pattern_invalid"
    with pytest.raises(Exception) as exc:
        validate_gst_renderable("INV/25-26/0000011", doc_type="gst_invoice", max_length=16)
    assert exc.value.code == "numbering.pattern_too_long"


@pytest.mark.asyncio
async def test_flag_off_uses_atomic_fallback(client, auth):
    changed = await client.put(
        f"/api/v1/settings/values/{ENGINE_FLAG}",
        headers=auth,
        json={"value": False, "reason": "runtime fallback test"},
    )
    assert changed.status_code == 200
    key = f"fallback_{uuid4().hex[:8]}"
    try:
        async with AsyncSessionLocal() as db:
            user, _sequence = await _user_and_sequence(db, key)
            first = await allocate_document(
                db, tenant_id=user.tenant_id, key=key, user=user
            )
            second = await allocate_document(
                db, tenant_id=user.tenant_id, key=key, user=user
            )
            assert first.number != second.number
            assert first.rendered.startswith("RUN/")
    finally:
        restored = await client.put(
            f"/api/v1/settings/values/{ENGINE_FLAG}",
            headers=auth,
            json={"value": True, "reason": "restore runtime fallback test"},
        )
        assert restored.status_code == 200


@pytest.mark.asyncio
async def test_offline_block_reserve_consume_and_return():
    async with AsyncSessionLocal() as db:
        user, sequence = await _user_and_sequence(db, f"block_{uuid4().hex[:8]}")
        block = await numbering.reserve_block(
            db,
            tenant_id=user.tenant_id,
            key=sequence.key,
            size=3,
            device_id="device-1",
            user=user,
        )
        allocated = await consume_block(db, block_id=block.id, user=user)
        assert allocated.rendered.startswith("RUN/")
        assert block.status == "partially_used"
        await numbering.return_block(
            db, block_id=block.id, used_up_to=allocated.number, user=user
        )
        assert block.status == "partially_used"
        assert block.used_count == 1
        unused = await db.scalar(
            select(NumberAllocation).where(
                NumberAllocation.sequence_id == sequence.id,
                NumberAllocation.number == allocated.number + 1,
            )
        )
        assert unused.status == "void"
        await db.commit()


@pytest.mark.asyncio
async def test_abandoned_sweep_declares_a_gap():
    async with AsyncSessionLocal() as db:
        user, sequence = await _user_and_sequence(db, f"sweep_{uuid4().hex[:8]}")
        allocation = await numbering.allocate(
            db, tenant_id=user.tenant_id, key=sequence.key, user=user
        )
        await db.execute(
            update(NumberAllocation)
                .where(NumberAllocation.id == allocation.allocation_id)
            .values(allocated_at=datetime.now(timezone.utc) - timedelta(hours=48))
        )
        await db.commit()
        from app.modules.settings.numbering import sweep_abandoned_allocations

        voided = await sweep_abandoned_allocations(db, older_than_hours=24)
        assert voided >= 1
        refreshed = await db.get(NumberAllocation, allocation.allocation_id)
        assert refreshed.status == "void"
        assert refreshed.reason_code == "abandoned"


@pytest.mark.asyncio
async def test_unreturned_report_refresh_and_task_registry():
    async with AsyncSessionLocal() as db:
        user, sequence = await _user_and_sequence(db, f"report_{uuid4().hex[:8]}")
        await numbering.reserve_block(
            db,
            tenant_id=user.tenant_id,
            key=sequence.key,
            size=2,
            device_id="device-2",
            user=user,
        )
        report = await _unreturned(db)
        tenant_report = next(
            item for item in report["reports"] if item["tenant_id"] == str(user.tenant_id)
        )
        assert tenant_report["total"] >= 1
        assert "hertex.numbering.unreturned" in TASKS


def test_celery_sweeps_are_registered_and_scheduled():
    from app.workers.celery_app import celery_app

    registered = {name for name in celery_app.tasks if name.startswith("hertex.numbering.")}
    assert registered == set(TASKS)
    for entry_name, entry in BEAT_SCHEDULE.items():
        assert celery_app.conf.beat_schedule[entry_name]["task"] == entry["task"]
    assert celery_app.conf.beat_scheduler == "celery.beat:PersistentScheduler"
    for name in TASKS:
        task = celery_app.tasks[name]
        assert task.max_retries == 3
        assert task.soft_time_limit == SOFT_TIME_LIMIT_SECONDS
        assert task.time_limit == TIME_LIMIT_SECONDS


def test_run_sweep_dispatches_only_registered_tasks(monkeypatch):
    calls: list[str] = []
    monkeypatch.setitem(TASKS, "test.sweep", lambda: calls.append("done") or {"done": True})
    assert run_sweep("test.sweep") == {"done": True}
    assert calls == ["done"]
    with pytest.raises(ValueError, match="Unknown sweep"):
        run_sweep("test.unknown")
