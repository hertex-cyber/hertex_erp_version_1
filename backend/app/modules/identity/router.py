import math
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.deps import get_current_user, require_permissions, require_superuser
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.schemas import Message, Page
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.session import get_db
from app.modules.identity.models import AuditLog, Permission, Role, Tenant, User
from app.modules.identity.schemas import (
    AccessToken,
    AdminPasswordReset,
    AuditLogRead,
    ChangePasswordRequest,
    LoginRequest,
    MeUpdate,
    PermissionRead,
    PermissionSummary,
    RefreshRequest,
    RegisterRequest,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    TenantCreate,
    TenantRead,
    TokenPair,
    UserCreate,
    UserRead,
    UserUpdate,
)

auth_router = APIRouter(prefix="/auth", tags=["Authentication"])
users_router = APIRouter(prefix="/users", tags=["Users & RBAC"])
roles_router = APIRouter(prefix="/roles", tags=["Users & RBAC"])
admin_router = APIRouter(prefix="/system", tags=["System"])


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "tenant"


USER_LOAD = (
    selectinload(User.roles).selectinload(Role.permissions),
    selectinload(User.tenant),
)


async def _get_user_by_email(db: AsyncSession, email: str) -> Optional[User]:
    return await db.scalar(select(User).options(*USER_LOAD).where(User.email == email.lower()))


async def _get_user_by_id(db: AsyncSession, user_id: uuid.UUID) -> Optional[User]:
    return await db.scalar(select(User).options(*USER_LOAD).where(User.id == user_id))


def _issue_tokens(user: User) -> TokenPair:
    return TokenPair(
        access_token=create_access_token(user.id, user.tenant_id, user.token_version),
        refresh_token=create_refresh_token(user.id, user.tenant_id, user.token_version),
        user=UserRead.model_validate(user),
    )


@auth_router.post("/register", response_model=TokenPair, status_code=201)
async def register(payload: RegisterRequest, db: AsyncSession = Depends(get_db)):
    email = payload.email.lower()
    if await _get_user_by_email(db, email):
        raise ConflictError("An account with this email already exists")

    tenant = Tenant(name=payload.tenant_name, slug=f"{slugify(payload.tenant_name)}-{uuid.uuid4().hex[:6]}")
    db.add(tenant)
    await db.flush()

    role = await db.scalar(
        select(Role).where(Role.slug == "tenant_admin", Role.tenant_id.is_(None))
    )
    user = User(
        tenant_id=tenant.id,
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        is_verified=True,
        roles=[role] if role else [],
    )
    db.add(user)
    await db.flush()
    await record_audit(
        db,
        user=user,
        action="register",
        module="system",
        entity="tenant",
        entity_id=tenant.id,
        changes={"tenant": tenant.name, "email": email},
    )
    await db.commit()
    user = await _get_user_by_id(db, user.id)
    assert user is not None
    return _issue_tokens(user)


@auth_router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user = await _get_user_by_email(db, payload.email)
    if user is None or not verify_password(payload.password, user.hashed_password):
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("Account is disabled")

    user.last_login_at = datetime.now(timezone.utc)
    await record_audit(
        db,
        user=user,
        action="login",
        module="system",
        entity="user",
        entity_id=user.id,
        request=request,
    )
    await db.commit()
    user = await _get_user_by_id(db, user.id)
    assert user is not None
    return _issue_tokens(user)


@auth_router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, db: AsyncSession = Depends(get_db)):
    claims = decode_token(payload.refresh_token, "refresh")
    user = await _get_user_by_id(db, uuid.UUID(claims["sub"]))
    if user is None or not user.is_active:
        raise UnauthorizedError("User not found or inactive")
    if int(claims.get("ver", 0)) != user.token_version:
        raise UnauthorizedError("Session revoked, please sign in again")
    return _issue_tokens(user)


@auth_router.get("/me", response_model=UserRead)
async def me(user: User = Depends(get_current_user)):
    return user


