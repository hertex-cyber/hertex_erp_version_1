import math
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.audit import record_audit
from app.core.config import settings
from app.core.deps import get_current_user, require_permissions, require_superuser
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, UnauthorizedError
from app.core.ratelimit import check_rate_limit
from app.core.schemas import Message, Page
from app.core.security import (
    create_challenge_token,
    decode_token,
    generate_recovery_codes,
    generate_totp_secret,
    hash_password,
    hash_token,
    totp_uri,
    validate_password_policy,
    verify_dummy_password,
    verify_password,
    verify_totp,
)
from app.core.session import (
    create_session,
    revoke_all_sessions,
    revoke_session,
    rotate_session,
    session_payload,
    user_sessions,
)
from app.db.session import get_db
from app.modules.identity.models import AuditLog, AuthToken, Permission, Role, Tenant, User
from app.modules.identity.schemas import (
    AdminPasswordReset,
    AuditLogRead,
    ChangePasswordRequest,
    ForgotPasswordRead,
    ForgotPasswordRequest,
    LoginRequest,
    MeUpdate,
    MfaChallenge,
    MfaDisableRequest,
    MfaEnableRequest,
    MfaSetupRead,
    MfaStatus,
    MfaVerifyRequest,
    PasswordPolicyRead,
    PermissionRead,
    PermissionSummary,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    RoleCreate,
    RoleRead,
    RoleUpdate,
    SecurityOverview,
    SessionRead,
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


def _set_auth_cookies(response: Response, refresh_token: str, csrf_token: str) -> None:
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        settings.CSRF_COOKIE_NAME,
        csrf_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie(settings.REFRESH_COOKIE_NAME, path="/")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")


def _require_csrf(request: Request) -> None:
    cookie = request.cookies.get(settings.CSRF_COOKIE_NAME)
    header = request.headers.get("x-csrf-token")
    if not cookie or not header or not secrets.compare_digest(cookie, header):
        raise UnauthorizedError("CSRF token missing or invalid")


def _client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


def _session_id(request: Request) -> uuid.UUID | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith("bearer "):
        return None
    try:
        return uuid.UUID(decode_token(header.split(None, 1)[1], "access").get("sid", ""))
    except (UnauthorizedError, ValueError, TypeError):
        return None


def _password_policy() -> PasswordPolicyRead:
    return PasswordPolicyRead(
        min_length=settings.PASSWORD_MIN_LENGTH,
        require_upper=settings.PASSWORD_REQUIRE_UPPER,
        require_lower=settings.PASSWORD_REQUIRE_LOWER,
        require_digit=settings.PASSWORD_REQUIRE_DIGIT,
        require_symbol=settings.PASSWORD_REQUIRE_SYMBOL,
        history_size=settings.PASSWORD_HISTORY_SIZE,
    )


async def _failed_login(
    db: AsyncSession,
    user: User | None,
    payload: LoginRequest,
    request: Request,
    reason: str,
) -> None:
    if user is not None:
        user.failed_login_count += 1
        if user.failed_login_count >= settings.MAX_FAILED_LOGINS:
            user.locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=settings.ACCOUNT_LOCKOUT_MINUTES
            )
            user.failed_login_count = 0
    await record_audit(
        db,
        user=user,
        action="login.failed",
        module="identity",
        entity="user",
        entity_id=user.id if user else None,
        changes={"email": payload.email, "reason": reason},
        request=request,
    )
    await db.commit()


async def _issue_tokens(
    db: AsyncSession, user: User, request: Request, response: Response
) -> TokenPair:
    access, refresh, session = await create_session(db, user, request)
    csrf = secrets.token_urlsafe(24)
    _set_auth_cookies(response, refresh, csrf)
    return TokenPair(
        access_token=access,
        refresh_token=refresh,
        user=UserRead.model_validate(user),
    )


@auth_router.post("/register", response_model=TokenPair, status_code=201)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = payload.email.lower()
    if await _get_user_by_email(db, email):
        raise ConflictError("An account with this email already exists")
    validate_password_policy(payload.password, email=email, full_name=payload.full_name)

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
        password_changed_at=datetime.now(timezone.utc),
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
        request=request,
    )
    await db.commit()
    user = await _get_user_by_id(db, user.id)
    assert user is not None
    return await _issue_tokens(db, user, request, response)


