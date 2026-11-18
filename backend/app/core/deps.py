import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.modules.identity.models import AuthSession, Role, User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Authentication required")

    payload = decode_token(credentials.credentials, "access")
    try:
        user_id = uuid.UUID(payload["sub"])
    except (ValueError, KeyError) as exc:
        raise UnauthorizedError("Invalid token subject") from exc

    user = await db.scalar(
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == user_id, User.is_active.is_(True))
    )
    if user is None:
        raise UnauthorizedError("User not found or inactive")
    if int(payload.get("ver", 0)) != user.token_version:
        raise UnauthorizedError("Session revoked, please sign in again")
    session_id = payload.get("sid")
    if session_id:
        try:
            session = await db.scalar(
                select(AuthSession).where(
                    AuthSession.id == uuid.UUID(str(session_id)),
                    AuthSession.user_id == user.id,
                )
            )
        except (ValueError, TypeError) as exc:
            raise UnauthorizedError("Invalid session") from exc
        if session is None or session.revoked_at is not None:
            raise UnauthorizedError("Session revoked, please sign in again")
        expires_at = session.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at < datetime.now(timezone.utc):
            raise UnauthorizedError("Session expired, please sign in again")
    return user


async def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    if credentials is None:
        return None
    try:
        return await get_current_user(credentials, db)
    except UnauthorizedError:
        return None


async def require_superuser(user: User = Depends(get_current_user)) -> User:
    if not user.is_superuser:
        raise ForbiddenError("Superadmin access required")
    return user


def require_permissions(*codes: str):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if not user.has_any_permission(list(codes)):
            raise ForbiddenError(f"Missing permission: {' or '.join(codes)}")
        return user

    return dependency


def require_all_permissions(*codes: str):
    async def dependency(user: User = Depends(get_current_user)) -> User:
        if user.is_superuser:
            return user
        granted = user.permission_codes()
        missing = [code for code in codes if code not in granted]
        if missing:
            raise ForbiddenError(f"Missing permissions: {', '.join(missing)}")
        return user

    return dependency


def client_ip(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None
