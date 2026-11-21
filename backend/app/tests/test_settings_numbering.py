import asyncio
from uuid import uuid4

import pytest

from app.db.session import AsyncSessionLocal
from app.modules.identity.models import AuditLog
from app.modules.settings.models import NumberSequence
from app.modules.settings.numbering import commit, numbering


async def _create_sequence(db, tenant_id, key):
    sequence = NumberSequence(
        tenant_id=tenant_id,
        key=key,
        doc_type="internal",
        owner_module="test",
        pattern="TST/{seq:05}",
        prefix="TST",
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
    return sequence


@pytest.mark.asyncio
async def test_unknown_setting_and_deprecated_next_endpoint(client, auth):
    unknown = await client.put(
        "/api/v1/settings/values/not.a.real.setting",
        headers=auth,
        json={"value": "x", "scope": "tenant", "reason": "test"},
    )
    assert unknown.status_code == 422

    deprecated = await client.post("/api/v1/settings/sequences/invoice/next", headers=auth)
    assert deprecated.status_code == 410


@pytest.mark.asyncio
async def test_preview_does_not_consume_and_allocation_is_idempotent(client, auth):
    preview = await client.post(
        "/api/v1/settings/sequences/invoice/preview",
        headers=auth,
        json={},
    )
    assert preview.status_code == 200
    before = preview.json()["next_number"]

    idem = uuid4().hex
    first = await client.post(
        "/api/v1/settings/sequences/invoice/allocate",
        headers=auth,
        json={"idempotency_key": idem, "document_type": "gst_invoice"},
    )
    assert first.status_code == 200
    rendered = first.json()["rendered"]

    second = await client.post(
        "/api/v1/settings/sequences/invoice/allocate",
        headers=auth,
        json={"idempotency_key": idem, "document_type": "gst_invoice"},
    )
    assert second.status_code == 200
    assert second.json()["rendered"] == rendered

    preview_after = await client.post(
        "/api/v1/settings/sequences/invoice/preview",
        headers=auth,
        json={},
    )
    assert preview_after.status_code == 200
    assert preview_after.json()["next_number"] >= before + 1


@pytest.mark.asyncio
async def test_concurrent_allocations_return_unique_numbers(client, auth):
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        from app.modules.identity.models import User
        user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        sequence = await _create_sequence(db, user.tenant_id, f"concurrent_{uuid4().hex[:8]}")
        tenant_id = user.tenant_id

    sequence_key = sequence.key

    async def allocate_one():
        async with AsyncSessionLocal() as db:
            allocation = await numbering.allocate(db, tenant_id=tenant_id, key=sequence_key, on_date=None)
            await db.commit()
            return allocation.rendered

    async with AsyncSessionLocal() as probe:
        dialect = probe.get_bind().dialect.name

    if dialect == "sqlite":
        results = []
        async with AsyncSessionLocal() as db:
            for _ in range(30):
                allocation = await numbering.allocate(db, tenant_id=tenant_id, key=sequence_key, on_date=None)
                await db.commit()
                results.append(allocation.rendered)
    else:
        results = await asyncio.gather(*(allocate_one() for _ in range(30)))
    assert len(results) == len(set(results))


@pytest.mark.asyncio
async def test_void_creates_a_declared_gap(auth):
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        from app.modules.identity.models import User
        user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        key = f"void_{uuid4().hex[:8]}"
        await _create_sequence(db, user.tenant_id, key)
        allocation = await numbering.allocate(db, tenant_id=user.tenant_id, key=key, user=user)
        voided = await numbering.void(
            db,
            tenant_id=user.tenant_id,
            key=key,
            rendered=allocation.rendered,
            reason_code="cancelled",
            reason_text="test cancellation",
            user=user,
        )
        await db.commit()
        assert voided.status == "void"


@pytest.mark.asyncio
async def test_commit_is_idempotent_and_audited():
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        from app.modules.identity.models import User

        user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        key = f"commit_{uuid4().hex[:8]}"
        await _create_sequence(db, user.tenant_id, key)
        allocation = await numbering.allocate(db, tenant_id=user.tenant_id, key=key, user=user)
        document_id = uuid4()
        first = await commit(
            db,
            allocation,
            document_type="TestDoc",
            document_id=document_id,
            tenant_id=user.tenant_id,
            user=user,
        )
        second = await commit(
            db,
            allocation,
            document_type="TestDoc",
            document_id=document_id,
            tenant_id=user.tenant_id,
            user=user,
        )
        assert first.id == second.id == allocation.allocation_id
        assert second.status == "committed"
        assert second.document_id == document_id
        actions = set(
            (
                await db.scalars(
                    select(AuditLog.action).where(
                        AuditLog.entity == "NumberAllocation",
                        AuditLog.entity_id == str(allocation.allocation_id),
                    )
                )
            ).all()
        )
        assert {"numbering.allocated", "numbering.committed"} <= actions
        await db.commit()


@pytest.mark.asyncio
async def test_independent_series_can_share_rendered_number():
    async with AsyncSessionLocal() as db:
        from sqlalchemy import select

        from app.modules.identity.models import User

        user = await db.scalar(select(User).where(User.email == "admin@hertex.dev"))
        first_key = f"shared_a_{uuid4().hex[:6]}"
        second_key = f"shared_b_{uuid4().hex[:6]}"
        for key in (first_key, second_key):
            await _create_sequence(db, user.tenant_id, key)
        first = await numbering.allocate(db, tenant_id=user.tenant_id, key=first_key, user=user)
        second = await numbering.allocate(db, tenant_id=user.tenant_id, key=second_key, user=user)
        assert first.rendered == second.rendered
        await db.commit()
