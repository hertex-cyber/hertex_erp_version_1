from fastapi import APIRouter

from app.modules.ai.router import router as ai_router
from app.modules.analytics.router import router as analytics_router
from app.modules.crm.router import router as crm_router
from app.modules.finance.router import router as finance_router
from app.modules.hr.router import router as hr_router
from app.modules.identity.router import (
    admin_router,
    auth_router,
    roles_router,
    users_router,
)
from app.modules.integrations.router import router as integrations_router
from app.modules.inventory.router import router as inventory_router
from app.modules.marketing.router import router as marketing_router
from app.modules.pos.router import router as pos_router
from app.modules.procurement.router import router as procurement_router
from app.modules.projects.router import router as projects_router
from app.modules.sales.router import router as sales_router
from app.modules.settings.router import router as settings_router
from app.modules.support.router import router as support_router
from app.modules.warehouse.router import router as warehouse_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(roles_router)
api_router.include_router(admin_router)
api_router.include_router(crm_router)
api_router.include_router(inventory_router)
api_router.include_router(warehouse_router)
api_router.include_router(finance_router)
api_router.include_router(sales_router)
api_router.include_router(procurement_router)
api_router.include_router(hr_router)
api_router.include_router(pos_router)
api_router.include_router(projects_router)
api_router.include_router(support_router)
api_router.include_router(marketing_router)
api_router.include_router(settings_router)
api_router.include_router(integrations_router)
api_router.include_router(analytics_router)
api_router.include_router(ai_router)