@auth_router.post("/login", response_model=TokenPair | MfaChallenge)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    email = payload.email.lower()
    ip = _client_ip(request) or "unknown"
    await check_rate_limit(f"login:ip:{ip}")
    await check_rate_limit(f"login:email:{email}")
    user = await _get_user_by_email(db, email)

    if user is None:
        verify_dummy_password(payload.password)
        await _failed_login(db, None, payload, request, "unknown_user")
        raise UnauthorizedError("Invalid email or password")
    if user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > datetime.now(timezone.utc):
        raise UnauthorizedError("Account temporarily locked. Please try again later.")
    if not verify_password(payload.password, user.hashed_password):
        await _failed_login(db, user, payload, request, "invalid_password")
        raise UnauthorizedError("Invalid email or password")
    if not user.is_active:
        raise ForbiddenError("Account is disabled")

    user.failed_login_count = 0
    user.locked_until = None
    if user.mfa_enabled:
        await db.commit()
        return MfaChallenge(
            challenge_token=create_challenge_token(user.id, "mfa_challenge"),
            expires_in=settings.MFA_CHALLENGE_EXPIRE_MINUTES * 60,
        )

    user.last_login_at = datetime.now(timezone.utc)
    await record_audit(
        db,
        user=user,
        action="login",
        module="identity",
        entity="user",
        entity_id=user.id,
        request=request,
    )
    await db.commit()
    user = await _get_user_by_id(db, user.id)
    assert user is not None
    return await _issue_tokens(db, user, request, response)


