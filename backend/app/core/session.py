import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.config import settings
from app.core.exceptions import UnauthorizedError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_token,
    new_jti,
)
from app.modules.identity.models import AuthSession, User


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _request_context(request: Request | None) -> tuple[str | None, str | None, str | None]:
    if request is None:
        return None, None, None
    agent = request.headers.get("user-agent")
    label = agent.split(")", 1)[0][:120] if agent else None
    ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else None
    )
    return ip, agent, label


async def create_session(
    db: AsyncSession, user: User, request: Request | None = None
) -> tuple[str, str, AuthSession]:
    ip, agent, label = _request_context(request)
    session = AuthSession(
        tenant_id=user.tenant_id,
        user_id=user.id,
        jti=new_jti(),
        refresh_hash=hash_token(secrets.token_urlsafe(32)),
        ip_address=ip,
        user_agent=agent,
        device_label=label,
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        last_used_at=datetime.now(timezone.utc),
    )
    db.add(session)
    await db.flush()
    refresh = create_refresh_token(user.id, user.tenant_id, user.token_version, session.id)
    access = create_access_token(user.id, user.tenant_id, user.token_version, session.id)
    session.refresh_hash = hash_token(refresh)
    await db.commit()
    return access, refresh, session


async def rotate_session(
    db: AsyncSession, refresh_token: str, request: Request | None = None
) -> tuple[str, str, AuthSession, User]:
    claims = decode_token(refresh_token, "refresh")
    try:
        user_id = UUID(claims["sub"])
        session_id = UUID(claims["sid"])
    except (KeyError, ValueError, TypeError) as exc:
        raise UnauthorizedError("Invalid refresh token") from exc

    user = await db.scalar(select(User).where(User.id == user_id))
    session = await db.scalar(select(AuthSession).where(AuthSession.id == session_id))
    if session is None or user is None or not user.is_active:
        raise UnauthorizedError("Session not found")
    if session.user_id != user.id or session.revoked_at is not None:
        raise UnauthorizedError("Session revoked, please sign in again")
    if _as_utc(session.expires_at) < datetime.now(timezone.utc):
        raise UnauthorizedError("Session expired, please sign in again")
    if int(claims.get("ver", 0)) != user.token_version:
        raise UnauthorizedError("Session revoked, please sign in again")

    if not secrets.compare_digest(session.refresh_hash, hash_token(refresh_token)):
        session.revoked_at = datetime.now(timezone.utc)
        for other in (await db.scalars(select(AuthSession).where(AuthSession.user_id == user.id))).all():
            other.revoked_at = session.revoked_at
        await record_audit(
            db,
            user=user,
            action="session.reuse_detected",
            module="identity",
            entity="auth_session",
            entity_id=session.id,
            request=request,
        )
        await db.commit()
        raise UnauthorizedError("Session revoked, please sign in again")

    ip, agent, _ = _request_context(request)
    refresh = create_refresh_token(user.id, user.tenant_id, user.token_version, session.id)
    access = create_access_token(user.id, user.tenant_id, user.token_version, session.id)
    session.refresh_hash = hash_token(refresh)
    session.last_used_at = datetime.now(timezone.utc)
    session.ip_address = ip or session.ip_address
    session.user_agent = agent or session.user_agent
    await db.commit()
    return access, refresh, session, user


async def user_sessions(db: AsyncSession, user_id: UUID) -> list[AuthSession]:
    rows = (
        await db.scalars(
            select(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .order_by(AuthSession.last_used_at.desc())
        )
    ).all()
    return list(rows)


async def revoke_session(db: AsyncSession, user_id: UUID, session_id: UUID) -> None:
    session = await db.scalar(
        select(AuthSession).where(AuthSession.id == session_id, AuthSession.user_id == user_id)
    )
    if session is None:
        raise UnauthorizedError("Session not found")
    session.revoked_at = datetime.now(timezone.utc)
    await db.commit()


async def revoke_all_sessions(db: AsyncSession, user_id: UUID) -> int:
    rows = (
        await db.scalars(
            select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        )
    ).all()
    now = datetime.now(timezone.utc)
    for session in rows:
        session.revoked_at = now
    await db.commit()
    return len(rows)


def session_payload(session: AuthSession, current: bool = False) -> dict[str, Any]:
    return {
        "id": session.id,
        "device_label": session.device_label,
        "ip_address": session.ip_address,
        "last_used_at": session.last_used_at,
        "expires_at": session.expires_at,
        "current": current,
    }
