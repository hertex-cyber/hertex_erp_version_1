from fastapi import APIRouter

from app.core.crud import build_crud_router
from app.modules.marketing.models import Campaign, CampaignSend, Segment
from app.modules.marketing.schemas import (
    CampaignCreate,
    CampaignRead,
    CampaignSendCreate,
    CampaignSendRead,
    CampaignSendUpdate,
    CampaignUpdate,
    SegmentCreate,
    SegmentRead,
    SegmentUpdate,
)

router = APIRouter(prefix="/marketing")


def _include(**kwargs):
    child, _ = build_crud_router(module="marketing", **kwargs)
    router.include_router(child)


_include(
    model=Campaign,
    read_schema=CampaignRead,
    create_schema=CampaignCreate,
    update_schema=CampaignUpdate,
    prefix="/campaigns",
    tags=["Marketing · Campaigns"],
    permission_prefix="marketing.campaign",
    entity="Campaign",
    search_fields=("name", "goal", "description"),
    filter_fields=("channel", "status"),
)

_include(
    model=Segment,
    read_schema=SegmentRead,
    create_schema=SegmentCreate,
    update_schema=SegmentUpdate,
    prefix="/segments",
    tags=["Marketing · Segments"],
    permission_prefix="marketing.segment",
    entity="Segment",
    search_fields=("name", "description"),
)

_include(
    model=CampaignSend,
    read_schema=CampaignSendRead,
    create_schema=CampaignSendCreate,
    update_schema=CampaignSendUpdate,
    prefix="/sends",
    tags=["Marketing · Sends"],
    permission_prefix="marketing.campaignsend",
    entity="CampaignSend",
    search_fields=(),
    filter_fields=("campaign_id", "segment_id", "status", "channel"),
    soft_delete=False,
)
