import base64
import binascii
import hashlib
import hmac
import re
import secrets
import struct
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote
from uuid import UUID

import bcrypt
from jose import JWTError, jwt

from app.core.config import settings
from app.core.exceptions import UnauthorizedError, ValidationError

COMMON_PASSWORDS = {
    "password", "password1", "password123", "123456789", "12345678", "qwerty123",
    "admin@123", "admin1234", "letmein123", "welcome123", "iloveyou1", "abc123456",
}

_SEQUENCES = ("0123456789", "abcdefghijklmnopqrstuvwxyz", "qwertyuiop", "asdfghjkl", "zxcvbnm")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8")[:72], bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:72], hashed.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def verify_dummy_password(password: str) -> None:
    """Equalise timing between unknown-user and wrong-password login attempts."""
    bcrypt.checkpw(password.encode("utf-8")[:72], bcrypt.gensalt())


def validate_password_policy(
    password: str,
    *,
    email: str | None = None,
    full_name: str | None = None,
    history: list[str] | None = None,
) -> None:
    problems: list[str] = []
    if len(password) < settings.PASSWORD_MIN_LENGTH:
        problems.append(f"at least {settings.PASSWORD_MIN_LENGTH} characters")
    if len(password.encode("utf-8")) > 72:
        problems.append("at most 72 bytes")
    if settings.PASSWORD_REQUIRE_UPPER and not re.search(r"[A-Z]", password):
        problems.append("an uppercase letter")
    if settings.PASSWORD_REQUIRE_LOWER and not re.search(r"[a-z]", password):
        problems.append("a lowercase letter")
    if settings.PASSWORD_REQUIRE_DIGIT and not re.search(r"\d", password):
        problems.append("a number")
    if settings.PASSWORD_REQUIRE_SYMBOL and not re.search(r"[^A-Za-z0-9]", password):
        problems.append("a symbol")

    lowered = password.lower()
    if lowered in COMMON_PASSWORDS:
        problems.append("a password that is not commonly used")
    tokens = [part for part in re.split(r"[^a-z0-9]+", (email or "").lower() + " " + (full_name or "").lower()) if len(part) >= 3]
    if any(token in lowered for token in tokens):
        problems.append("no part of your name or email")
    if re.search(r"(.)\1{2,}", password):
        problems.append("no repeated character runs")
    if any(seq[i : i + 4] in lowered for seq in _SEQUENCES for i in range(len(seq) - 3)):
        problems.append("no sequential characters")
    if history and any(verify_password(password, old) for old in history[-settings.PASSWORD_HISTORY_SIZE :]):
        problems.append("a password you have not used recently")

    if problems:
        raise ValidationError("Password must contain " + ", ".join(problems))


def new_jti() -> str:
    return secrets.token_urlsafe(18)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _encode(
    subject: str,
    token_type: str,
    expires_delta: timedelta,
    tenant_id: str | None = None,
    token_version: int = 0,
    extra: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "tid": tenant_id,
        "ver": token_version,
        "jti": new_jti(),
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def create_access_token(
    subject: str | UUID,
    tenant_id: str | UUID | None = None,
    token_version: int = 0,
    session_id: str | UUID | None = None,
) -> str:
    return _encode(
        str(subject),
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        str(tenant_id) if tenant_id else None,
        token_version,
        {"sid": str(session_id)} if session_id else None,
    )


def create_refresh_token(
    subject: str | UUID,
    tenant_id: str | UUID | None = None,
    token_version: int = 0,
    session_id: str | UUID | None = None,
) -> str:
    return _encode(
        str(subject),
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        str(tenant_id) if tenant_id else None,
        token_version,
        {"sid": str(session_id)} if session_id else None,
    )


def create_challenge_token(subject: str | UUID, purpose: str) -> str:
    return _encode(
        str(subject),
        purpose,
        timedelta(minutes=settings.MFA_CHALLENGE_EXPIRE_MINUTES),
    )


def decode_token(token: str, expected_type: str = "access") -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    except JWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc

    if payload.get("type") != expected_type:
        raise UnauthorizedError("Invalid token type")
    if not payload.get("sub"):
        raise UnauthorizedError("Invalid token payload")
    return payload


def generate_totp_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def totp_code(secret: str, step: int | None = None) -> str:
    counter = int(time.time()) // 30 if step is None else step
    key = base64.b32decode(secret + "=" * (-len(secret) % 8))
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def verify_totp(secret: str, code: str, last_step: int | None = None) -> tuple[bool, int | None]:
    if not re.fullmatch(r"\d{6}", code or ""):
        return False, last_step
    current = int(time.time()) // 30
    try:
        for step in (current, current - 1, current + 1):
            if last_step is not None and step <= last_step:
                continue
            if hmac.compare_digest(totp_code(secret, step), code):
                return True, step
    except (ValueError, TypeError, binascii.Error):
        return False, last_step
    return False, last_step


def totp_uri(secret: str, email: str) -> str:
    label = quote(f"{settings.MFA_ISSUER}:{email}")
    return (
        f"otpauth://totp/{label}?secret={secret}"
        f"&issuer={quote(settings.MFA_ISSUER)}&algorithm=SHA1&digits=6&period=30"
    )


def generate_recovery_codes(count: int = 8) -> list[str]:
    return [f"{secrets.token_hex(3)}-{secrets.token_hex(3)}".upper() for _ in range(count)]
