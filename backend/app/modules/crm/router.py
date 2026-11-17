from fastapi import APIRouter
from sqlalchemy.orm import selectinload

from app.core.crud import build_crud_router
from app.modules.crm.models import Activity, Company, Contact, Deal, Lead
from app.modules.crm.schemas import (
    ActivityCreate,
    ActivityRead,
    ActivityUpdate,
    CompanyCreate,
    CompanyRead,
    CompanyUpdate,
    ContactCreate,
    ContactRead,
    ContactUpdate,
    DealCreate,
    DealRead,
    DealUpdate,
    LeadCreate,
    LeadRead,
    LeadUpdate,
)

router = APIRouter(prefix="/crm")


def _include(*args, **kwargs):
    child, _ = build_crud_router(module="crm", **kwargs)
    router.include_router(child)


_include(
    model=Company,
    read_schema=CompanyRead,
    create_schema=CompanyCreate,
    update_schema=CompanyUpdate,
    prefix="/companies",
    tags=["CRM · Companies"],
    permission_prefix="crm.company",
    entity="Company",
    search_fields=("name", "email", "gstin", "city"),
    filter_fields=("industry", "state", "country"),
)

_include(
    model=Contact,
    read_schema=ContactRead,
    create_schema=ContactCreate,
    update_schema=ContactUpdate,
    prefix="/contacts",
    tags=["CRM · Contacts"],
    permission_prefix="crm.contact",
    entity="Contact",
    search_fields=("first_name", "last_name", "email", "phone"),
    filter_fields=("company_id",),
    load_options=(selectinload(Contact.company),),
)

_include(
    model=Lead,
    read_schema=LeadRead,
    create_schema=LeadCreate,
    update_schema=LeadUpdate,
    prefix="/leads",
    tags=["CRM · Leads"],
    permission_prefix="crm.lead",
    entity="Lead",
    search_fields=("name", "company_name", "email", "phone"),
    filter_fields=("source", "status", "owner_id"),
)

_include(
    model=Deal,
    read_schema=DealRead,
    create_schema=DealCreate,
    update_schema=DealUpdate,
    prefix="/deals",
    tags=["CRM · Deals"],
    permission_prefix="crm.deal",
    entity="Deal",
    search_fields=("name",),
    filter_fields=("stage", "company_id", "owner_id"),
)

_include(
    model=Activity,
    read_schema=ActivityRead,
    create_schema=ActivityCreate,
    update_schema=ActivityUpdate,
    prefix="/activities",
    tags=["CRM · Activities"],
    permission_prefix="crm.activity",
    entity="Activity",
    search_fields=("subject", "notes"),
    filter_fields=("activity_type", "related_entity", "completed"),
)
