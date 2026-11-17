from fastapi import APIRouter
from sqlalchemy.orm import selectinload

from app.core.crud import build_crud_router
from app.modules.warehouse.models import Bin, Warehouse
from app.modules.warehouse.schemas import (
    BinCreate,
    BinRead,
    BinUpdate,
    WarehouseCreate,
    WarehouseRead,
    WarehouseUpdate,
)

router = APIRouter(prefix="/warehouse")


def _include(**kwargs):
    child, _ = build_crud_router(module="warehouse", **kwargs)
    router.include_router(child)


_include(
    model=Warehouse,
    read_schema=WarehouseRead,
    create_schema=WarehouseCreate,
    update_schema=WarehouseUpdate,
    prefix="/warehouses",
    tags=["Warehouse · Facilities"],
    permission_prefix="warehouse.warehouse",
    entity="Warehouse",
    search_fields=("name", "code", "city"),
    filter_fields=("state", "city"),
)

_include(
    model=Bin,
    read_schema=BinRead,
    create_schema=BinCreate,
    update_schema=BinUpdate,
    prefix="/bins",
    tags=["Warehouse · Bins"],
    permission_prefix="warehouse.bin",
    entity="Bin",
    search_fields=("code", "name"),
    filter_fields=("warehouse_id",),
    load_options=(selectinload(Bin.warehouse),),
)