@auth_router.post("/mfa/verify", response_model=TokenPair)
async def verify_mfa(
    payload: MfaVerifyRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    claims = decode_token(payload.challenge_token, "mfa_challenge")
    try:
        user = await _get_user_by_id(db, uuid.UUID(claims["sub"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise UnauthorizedError("Invalid challenge") from exc
    if user is None or not user.mfa_enabled or not user.is_active:
        raise UnauthorizedError("Invalid challenge")

    if payload.recovery_code:
        code_hash = hash_token(payload.recovery_code.upper().strip())
        token = await db.scalar(
            select(AuthToken).where(
                AuthToken.user_id == user.id,
                AuthToken.purpose == "mfa_recovery",
                AuthToken.token_hash == code_hash,
                AuthToken.used_at.is_(None),
            )
        )
        if token is None:
            await record_audit(db, user=user, action="mfa.failed", module="identity", entity="user", entity_id=user.id, request=request)
            await db.commit()
            raise UnauthorizedError("Invalid recovery code")
        token.used_at = datetime.now(timezone.utc)
    else:
        valid, step = verify_totp(user.mfa_secret or "", payload.code or "")
        if not valid:
            await record_audit(db, user=user, action="mfa.failed", module="identity", entity="user", entity_id=user.id, request=request)
            await db.commit()
            raise UnauthorizedError("Invalid verification code")
        user.mfa_last_step = step or 0

    user.last_login_at = datetime.now(timezone.utc)
    await record_audit(db, user=user, action="mfa.verify", module="identity", entity="user", entity_id=user.id, request=request)
    await db.commit()
    user = await _get_user_by_id(db, user.id)
    assert user is not None
    return await _issue_tokens(db, user, request, response)


@auth_router.post("/mfa/setup", response_model=MfaSetupRead)
async def setup_mfa(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    secret = generate_totp_secret()
    user.mfa_secret = secret
    await db.commit()
    return MfaSetupRead(secret=secret, uri=totp_uri(secret, user.email), recovery_codes=generate_recovery_codes())


@auth_router.post("/mfa/enable", response_model=MfaStatus)
async def enable_mfa(
    payload: MfaEnableRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not user.mfa_secret:
        raise UnauthorizedError("Start MFA setup first")
    valid, step = verify_totp(user.mfa_secret, payload.code)
    if not valid:
        raise UnauthorizedError("Invalid verification code")
    user.mfa_enabled = True
    user.mfa_last_step = step or 0
    for code in payload.recovery_codes:
        db.add(
            AuthToken(
                tenant_id=user.tenant_id,
                user_id=user.id,
                token_hash=hash_token(code.upper().strip()),
                purpose="mfa_recovery",
                expires_at=datetime.now(timezone.utc) + timedelta(days=365),
            )
        )
    await record_audit(db, user=user, action="mfa.enabled", module="identity", entity="user", entity_id=user.id, request=request)
    await db.commit()
    return MfaStatus(enabled=True, has_recovery_codes=True)


@auth_router.post("/mfa/disable", response_model=MfaStatus)
async def disable_mfa(
    payload: MfaDisableRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.password, user.hashed_password):
        raise UnauthorizedError("Password is incorrect")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_last_step = 0
    for token in (await db.scalars(select(AuthToken).where(AuthToken.user_id == user.id, AuthToken.purpose == "mfa_recovery"))).all():
        token.used_at = datetime.now(timezone.utc)
    await record_audit(db, user=user, action="mfa.disabled", module="identity", entity="user", entity_id=user.id, request=request)
    await db.commit()
    return MfaStatus(enabled=False)


@auth_router.get("/mfa", response_model=MfaStatus)
async def mfa_status(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    codes = await db.scalar(
        select(func.count()).select_from(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == "mfa_recovery",
            AuthToken.used_at.is_(None),
        )
    )
    return MfaStatus(enabled=user.mfa_enabled, has_recovery_codes=bool(codes))


@auth_router.post("/refresh", response_model=TokenPair)
async def refresh(
    payload: RefreshRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    token = payload.refresh_token or request.cookies.get(settings.REFRESH_COOKIE_NAME)
    if not token:
        raise UnauthorizedError("Refresh token required")
    if not payload.refresh_token:
        _require_csrf(request)
        await check_rate_limit(f"refresh:ip:{_client_ip(request) or 'unknown'}")
    access, new_refresh, session, user = await rotate_session(db, token, request)
    csrf = secrets.token_urlsafe(24)
    _set_auth_cookies(response, new_refresh, csrf)
    return TokenPair(
        access_token=access,
        refresh_token=new_refresh,
        user=UserRead.model_validate(user),
    )


@auth_router.post("/forgot-password", response_model=ForgotPasswordRead)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(f"forgot:ip:{_client_ip(request) or 'unknown'}")
    user = await _get_user_by_email(db, payload.email.lower())
    dev_token = None
    if user and user.is_active:
        token = secrets.token_urlsafe(32)
        db.add(
            AuthToken(
                tenant_id=user.tenant_id,
                user_id=user.id,
                token_hash=hash_token(token),
                purpose="password_reset",
                expires_at=datetime.now(timezone.utc) + timedelta(minutes=settings.PASSWORD_RESET_EXPIRE_MINUTES),
            )
        )
        await record_audit(db, user=user, action="password.reset_requested", module="identity", entity="user", entity_id=user.id, request=request)
        await db.commit()
        if settings.ENVIRONMENT in {"development", "test"}:
            dev_token = token
    return ForgotPasswordRead(message="If the account exists, a reset link has been issued.", dev_token=dev_token)


@auth_router.post("/reset-password", response_model=Message)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    token = await db.scalar(
        select(AuthToken).where(
            AuthToken.token_hash == hash_token(payload.token),
            AuthToken.purpose == "password_reset",
            AuthToken.used_at.is_(None),
        )
    )
    if token is None or token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise UnauthorizedError("Reset link is invalid or expired")
    user = await _get_user_by_id(db, token.user_id)
    if user is None or not user.is_active:
        raise UnauthorizedError("Reset link is invalid or expired")
    validate_password_policy(
        payload.new_password,
        email=user.email,
        full_name=user.full_name,
        history=user.password_history,
    )
    user.password_history = (user.password_history or [])[-settings.PASSWORD_HISTORY_SIZE :] + [user.hashed_password]
    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.token_version += 1
    user.failed_login_count = 0
    user.locked_until = None
    token.used_at = datetime.now(timezone.utc)
    await revoke_all_sessions(db, user.id)
    await record_audit(db, user=user, action="password.reset", module="identity", entity="user", entity_id=user.id, request=request)
    await db.commit()
    return Message(message="Password reset. Please sign in again.")


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


@auth_router.post("/change-password", response_model=TokenPair)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not verify_password(payload.current_password, user.hashed_password):
        raise UnauthorizedError("Current password is incorrect")
    validate_password_policy(
        payload.new_password,
        email=user.email,
        full_name=user.full_name,
        history=user.password_history,
    )
    user.password_history = (user.password_history or [])[-settings.PASSWORD_HISTORY_SIZE :] + [user.hashed_password]
    user.hashed_password = hash_password(payload.new_password)
    user.password_changed_at = datetime.now(timezone.utc)
    user.token_version += 1
    await revoke_all_sessions(db, user.id)
    await record_audit(
        db,
        user=user,
        action="change_password",
        module="identity",
        entity="user",
        entity_id=user.id,
        request=request,
    )
    await db.commit()
    refreshed = await _get_user_by_id(db, user.id)
    assert refreshed is not None
    return await _issue_tokens(db, refreshed, request, response)


@auth_router.post("/logout", response_model=Message)
async def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    sid = _session_id(request)
    if sid:
        await revoke_session(db, user.id, sid)
    else:
        await revoke_all_sessions(db, user.id)
    await record_audit(db, user=user, action="logout", module="identity", entity="user", entity_id=user.id, request=request)
    await db.commit()
    _clear_auth_cookies(response)
    return Message(message="Signed out")


@auth_router.get("/sessions", response_model=list[SessionRead])
async def list_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current = _session_id(request)
    rows = await user_sessions(db, user.id)
    return [SessionRead(**session_payload(row, row.id == current)) for row in rows]


@auth_router.delete("/sessions/{session_id}", response_model=Message)
async def revoke_one_session(
    session_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await revoke_session(db, user.id, session_id)
    await record_audit(db, user=user, action="session.revoked", module="identity", entity="auth_session", entity_id=session_id, request=request)
    await db.commit()
    return Message(message="Session revoked")


@auth_router.delete("/sessions", response_model=Message)
async def revoke_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = await revoke_all_sessions(db, user.id)
    await record_audit(db, user=user, action="session.revoke_all", module="identity", entity="user", entity_id=user.id, changes={"count": count}, request=request)
    await db.commit()
    return Message(message=f"Revoked {count} sessions")


@auth_router.get("/security", response_model=SecurityOverview)
async def security_overview(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    current = _session_id(request)
    rows = await user_sessions(db, user.id)
    last_logins = list(
        (
            await db.scalars(
                select(AuditLog.created_at)
                .where(AuditLog.actor_id == user.id, AuditLog.action.in_(("login", "mfa.verify")))
                .order_by(AuditLog.created_at.desc())
                .limit(5)
            )
        ).all()
    )
    codes = await db.scalar(
        select(func.count()).select_from(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.purpose == "mfa_recovery",
            AuthToken.used_at.is_(None),
        )
    )
    return SecurityOverview(
        password_policy=_password_policy(),
        mfa=MfaStatus(enabled=user.mfa_enabled, has_recovery_codes=bool(codes)),
        sessions=[SessionRead(**session_payload(row, row.id == current)) for row in rows],
        last_logins=last_logins,
    )


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
    validate_password_policy(payload.password, email=email, full_name=payload.full_name)
    roles = await _resolve_roles(db, actor, payload.role_ids)
    db_user = User(
        tenant_id=actor.tenant_id,
        email=email,
        hashed_password=hash_password(payload.password),
        password_changed_at=datetime.now(timezone.utc),
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
    validate_password_policy(
        payload.new_password,
        email=db_user.email,
        full_name=db_user.full_name,
        history=db_user.password_history,
    )
    db_user.password_history = (db_user.password_history or [])[-settings.PASSWORD_HISTORY_SIZE :] + [db_user.hashed_password]
    db_user.hashed_password = hash_password(payload.new_password)
    db_user.password_changed_at = datetime.now(timezone.utc)
    db_user.token_version += 1
    await revoke_all_sessions(db, db_user.id)
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
    await revoke_all_sessions(db, db_user.id)
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
