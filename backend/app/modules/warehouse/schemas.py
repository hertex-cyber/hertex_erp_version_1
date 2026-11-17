from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import Field

from app.core.schemas import ORMModel


class WarehouseBase(ORMModel):
    name: str = Field(min_length=1, max_length=150)
    code: str = Field(min_length=1, max_length=50)
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None


class WarehouseCreate(WarehouseBase):
    pass


class WarehouseUpdate(ORMModel):
    name: Optional[str] = None
    code: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: Optional[bool] = None


class WarehouseRead(ORMModel):
    id: UUID
    name: str
    code: str
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    is_active: bool
    created_at: datetime


class BinBase(ORMModel):
    warehouse_id: UUID
    code: str = Field(min_length=1, max_length=50)
    name: Optional[str] = None


class BinCreate(BinBase):
    pass


class BinUpdate(ORMModel):
    code: Optional[str] = None
    name: Optional[str] = None
    is_active: Optional[bool] = None


class BinRead(ORMModel):
    id: UUID
    warehouse_id: UUID
    code: str
    name: Optional[str] = None
    is_active: bool
    created_at: datetime
    warehouse: Optional[WarehouseRead] = None
