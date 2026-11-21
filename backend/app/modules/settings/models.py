"""Settings & numbering ORM models (module 15 / 15A).

Three-layer design for numbering:

* ``NumberSequence``        — the *series definition* (pattern, policy, doc type)
* ``NumberSequencePeriod``  — the *counter*, one row per series x fiscal period
* ``NumberAllocation``      — the *ledger*, one row per number ever handed out

The ledger is what makes gaps explainable (GST Rule 46 + GSTR-1 reconciliation):
a number is either attached to a document, voided with a reason, part of an
offline block, or not yet allocated at all.
"""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel, TenantBaseModel

# --- enumerated-ish string vocabularies (portable across PG + SQLite) ---------
SCOPE_TYPES = ("tenant", "branch", "user")
VALUE_TYPES = (
    "string",
    "int",
    "decimal",
    "bool",
    "enum",
    "json",
    "date",
    "currency",
    "duration",
    "secret",
)
SETTING_SOURCES = ("admin", "seed", "migration", "api", "default")
CHANGE_TYPES = ("set", "unset", "rotate", "approve", "reject", "migrate")
APPROVAL_STATES = ("none", "pending", "approved", "rejected")
IMPLEMENTATIONS = ("standard", "nogap")
RESET_POLICIES = ("never", "fiscal_year", "calendar_year", "monthly")
SEQUENCE_STATUSES = ("draft", "active", "locked")
ALLOCATION_STATUSES = ("allocated", "committed", "void", "manual", "block")
GAP_REASONS = (
    "abandoned",
    "cancelled",
    "void",
    "manual_skip",
    "block_unused",
    "block_expired",
)
BLOCK_STATUSES = ("issued", "partially_used", "exhausted", "returned", "expired")
SECRET_STATUSES = ("active", "pending", "retired")


