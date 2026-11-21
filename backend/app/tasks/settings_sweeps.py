from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.modules.settings import numbering
from app.modules.settings.models import NumberSequence

Sweep = Callable[[AsyncSession], Awaitable[dict]]

SOFT_TIME_LIMIT_SECONDS = 300
TIME_LIMIT_SECONDS = 600

_task_engine = create_async_engine(settings.DATABASE_URL, poolclass=NullPool, echo=False)
TaskSessionLocal = async_sessionmaker(
    _task_engine, class_=AsyncSession, expire_on_commit=False
)


async def _with_session(sweep: Sweep) -> dict:
    async with TaskSessionLocal() as db:
        return await sweep(db)


async def _periods(db: AsyncSession) -> dict:
    opened = await numbering.open_next_periods(db, days_ahead=7)
    return {"opened": opened}


async def _abandoned(db: AsyncSession) -> dict:
    voided = await numbering.sweep_abandoned_allocations(db, older_than_hours=24)
    return {"voided": voided}


async def _blocks(db: AsyncSession) -> dict:
    expired = await numbering.expire_blocks(db)
    return {"expired": expired}


async def _unreturned(db: AsyncSession) -> dict:
    tenant_ids = list((await db.scalars(select(NumberSequence.tenant_id).distinct())).all())
    reports = []
    for tenant_id in tenant_ids:
        reports.append(
            await numbering.refresh_unreturned_block_report(db, tenant_id=tenant_id)
        )
    return {"reports": reports}


def numbering_periods() -> dict:
    return asyncio.run(_with_session(_periods))


def numbering_abandoned() -> dict:
    return asyncio.run(_with_session(_abandoned))


def numbering_blocks() -> dict:
    return asyncio.run(_with_session(_blocks))


def numbering_unreturned() -> dict:
    return asyncio.run(_with_session(_unreturned))


TASKS = {
    "hertex.numbering.periods": numbering_periods,
    "hertex.numbering.abandoned": numbering_abandoned,
    "hertex.numbering.blocks": numbering_blocks,
    "hertex.numbering.unreturned": numbering_unreturned,
}

BEAT_SCHEDULE = {
    "numbering-periods": {"task": "hertex.numbering.periods", "schedule": 86400.0},
    "numbering-abandoned": {"task": "hertex.numbering.abandoned", "schedule": 3600.0},
    "numbering-blocks": {"task": "hertex.numbering.blocks", "schedule": 3600.0},
    "numbering-unreturned": {"task": "hertex.numbering.unreturned", "schedule": 21600.0},
}


def run_sweep(name: str) -> dict:
    if name not in TASKS:
        raise ValueError(f"Unknown sweep task '{name}'")
    return TASKS[name]()


def register(celery_app) -> None:
    for task_name, task_fn in TASKS.items():
        celery_app.task(
            name=task_name,
            ignore_result=True,
            autoretry_for=(Exception,),
            retry_backoff=5,
            retry_backoff_max=300,
            retry_jitter=True,
            max_retries=3,
            soft_time_limit=SOFT_TIME_LIMIT_SECONDS,
            time_limit=TIME_LIMIT_SECONDS,
        )(task_fn)
