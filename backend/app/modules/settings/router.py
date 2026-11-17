from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.crud import build_crud_router
from app.core.deps import require_permissions
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.modules.identity.models import User
from app.modules.settings.models import AppSetting, NumberSequence
from app.modules.settings.schemas import (
    SequenceCreate,
    SequenceNext,
    SequenceRead,
    SequenceUpdate,
    SettingCreate,
    SettingRead,
    SettingUpdate,
)

router = APIRouter(prefix="/settings")


def _include(**kwargs):
    child, _ = build_crud_router(module="settings", **kwargs)
    router.include_router(child)


_include(
    model=AppSetting,
    read_schema=SettingRead,
    create_schema=SettingCreate,
    update_schema=SettingUpdate,
    prefix="/values",
    tags=["Settings · Values"],
    permission_prefix="settings.setting",
    entity="AppSetting",
    search_fields=("key", "category", "description"),
    filter_fields=("category",),
)

_include(
    model=NumberSequence,
    read_schema=SequenceRead,
    create_schema=SequenceCreate,
    update_schema=SequenceUpdate,
    prefix="/sequences",
    tags=["Settings · Sequences"],
    permission_prefix="settings.sequence",
    entity="NumberSequence",
    search_fields=("key", "prefix"),
)


@router.post(
    "/sequences/{key}/next",
    response_model=SequenceNext,
    tags=["Settings · Sequences"],
)
async def next_sequence_number(
    key: str,
    user: User = Depends(require_permissions("settings.sequence.update")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(NumberSequence).where(NumberSequence.key == key)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(NumberSequence.tenant_id == user.tenant_id)
    sequence = await db.scalar(stmt)
    if sequence is None:
        raise NotFoundError("Number sequence not found")
    number = f"{sequence.prefix}-{sequence.next_number:0{sequence.padding}d}"
    sequence.next_number += 1
    await db.commit()
    return SequenceNext(key=key, number=number)
