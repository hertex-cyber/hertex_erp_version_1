"""Import every ORM model so ``Base.metadata`` is complete.

Alembic autogenerate and ``Base.metadata.create_all`` both rely on this module
being imported. Keep it in sync whenever a new module ships.
"""

from app.db.base import Base
from app.modules.ai import service as _ai_service  # noqa: F401
from app.modules.analytics import service as _analytics_service  # noqa: F401
from app.modules.crm import models as _crm_models  # noqa: F401
from app.modules.finance import models as _finance_models  # noqa: F401
from app.modules.hr import models as _hr_models  # noqa: F401
from app.modules.identity import models as _identity_models  # noqa: F401
from app.modules.integrations import models as _integrations_models  # noqa: F401
from app.modules.inventory import models as _inventory_models  # noqa: F401
from app.modules.marketing import models as _marketing_models  # noqa: F401
from app.modules.pos import models as _pos_models  # noqa: F401
from app.modules.procurement import models as _procurement_models  # noqa: F401
from app.modules.projects import models as _projects_models  # noqa: F401
from app.modules.sales import models as _sales_models  # noqa: F401
from app.modules.settings import models as _settings_models  # noqa: F401
from app.modules.support import models as _support_models  # noqa: F401
from app.modules.warehouse import models as _warehouse_models  # noqa: F401

__all__ = ["Base"]
