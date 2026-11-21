"""Settings & numbering API schemas (module 15A)."""

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


# --------------------------------------------------------------------- values
class RegistryItem(ORMModel):
    key: str
    type: str
    module: str
    label: str
    help: str = ""
    choices: Optional[list[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    regex: Optional[str] = None
    critical: bool
    deploy_only: bool
    immutable_after: Optional[str] = None
    scopes: list[str]
    default: Any = None
    data_impact: str = "none"
    is_secret: bool = False
    env_var: Optional[str] = None
    json_schema: Optional[dict[str, Any]] = None


class SettingRead(ORMModel):
    id: UUID
    key: str
    value: Any = None
    category: str
    description: str
    scope_type: str = "tenant"
    scope_id: Optional[UUID] = None
    value_type: str = "json"
    is_secret: bool = False
    data_impact: str = "none"
    version: int = 1
    source: str = "admin"
    is_active: bool
    created_at: datetime


class SettingWrite(ORMModel):
    value: Any = None
    scope: str = "tenant"
    scope_id: Optional[UUID] = None
    reason: Optional[str] = None
    version: Optional[int] = None


class SettingWriteResult(ORMModel):
    key: str
    value: Any = None
    source: str = "admin"
    applied: bool = True
    approval_state: Optional[str] = None
    id: Optional[str] = None
    message: Optional[str] = None


class EffectiveSetting(ORMModel):
    key: str
    type: str
    module: str
    label: str
    help: str = ""
    choices: Optional[list[str]] = None
    min: Optional[float] = None
    max: Optional[float] = None
    critical: bool = False
    deploy_only: bool = False
    scopes: list[str] = []
    default: Any = None
    value: Any = None
    effective_source: str = "default"
    stored_version: int = 0
    config_version: int = 1
    data_impact: str = "none"
    is_secret: bool = False
    env_var: Optional[str] = None
    json_schema: Optional[dict[str, Any]] = None


class ChangeRead(ORMModel):
    id: Optional[str] = None
    key: str
    old_value: Any = None
    new_value: Any = None
    change_type: str = "set"
    reason: str = ""
    actor: str = "system"
    approval_state: str = "none"
    created_at: Optional[datetime] = None


# ------------------------------------------------------------------- secrets
class SecretWrite(ORMModel):
    value: str = Field(min_length=1, max_length=4096)
    reason: Optional[str] = None


class SecretRotate(ORMModel):
    value: str = Field(min_length=1, max_length=4096)
    window_hours: int = 72


class SecretRewrap(ORMModel):
    key_version: int = Field(ge=1)


class SecretRead(ORMModel):
    key: str
    configured: bool = True
    mask: str = "••••"
    status: str = "active"
    rotated_at: Optional[datetime] = None
    rotation_ends_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    key_version: int = 1
    algo: str = "AES-256-GCM"


# ----------------------------------------------------------------- sequences
class SequenceBase(ORMModel):
    key: str = Field(min_length=1, max_length=80)
    doc_type: str = "internal"
    owner_module: str = "general"
    pattern: Optional[str] = None
    prefix: str = "DOC"
    suffix: str = ""
    padding: int = 5
    start_number: int = 1
    increment: int = 1
    implementation: str = "standard"
    reset_policy: str = "fiscal_year"
    branch_id: Optional[UUID] = None
    gstin: Optional[str] = None
    max_length: Optional[int] = None
    allowed_chars_regex: Optional[str] = None
    irp_safe: bool = False
    manual_allowed: bool = False
    advance_on_manual: bool = True


class SequenceCreate(SequenceBase):
    next_number: int = 1


class SequenceUpdate(ORMModel):
    doc_type: Optional[str] = None
    owner_module: Optional[str] = None
    pattern: Optional[str] = None
    prefix: Optional[str] = None
    suffix: Optional[str] = None
    padding: Optional[int] = None
    start_number: Optional[int] = None
    increment: Optional[int] = None
    implementation: Optional[str] = None
    reset_policy: Optional[str] = None
    gstin: Optional[str] = None
    max_length: Optional[int] = None
    allowed_chars_regex: Optional[str] = None
    irp_safe: Optional[bool] = None
    manual_allowed: Optional[bool] = None
    advance_on_manual: Optional[bool] = None
    status: Optional[str] = None
    is_active: Optional[bool] = None


class SequenceRead(ORMModel):
    id: UUID
    key: str
    doc_type: str = "internal"
    owner_module: str = "general"
    pattern: Optional[str] = None
    prefix: str
    suffix: str = ""
    next_number: int = 1
    padding: int
    start_number: int = 1
    increment: int = 1
    implementation: str = "standard"
    reset_policy: str = "fiscal_year"
    branch_id: Optional[UUID] = None
    gstin: Optional[str] = None
    max_length: Optional[int] = None
    irp_safe: bool = False
    manual_allowed: bool = False
    status: str = "active"
    is_active: bool
    created_at: datetime


class SequenceNext(ORMModel):
    key: str
    number: str


class SequencePreviewRequest(ORMModel):
    on_date: Optional[date] = None
    branch_id: Optional[UUID] = None
    branch_code: str = ""
    state_code: str = ""


class SequencePreview(ORMModel):
    key: str
    fiscal_year: str
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    next_number: int
    rendered: str
    consumed: bool = False
    implementation: str = "standard"
    period_open: bool = True


class SequenceStatus(ORMModel):
    key: str
    doc_type: str
    owner_module: str
    pattern: Optional[str] = None
    implementation: str
    reset_policy: str
    status: str
    branch_id: Optional[UUID] = None
    fiscal_year: Optional[str] = None
    next_number: int = 1
    allocated_count: int = 0
    period_status: str = "not_open"
    period_start: Optional[date] = None
    period_end: Optional[date] = None
    last_allocated_at: Optional[datetime] = None
    open_blocks: int = 0
    manual_allocations: int = 0
    voided_allocations: int = 0
    preview: Optional[str] = None


class AllocateRequest(ORMModel):
    on_date: Optional[date] = None
    branch_id: Optional[UUID] = None
    idempotency_key: Optional[str] = None
    document_type: Optional[str] = None
    document_id: Optional[UUID] = None


class AllocationRead(ORMModel):
    number: int
    rendered: str
    fiscal_year: str
    allocation_id: UUID
    sequence_id: UUID
    period_id: UUID
    replayed: bool = False
    status: str = "allocated"


class VoidRequest(ORMModel):
    rendered: str
    reason_code: str
    reason_text: str = ""


class BlockCreate(ORMModel):
    size: int = Field(default=100, ge=1, le=500)
    device_id: str = Field(min_length=1, max_length=80)
    session_id: Optional[UUID] = None
    expires_in_days: int = Field(default=7, ge=1, le=90)


class BlockReturn(ORMModel):
    used_up_to: Optional[int] = None


class BlockRead(ORMModel):
    id: UUID
    sequence_id: UUID
    fiscal_year: str
    range_start: int
    range_end: int
    size: int
    device_id: str
    status: str
    used_count: int = 0
    expired: bool = False
    expires_at: Optional[datetime] = None
    issued_at: Optional[datetime] = None


class GapReport(ORMModel):
    unexplained: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    unreturned_blocks: list[dict[str, Any]] = []
    totals: dict[str, Any] = {}


class UsageReport(ORMModel):
    items: list[dict[str, Any]] = []
    total: int = 0


class SettingsDriftReport(ORMModel):
    unknown_keys: list[dict[str, Any]] = []
    invalid_values: list[dict[str, Any]] = []
    schemas_missing: list[dict[str, Any]] = []
    secrets_outside_registry: list[dict[str, Any]] = []
    scope_conflicts: list[dict[str, Any]] = []
    critical_changes_without_governance: list[dict[str, Any]] = []
    checksum_mismatches: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    total: int = 0


class SequenceValidationResult(ORMModel):
    key: Optional[str] = None
    pattern: Optional[str] = None
    sample: Optional[str] = None
    problems: list[str] = []
    valid: bool = True
