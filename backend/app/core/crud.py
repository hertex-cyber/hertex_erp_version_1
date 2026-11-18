"""Reusable tenant-scoped CRUD service + router factory.

Every business module gets consistent pagination, search, filtering, soft delete,
tenant isolation and audit logging without copying boilerplate.
"""

import math
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel
from sqlalchemy import Select, Uuid, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.deps import require_permissions
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.schemas import Page
from app.db.session import get_db
from app.modules.identity.models import User


def tenant_scoped(stmt: Select, model: type[Any], user: User) -> Select:
    if hasattr(model, "tenant_id") and not user.is_superuser and user.tenant_id:
        stmt = stmt.where(model.tenant_id == user.tenant_id)  # type: ignore[attr-defined]
    return stmt


def coerce_identifier(value: Any, entity: str = "Record") -> UUID:
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError) as exc:
        raise NotFoundError(f"{entity} not found") from exc


class CRUDService:
    def __init__(
        self,
        model: type[Any],
        *,
        search_fields: tuple[str, ...] = (),
        filter_fields: tuple[str, ...] = (),
        load_options: tuple[Any, ...] = (),
        soft_delete: bool = True,
        number_field: Optional[str] = None,
        number_prefix: Optional[str] = None,
        immutable: bool = False,
    ):
        self.model = model
        self.search_fields = search_fields
        self.filter_fields = filter_fields
        self.load_options = load_options
        self.soft_delete = soft_delete
        self.number_field = number_field
        self.number_prefix = number_prefix
        self.immutable = immutable

    def base_select(self, user: User) -> Select:
        stmt = select(self.model)
        if self.load_options:
            stmt = stmt.options(*self.load_options)
        return tenant_scoped(stmt, self.model, user)

    async def get(self, db: AsyncSession, user: User, item_id: Any) -> Any:
        identifier = coerce_identifier(item_id, self.model.__name__)
        stmt = tenant_scoped(select(self.model), self.model, user).where(
            self.model.id == identifier
        )
        if self.load_options:
            stmt = stmt.options(*self.load_options)
        obj = await db.scalar(stmt)
        if obj is None:
            raise NotFoundError(f"{self.model.__name__} not found")
        return obj

    async def list(
        self,
        db: AsyncSession,
        user: User,
        *,
        page: int,
        size: int,
        search: Optional[str],
        filters: dict[str, Any],
        include_inactive: bool = False,
    ) -> tuple[list[Any], int]:
        stmt = self.base_select(user)
        count_stmt = tenant_scoped(select(func.count()).select_from(self.model), self.model, user)

        if self.soft_delete and hasattr(self.model, "is_active") and not include_inactive:
            stmt = stmt.where(self.model.is_active.is_(True))
            count_stmt = count_stmt.where(self.model.is_active.is_(True))

        if search and self.search_fields:
            clauses = [
                getattr(self.model, field).ilike(f"%{search}%") for field in self.search_fields
            ]
            stmt = stmt.where(or_(*clauses))
            count_stmt = count_stmt.where(or_(*clauses))

        for field, value in filters.items():
            if field not in self.filter_fields or value in (None, ""):
                continue
            column = getattr(self.model, field)
            if isinstance(column.type, Uuid):
                value = coerce_identifier(value, field)
            if isinstance(value, str) and value.lower() in {"true", "false"}:
                column = column.is_(value.lower() == "true")
            stmt = stmt.where(column == value)
            count_stmt = count_stmt.where(column == value)

        total = int((await db.scalar(count_stmt)) or 0)
        order_column = getattr(self.model, "created_at", self.model.id)
        stmt = stmt.order_by(order_column.desc()).offset((page - 1) * size).limit(size)
        items = list((await db.scalars(stmt)).all())
        return items, total

    async def create(self, db: AsyncSession, user: User, data: dict[str, Any]) -> Any:
        if hasattr(self.model, "tenant_id") and "tenant_id" not in data:
            data["tenant_id"] = user.tenant_id
        if hasattr(self.model, "created_by_id") and "created_by_id" not in data:
            data["created_by_id"] = user.id
        if self.number_field and not data.get(self.number_field):
            from app.core.numbering import next_number

            data[self.number_field] = await next_number(
                db,
                self.model,
                self.number_field,
                self.number_prefix or "DOC",
                user.tenant_id,
            )
        obj = self.model(**data)
        db.add(obj)
        await db.flush()
        return obj

    async def update(self, db: AsyncSession, user: User, item_id: Any, data: dict[str, Any]) -> Any:
        if self.immutable:
            raise ForbiddenError(f"{self.model.__name__} records are immutable")
        obj = await self.get(db, user, item_id)
        for field, value in data.items():
            if hasattr(obj, field):
                setattr(obj, field, value)
        await db.flush()
        return obj

    async def delete(self, db: AsyncSession, user: User, item_id: Any) -> None:
        if self.immutable:
            raise ForbiddenError(f"{self.model.__name__} records are immutable")
        obj = await self.get(db, user, item_id)
        if self.soft_delete and hasattr(obj, "is_active"):
            obj.is_active = False
        else:
            await db.delete(obj)
        await db.flush()


