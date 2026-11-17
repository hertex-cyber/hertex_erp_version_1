from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class SettingBase(ORMModel):
    key: str = Field(min_length=1, max_length=120)
    value: dict[str, Any] = {}
    category: str = "general"
    description: str = ""


class SettingCreate(SettingBase):
    pass


class SettingUpdate(ORMModel):
    value: Optional[dict[str, Any]] = None
    category: Optional[str] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


class SettingRead(ORMModel):
    id: UUID
    key: str
    value: dict[str, Any]
    category: str
    description: str
    is_active: bool
    created_at: datetime


class SequenceBase(ORMModel):
    key: str = Field(min_length=1, max_length=80)
    prefix: str = "DOC"
    next_number: int = 1
    padding: int = 5


class SequenceCreate(SequenceBase):
    pass


class SequenceUpdate(ORMModel):
    prefix: Optional[str] = None
    next_number: Optional[int] = None
    padding: Optional[int] = None
    is_active: Optional[bool] = None


class SequenceRead(ORMModel):
    id: UUID
    key: str
    prefix: str
    next_number: int
    padding: int
    is_active: bool
    created_at: datetime


class SequenceNext(ORMModel):
    key: str
    number: str