@auth_router.patch("/me", response_model=UserRead)
async def update_me(
    payload: MeUpdate,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    for field, value in data.items():
        setattr(user, field, value)
    await record_audit(
        db,
        user=user,
        action="update",
        module="system",
        entity="user",
        entity_id=user.id,
        changes=data,
        request=request,
    )
    await db.commit()
    updated_user = await _get_user_by_id(db, user.id)
    assert updated_user is not None
    return updated_user


@auth_router.get("/permissions", response_model=PermissionSummary)
async def my_permissions(user: User = Depends(get_current_user)):
    return PermissionSummary(
        is_superuser=user.is_superuser,
        permissions=sorted(user.permission_codes()),
        roles=[role.slug for role in user.roles],
        tenant_id=user.tenant_id,
    )


@auth_router.post("/change-password", response_model=AccessToken)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise UnauthorizedError("Current password is incorrect")
    user.hashed_password = hash_password(payload.new_password)
    user.token_version += 1
    await record_audit(
        db,
        user=user,
        action="change_password",
        module="system",
        entity="user",
        entity_id=user.id,
        request=request,
    )
    await db.commit()
    return AccessToken(access_token=create_access_token(user.id, user.tenant_id, user.token_version))


@auth_router.post("/logout", response_model=Message)
async def logout(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    user.token_version += 1
    await db.commit()
    return Message(message="Signed out")


# ── Users ────────────────────────────────────────────────────────────────────

manage_users = require_permissions("system.user.manage")


@users_router.get("", response_model=Page[UserRead])
async def list_users(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    q: Optional[str] = None,
    tenant_id: Optional[uuid.UUID] = None,
    user: User = Depends(manage_users),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).options(*USER_LOAD)
    count_stmt = select(func.count()).select_from(User)
    if not user.is_superuser:
        stmt = stmt.where(User.tenant_id == user.tenant_id)
        count_stmt = count_stmt.where(User.tenant_id == user.tenant_id)
    elif tenant_id:
        stmt = stmt.where(User.tenant_id == tenant_id)
        count_stmt = count_stmt.where(User.tenant_id == tenant_id)
    if q:
        pattern = f"%{q}%"
        clause = or_(User.email.ilike(pattern), User.full_name.ilike(pattern))
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    total = int((await db.scalar(count_stmt)) or 0)
    users = list(
        (await db.scalars(stmt.order_by(User.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    )
    return {"items": users, "total": total, "page": page, "size": size, "pages": max(1, math.ceil(total / size))}


async def _resolve_roles(db: AsyncSession, user: User, role_ids: list[uuid.UUID]) -> list[Role]:
    if not role_ids:
        return []
    roles = list((await db.scalars(select(Role).where(Role.id.in_(role_ids)))).all())
    for role in roles:
        if role.tenant_id is not None and role.tenant_id != user.tenant_id and not user.is_superuser:
            raise ForbiddenError("Cannot assign a role from another tenant")
    return roles


@users_router.post("", response_model=UserRead, status_code=201)
async def create_user(
    payload: UserCreate,
    request: Request,
    actor: User = Depends(manage_users),
    db: AsyncSession = Depends(get_db),
):
    email = payload.email.lower()
    if await _get_user_by_email(db, email):
        raise ConflictError("A user with this email already exists")
    roles = await _resolve_roles(db, actor, payload.role_ids)
    db_user = User(
        tenant_id=actor.tenant_id,
        email=email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        phone=payload.phone,
        is_active=payload.is_active,
        is_verified=True,
        roles=roles,
    )
    db.add(db_user)
    await db.flush()
    await record_audit(
        db,
        user=actor,
        action="create",
        module="system",
        entity="user",
        entity_id=db_user.id,
        changes={"email": email, "roles": [role.slug for role in roles]},
        request=request,
    )
    await db.commit()
    created = await _get_user_by_id(db, db_user.id)
    assert created is not None
    return created


@users_router.patch("/{user_id}", response_model=UserRead)
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    request: Request,
    actor: User = Depends(manage_users),
    db: AsyncSession = Depends(get_db),
):
    db_user = await db.scalar(select(User).options(*USER_LOAD).where(User.id == user_id))
    if db_user is None:
        raise NotFoundError("User not found")
    if not actor.is_superuser and db_user.tenant_id != actor.tenant_id:
        raise ForbiddenError("Cannot manage a user from another tenant")

    data = payload.model_dump(exclude_unset=True, exclude={"role_ids"})
    for field, value in data.items():
        setattr(db_user, field, value)
    if payload.role_ids is not None:
        db_user.roles = await _resolve_roles(db, actor, payload.role_ids)
    await record_audit(
        db,
        user=actor,
        action="update",
        module="system",
        entity="user",
        entity_id=db_user.id,
        changes=data,
        request=request,
    )
    await db.commit()
    updated = await _get_user_by_id(db, db_user.id)
    assert updated is not None
    return updated


@users_router.post("/{user_id}/reset-password", response_model=Message)
async def reset_user_password(
    user_id: uuid.UUID,
    payload: AdminPasswordReset,
    request: Request,
    actor: User = Depends(manage_users),
    db: AsyncSession = Depends(get_db),
):
    db_user = await db.scalar(select(User).where(User.id == user_id))
    if db_user is None:
        raise NotFoundError("User not found")
    if not actor.is_superuser and db_user.tenant_id != actor.tenant_id:
        raise ForbiddenError("Cannot manage a user from another tenant")
    db_user.hashed_password = hash_password(payload.new_password)
    db_user.token_version += 1
    await record_audit(
        db,
        user=actor,
        action="reset_password",
        module="system",
        entity="user",
        entity_id=db_user.id,
        request=request,
    )
    await db.commit()
    return Message(message="Password reset")


@users_router.delete("/{user_id}", response_model=Message)
async def deactivate_user(
    user_id: uuid.UUID,
    request: Request,
    actor: User = Depends(manage_users),
    db: AsyncSession = Depends(get_db),
):
    db_user = await db.scalar(select(User).where(User.id == user_id))
    if db_user is None:
        raise NotFoundError("User not found")
    if db_user.id == actor.id:
        raise ForbiddenError("You cannot deactivate your own account")
    if not actor.is_superuser and db_user.tenant_id != actor.tenant_id:
        raise ForbiddenError("Cannot manage a user from another tenant")
    db_user.is_active = False
    db_user.token_version += 1
    await record_audit(
        db,
        user=actor,
        action="deactivate",
        module="system",
        entity="user",
        entity_id=db_user.id,
        request=request,
    )
    await db.commit()
    return Message(message="User deactivated")


# ── Roles & permissions ─────────────────────────────────────────────────────

manage_roles = require_permissions("system.role.manage")


@roles_router.get("", response_model=list[RoleRead])
async def list_roles(
    actor: User = Depends(manage_roles),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Role).options(selectinload(Role.permissions)).order_by(Role.name)
    if not actor.is_superuser:
        stmt = stmt.where(or_(Role.tenant_id.is_(None), Role.tenant_id == actor.tenant_id))
    return list((await db.scalars(stmt)).all())


@roles_router.post("", response_model=RoleRead, status_code=201)
async def create_role(
    payload: RoleCreate,
    actor: User = Depends(manage_roles),
    db: AsyncSession = Depends(get_db),
):
    perms = []
    if payload.permission_ids:
        perms = list(
            (await db.scalars(select(Permission).where(Permission.id.in_(payload.permission_ids)))).all()
        )
    role = Role(
        tenant_id=actor.tenant_id,
        name=payload.name,
        slug=payload.slug,
        description=payload.description,
        approval_limit=payload.approval_limit,
        is_system=False,
        permissions=perms,
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return role


@roles_router.patch("/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: uuid.UUID,
    payload: RoleUpdate,
    actor: User = Depends(manage_roles),
    db: AsyncSession = Depends(get_db),
):
    role = await db.scalar(
        select(Role).options(selectinload(Role.permissions)).where(Role.id == role_id)
    )
    if role is None:
        raise NotFoundError("Role not found")
    if role.is_system or (role.tenant_id not in (None, actor.tenant_id) and not actor.is_superuser):
        raise ForbiddenError("System and cross-tenant roles cannot be edited")
    data = payload.model_dump(exclude_unset=True, exclude={"permission_ids"})
    for field, value in data.items():
        setattr(role, field, value)
    if payload.permission_ids is not None:
        role.permissions = list(
            (await db.scalars(select(Permission).where(Permission.id.in_(payload.permission_ids)))).all()
        )
    await db.commit()
    return role


@roles_router.delete("/{role_id}", response_model=Message)
async def delete_role(
    role_id: uuid.UUID,
    actor: User = Depends(manage_roles),
    db: AsyncSession = Depends(get_db),
):
    role = await db.scalar(select(Role).where(Role.id == role_id))
    if role is None:
        raise NotFoundError("Role not found")
    if role.is_system or (role.tenant_id not in (None, actor.tenant_id) and not actor.is_superuser):
        raise ForbiddenError("System and cross-tenant roles cannot be deleted")
    role.is_active = False
    await db.commit()
    return Message(message="Role deactivated")


@roles_router.get("/permissions/catalog", response_model=list[PermissionRead])
async def permission_catalog(
    actor: User = Depends(manage_roles),
    db: AsyncSession = Depends(get_db),
):
    perms = list((await db.scalars(select(Permission).order_by(Permission.module, Permission.code))).all())
    return perms


# ── System: tenants + audit ─────────────────────────────────────────────────

@admin_router.get("/tenants", response_model=list[TenantRead])
async def list_tenants(
    actor: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    return list((await db.scalars(select(Tenant).order_by(Tenant.name))).all())


@admin_router.post("/tenants", response_model=TenantRead, status_code=201)
async def create_tenant(
    payload: TenantCreate,
    actor: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
):
    tenant = Tenant(name=payload.name, slug=f"{slugify(payload.name)}-{uuid.uuid4().hex[:6]}", plan=payload.plan)
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@admin_router.get("/audit-logs", response_model=Page[AuditLogRead])
async def list_audit_logs(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    module: Optional[str] = None,
    action: Optional[str] = None,
    actor: User = Depends(require_permissions("system.audit.read")),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(AuditLog)
    count_stmt = select(func.count()).select_from(AuditLog)
    if not actor.is_superuser and actor.tenant_id:
        stmt = stmt.where(AuditLog.tenant_id == actor.tenant_id)
        count_stmt = count_stmt.where(AuditLog.tenant_id == actor.tenant_id)
    if module:
        stmt = stmt.where(AuditLog.module == module)
        count_stmt = count_stmt.where(AuditLog.module == module)
    if action:
        stmt = stmt.where(AuditLog.action == action)
        count_stmt = count_stmt.where(AuditLog.action == action)
    total = int((await db.scalar(count_stmt)) or 0)
    items = list(
        (await db.scalars(stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * size).limit(size))).all()
    )
    return {"items": items, "total": total, "page": page, "size": size, "pages": max(1, math.ceil(total / size))}
