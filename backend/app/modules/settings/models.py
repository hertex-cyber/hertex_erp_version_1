from typing import Any

from sqlalchemy import JSON, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import TenantBaseModel


class AppSetting(TenantBaseModel):
    __tablename__ = "app_settings"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_app_settings_tenant_key"),)

    key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    category: Mapped[str] = mapped_column(String(80), default="general", index=True)
    description: Mapped[str] = mapped_column(Text, default="")


class NumberSequence(TenantBaseModel):
    __tablename__ = "number_sequences"
    __table_args__ = (UniqueConstraint("tenant_id", "key", name="uq_number_sequences_tenant_key"),)

    key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    prefix: Mapped[str] = mapped_column(String(30), default="DOC")
    next_number: Mapped[int] = mapped_column(Integer, default=1)
    padding: Mapped[int] = mapped_column(Integer, default=5)