def build_crud_router(
    *,
    model: type[Any],
    read_schema: type[BaseModel],
    create_schema: type[BaseModel],
    update_schema: type[BaseModel],
    prefix: str,
    tags: Sequence[str],
    permission_prefix: str,
    module: str,
    entity: str,
    search_fields: tuple[str, ...] = (),
    filter_fields: tuple[str, ...] = (),
    load_options: tuple[Any, ...] = (),
    soft_delete: bool = True,
    number_field: Optional[str] = None,
    number_prefix: Optional[str] = None,
    serializer: Optional[Callable[[Any, User], dict[str, Any]]] = None,
    base_path: str = "",
    create_enabled: bool = True,
    update_enabled: bool = True,
    delete_enabled: bool = True,
    immutable: bool = False,
    update_guard: Optional[Callable[[AsyncSession, User, Any, dict[str, Any]], Awaitable[None]]] = None,
    delete_guard: Optional[Callable[[AsyncSession, User, Any], Awaitable[None]]] = None,
    idempotency_hooks: Optional[tuple[Callable, Callable]] = None,
    after_create: Optional[
        Callable[[AsyncSession, User, Any, dict[str, Any], Request], Awaitable[None]]
    ] = None,
    after_update: Optional[
        Callable[[AsyncSession, User, Any, dict[str, Any], Request], Awaitable[None]]
    ] = None,
) -> tuple[APIRouter, CRUDService]:
    router = APIRouter(prefix=prefix, tags=list(tags))
    service = CRUDService(
        model,
        search_fields=search_fields,
        filter_fields=filter_fields,
        load_options=load_options,
        soft_delete=soft_delete,
        number_field=number_field,
        number_prefix=number_prefix,
        immutable=immutable,
    )

    read_dep = require_permissions(f"{permission_prefix}.read")
    create_dep = require_permissions(f"{permission_prefix}.create")
    update_dep = require_permissions(f"{permission_prefix}.update")
    delete_dep = require_permissions(f"{permission_prefix}.delete")

    PageSchema = Page[read_schema]  # type: ignore[valid-type]

    @router.get(base_path, response_model=PageSchema)
    async def list_items(
        request: Request,
        page: int = Query(1, ge=1),
        size: int = Query(50, ge=1, le=200),
        q: Optional[str] = None,
        include_inactive: bool = False,
        user: User = Depends(read_dep),
        db: AsyncSession = Depends(get_db),
    ):
        filters = {
            field: request.query_params.get(field)
            for field in filter_fields
            if request.query_params.get(field) not in (None, "")
        }
        items, total = await service.list(
            db,
            user,
            page=page,
            size=size,
            search=q,
            filters=filters,
            include_inactive=include_inactive,
        )
        if serializer:
            items = [serializer(item, user) for item in items]
        return {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
            "pages": max(1, math.ceil(total / size)),
        }

    if create_enabled:
        @router.post(base_path, response_model=read_schema, status_code=201)
        async def create_item(
            payload: create_schema,  # type: ignore[valid-type]
            request: Request,
            user: User = Depends(create_dep),
            db: AsyncSession = Depends(get_db),
        ):
            data = payload.model_dump(exclude_unset=True)
            idempotency_key = request.headers.get("idempotency-key")
            scope = f"{request.method}:{request.url.path}"
            if idempotency_key and idempotency_hooks:
                cached = await idempotency_hooks[0](db, user, scope, idempotency_key)
                if cached is not None:
                    return cached["response"]
            try:
                obj = await service.create(db, user, data)
                await record_audit(
                    db,
                    user=user,
                    action="create",
                    module=module,
                    entity=entity,
                    entity_id=getattr(obj, "id", None),
                    changes=data,
                    request=request,
                )
                await db.commit()
                await db.refresh(obj)
                if after_create is not None:
                    await after_create(db, user, obj, data, request)
                result = serializer(obj, user) if serializer else obj
                if idempotency_key and idempotency_hooks:
                    await idempotency_hooks[1](db, user, scope, idempotency_key, result, 201)
                    await db.commit()
                return result
            except IntegrityError as exc:
                await db.rollback()
                raise ConflictError(f"{entity} conflicts with an existing record") from exc

    @router.get("/{item_id}", response_model=read_schema)
    async def get_item(
        item_id: str,
        user: User = Depends(read_dep),
        db: AsyncSession = Depends(get_db),
    ):
        obj = await service.get(db, user, item_id)
        return serializer(obj, user) if serializer else obj

    if update_enabled:
        @router.patch("/{item_id}", response_model=read_schema)
        async def update_item(
            item_id: str,
            payload: update_schema,  # type: ignore[valid-type]
            request: Request,
            user: User = Depends(update_dep),
            db: AsyncSession = Depends(get_db),
        ):
            data = payload.model_dump(exclude_unset=True)
            idempotency_key = request.headers.get("idempotency-key")
            scope = f"{request.method}:{request.url.path}"
            if idempotency_key and idempotency_hooks:
                cached = await idempotency_hooks[0](db, user, scope, idempotency_key)
                if cached is not None:
                    return cached["response"]
            try:
                if update_guard:
                    raw_body: dict[str, Any] = {}
                    try:
                        raw_body = await request.json()
                    except Exception:
                        raw_body = {}
                    await update_guard(db, user, item_id, raw_body if isinstance(raw_body, dict) else {})
                obj = await service.update(db, user, item_id, data)
                await record_audit(
                    db,
                    user=user,
                    action="update",
                    module=module,
                    entity=entity,
                    entity_id=item_id,
                    changes=data,
                    request=request,
                )
                await db.commit()
                await db.refresh(obj)
                if after_update is not None:
                    await after_update(db, user, obj, data, request)
                result = serializer(obj, user) if serializer else obj
                if idempotency_key and idempotency_hooks:
                    await idempotency_hooks[1](db, user, scope, idempotency_key, result, 200)
                    await db.commit()
                return result
            except IntegrityError as exc:
                await db.rollback()
                raise ConflictError(f"{entity} conflicts with an existing record") from exc

    if delete_enabled:
        @router.delete("/{item_id}")
        async def delete_item(
            item_id: str,
            request: Request,
            user: User = Depends(delete_dep),
            db: AsyncSession = Depends(get_db),
        ):
            if delete_guard:
                await delete_guard(db, user, item_id)
            await service.delete(db, user, item_id)
            await record_audit(
                db,
                user=user,
                action="delete",
                module=module,
                entity=entity,
                entity_id=item_id,
                request=request,
            )
            await db.commit()
            return {"message": f"{entity} deleted"}

    return router, service
