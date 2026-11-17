from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def next_number(
    db: AsyncSession,
    model: type[Any],
    field: str,
    prefix: str,
    tenant_id: UUID | None,
    width: int = 5,
) -> str:
    """Generate a per-tenant sequential document number.

    Kept intentionally simple for scaffolding; a row-locked ``number_sequences``
    table can replace this without changing callers.
    """
    stmt = select(func.count()).select_from(model)
    if tenant_id and hasattr(model, "tenant_id"):
        stmt = stmt.where(model.tenant_id == tenant_id)  # type: ignore[attr-defined]
    count = int((await db.scalar(stmt)) or 0)
    return f"{prefix}-{count + 1:0{width}d}"