class AppSetting(TenantBaseModel):
    """One configuration value at one scope.

    Values are typed against :mod:`app.modules.settings.registry`; unregistered
    keys are rejected at the API boundary. Secret settings are pointers into
    ``setting_secrets`` — the plaintext never lands in this table.
    """

    __tablename__ = "app_settings"
    __table_args__ = (
        Index(
            "uq_app_settings_scope_tenant",
            "tenant_id",
            "scope_type",
            "key",
            unique=True,
            postgresql_where=text("scope_id IS NULL"),
            sqlite_where=text("scope_id IS NULL"),
        ),
        Index(
            "uq_app_settings_scope_scoped",
            "tenant_id",
            "scope_type",
            "scope_id",
            "key",
            unique=True,
            postgresql_where=text("scope_id IS NOT NULL"),
            sqlite_where=text("scope_id IS NOT NULL"),
        ),
        Index("ix_app_settings_tenant_key", "tenant_id", "key"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value: Mapped[Any] = mapped_column(JSON, default=dict, nullable=True)
    category: Mapped[str] = mapped_column(String(80), default="general", index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    scope_type: Mapped[str] = mapped_column(String(16), default="tenant", nullable=False)
    scope_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    value_type: Mapped[str] = mapped_column(String(16), default="json", nullable=False)
    is_secret: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    source: Mapped[str] = mapped_column(String(16), default="admin", nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    updated_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SettingChange(BaseModel):
    """Change history with before/after and a mandatory reason for critical keys."""

    __tablename__ = "setting_changes"
    __table_args__ = (
        Index("ix_setting_changes_tenant_key", "tenant_id", "key"),
        Index("ix_setting_changes_tenant_state", "tenant_id", "approval_state"),
    )

    tenant_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(16), default="tenant", nullable=False)
    scope_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    old_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    new_value: Mapped[Any] = mapped_column(JSON, nullable=True)
    change_type: Mapped[str] = mapped_column(String(16), default="set", nullable=False)
    reason: Mapped[str] = mapped_column(Text, default="", nullable=False)
    actor_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email: Mapped[str] = mapped_column(String(255), default="system", nullable=False)
    approved_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    approval_state: Mapped[str] = mapped_column(String(16), default="none", nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    request_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    correlation_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)


class SettingSecret(TenantBaseModel):
    """Encrypted secret setting (AES-256-GCM) with a rotation window."""

    __tablename__ = "setting_secrets"
    __table_args__ = (
        UniqueConstraint("tenant_id", "key", name="uq_setting_secrets_tenant_key"),
    )

    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    key_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    algo: Mapped[str] = mapped_column(String(32), default="AES-256-GCM", nullable=False)
    previous_ciphertext: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    previous_nonce: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)
    previous_key_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    previous_expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    mask: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    rotated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    rotated_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    last_used_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NumberSequence(TenantBaseModel):
    """Series definition for one document channel (optionally per branch/GSTIN)."""

    __tablename__ = "number_sequences"
    __table_args__ = (
        Index(
            "uq_number_sequences_tenant_key_default",
            "tenant_id",
            "key",
            unique=True,
            postgresql_where=text("branch_id IS NULL"),
            sqlite_where=text("branch_id IS NULL"),
        ),
        Index(
            "uq_number_sequences_tenant_key_branch",
            "tenant_id",
            "key",
            "branch_id",
            unique=True,
            postgresql_where=text("branch_id IS NOT NULL"),
            sqlite_where=text("branch_id IS NOT NULL"),
        ),
        Index("ix_number_sequences_tenant_module", "tenant_id", "owner_module"),
    )

    key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    doc_type: Mapped[str] = mapped_column(String(40), default="internal", nullable=False)
    owner_module: Mapped[str] = mapped_column(String(40), default="general", nullable=False)
    pattern: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prefix: Mapped[str] = mapped_column(String(30), default="DOC")
    suffix: Mapped[str] = mapped_column(String(30), default="")
    next_number: Mapped[int] = mapped_column(Integer, default=1)  # deprecated mirror
    padding: Mapped[int] = mapped_column(Integer, default=5)
    start_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    increment: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    implementation: Mapped[str] = mapped_column(String(16), default="standard", nullable=False)
    reset_policy: Mapped[str] = mapped_column(String(16), default="fiscal_year", nullable=False)
    # Deliberately un-FK'd: branch master data does not exist yet, and a series
    # must be creatable per branch/GSTIN the moment a Branch model appears.
    branch_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), nullable=True, index=True
    )
    gstin: Mapped[Optional[str]] = mapped_column(String(15), nullable=True)
    max_length: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    allowed_chars_regex: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    irp_safe: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    manual_allowed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    advance_on_manual: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="active", nullable=False)
    last_allocated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NumberSequencePeriod(TenantBaseModel):
    """The counter. The only row that is ever incremented."""

    __tablename__ = "number_sequence_periods"
    __table_args__ = (
        UniqueConstraint("sequence_id", "fiscal_year", name="uq_sequence_periods_seq_fy"),
        Index("ix_sequence_periods_tenant_fy", "tenant_id", "fiscal_year"),
    )

    sequence_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("number_sequences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fiscal_year: Mapped[str] = mapped_column(String(9), default="", nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    next_number: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    allocated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False)
    last_allocated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_allocated_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class NumberAllocation(TenantBaseModel):
    """Ledger: every number handed out, with its disposition."""

    __tablename__ = "number_allocations"
    __table_args__ = (
        UniqueConstraint(
            "sequence_id", "fiscal_year", "number", name="uq_number_allocations_seq_fy_number"
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_number_allocations_idempotency"),
        Index("ix_number_allocations_tenant_status", "tenant_id", "status", "allocated_at"),
        Index("ix_number_allocations_document", "tenant_id", "document_type", "document_id"),
    )

    sequence_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("number_sequences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("number_sequence_periods.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    fiscal_year: Mapped[str] = mapped_column(String(9), default="", nullable=False)
    number: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rendered: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="allocated", nullable=False)
    document_type: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    document_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    branch_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    reason_code: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)
    reason_text: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    allocated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    committed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    voided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    allocated_by_id: Mapped[Optional[UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class NumberSequenceBlock(TenantBaseModel):
    """Reserved range of numbers for offline devices (POS / warehouse guns)."""

    __tablename__ = "number_sequence_blocks"
    __table_args__ = (
        Index("ix_sequence_blocks_device", "tenant_id", "device_id", "status"),
    )

    sequence_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("number_sequences.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    period_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("number_sequence_periods.id", ondelete="CASCADE"),
        nullable=False,
    )
    fiscal_year: Mapped[str] = mapped_column(String(9), default="", nullable=False)
    range_start: Mapped[int] = mapped_column(BigInteger, nullable=False)
    range_end: Mapped[int] = mapped_column(BigInteger, nullable=False)
    size: Mapped[int] = mapped_column(Integer, nullable=False)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    session_id: Mapped[Optional[UUID]] = mapped_column(UUID(as_uuid=True), nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="issued", nullable=False)
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    returned_from: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
