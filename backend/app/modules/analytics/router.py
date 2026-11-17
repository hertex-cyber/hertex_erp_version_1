from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import require_permissions
from app.db.session import get_db
from app.modules.analytics.schemas import DashboardResponse
from app.modules.analytics.service import dashboard_payload
from app.modules.identity.models import User

router = APIRouter(prefix="/analytics", tags=["Analytics & BI"])

read_dashboard = require_permissions("analytics.dashboard.read")


@router.get("/dashboard", response_model=DashboardResponse)
async def dashboard(
    user: User = Depends(read_dashboard), db: AsyncSession = Depends(get_db)
):
    return await dashboard_payload(db, user)
