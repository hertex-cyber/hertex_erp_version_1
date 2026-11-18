from datetime import datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from pydantic import EmailStr, Field

from app.core.schemas import ORMModel


class TenantCreate(ORMModel):
    name: str = Field(min_length=2, max_length=200)
    plan: str = "standard"


class TenantRead(ORMModel):
    id: UUID
    name: str
    slug: str
    plan: str
    is_active: bool
    created_at: datetime


class PermissionRead(ORMModel):
    id: UUID
    code: str
    module: str
    action: str
    description: str


class RoleBase(ORMModel):
    name: str = Field(min_length=2, max_length=120)
    slug: str = Field(min_length=2, max_length=120)
    description: str = ""
    approval_limit: Optional[Decimal] = None


class RoleCreate(RoleBase):
    permission_ids: list[UUID] = []


class RoleUpdate(ORMModel):
    name: Optional[str] = None
    description: Optional[str] = None
    approval_limit: Optional[Decimal] = None
    permission_ids: Optional[list[UUID]] = None
    is_active: Optional[bool] = None


class RoleRead(ORMModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    name: str
    slug: str
    description: str
    is_system: bool
    is_active: bool = True
    approval_limit: Optional[Decimal] = None
    permissions: list[PermissionRead] = []


class UserRead(ORMModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    email: EmailStr
    full_name: str
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: bool
    is_superuser: bool
    is_verified: bool
    last_login_at: Optional[datetime] = None
    created_at: datetime
    roles: list[RoleRead] = []


class UserCreate(ORMModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)
    full_name: str = Field(min_length=1, max_length=200)
    phone: Optional[str] = None
    role_ids: list[UUID] = []
    is_active: bool = True


class UserUpdate(ORMModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    is_active: Optional[bool] = None
    role_ids: Optional[list[UUID]] = None


class AdminPasswordReset(ORMModel):
    new_password: str = Field(min_length=12, max_length=72)


class LoginRequest(ORMModel):
    email: EmailStr
    password: str


class RegisterRequest(ORMModel):
    tenant_name: str = Field(min_length=2, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=12, max_length=72)


class RefreshRequest(ORMModel):
    refresh_token: Optional[str] = None


class TokenPair(ORMModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserRead


class AccessToken(ORMModel):
    access_token: str
    token_type: str = "bearer"


class MeUpdate(ORMModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None


class ChangePasswordRequest(ORMModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=72)


class MfaChallenge(ORMModel):
    mfa_required: bool = True
    challenge_token: str
    expires_in: int


class MfaSetupRead(ORMModel):
    secret: str
    uri: str
    recovery_codes: list[str] = []


class MfaEnableRequest(ORMModel):
    code: str = Field(min_length=6, max_length=6)
    recovery_codes: list[str]


class MfaDisableRequest(ORMModel):
    password: str


class MfaVerifyRequest(ORMModel):
    challenge_token: str
    code: Optional[str] = None
    recovery_code: Optional[str] = None


class MfaStatus(ORMModel):
    enabled: bool
    has_recovery_codes: bool = False


class ForgotPasswordRequest(ORMModel):
    email: EmailStr


class ForgotPasswordRead(ORMModel):
    message: str
    dev_token: Optional[str] = None


class ResetPasswordRequest(ORMModel):
    token: str
    new_password: str = Field(min_length=12, max_length=72)


class PasswordPolicyRead(ORMModel):
    min_length: int
    require_upper: bool
    require_lower: bool
    require_digit: bool
    require_symbol: bool
    history_size: int


class SessionRead(ORMModel):
    id: UUID
    device_label: Optional[str] = None
    ip_address: Optional[str] = None
    last_used_at: Optional[datetime] = None
    expires_at: datetime
    current: bool = False


class SecurityOverview(ORMModel):
    password_policy: PasswordPolicyRead
    mfa: MfaStatus
    sessions: list[SessionRead] = []
    last_logins: list[datetime] = []


class PermissionSummary(ORMModel):
    is_superuser: bool
    permissions: list[str]
    roles: list[str]
    tenant_id: Optional[UUID] = None


class AuditLogRead(ORMModel):
    id: UUID
    tenant_id: Optional[UUID] = None
    actor_id: Optional[UUID] = None
    actor_email: str
    action: str
    module: str
    entity: str
    entity_id: Optional[str] = None
    changes: dict = {}
    ip_address: Optional[str] = None
    created_at: datetime
