"""Single source of truth for RBAC permission codes.

Every module registers its resources here. The seeder materialises these into the
``permissions`` table and role templates are derived from the same catalog so the
frontend navigation and backend guards never drift apart.
"""

RESOURCE_ACTIONS = ("read", "create", "update", "delete")

MODULE_RESOURCES: dict[str, list[str]] = {
    "crm": ["company", "contact", "lead", "deal", "activity"],
    "inventory": ["category", "product", "stockmove"],
    "warehouse": ["warehouse", "bin"],
    "sales": ["customer", "salesorder", "deliverychallan"],
    "procurement": ["vendor", "requisition", "purchaseorder", "goodsreceipt", "vendorinvoice"],
    "finance": ["account", "journalentry", "invoice", "payment", "bankaccount", "banktransaction"],
    "hr": ["department", "employee", "attendance", "leaverequest", "payrollrun", "payslip"],
    "pos": ["session", "sale"],
    "projects": ["project", "task"],
    "support": ["ticket", "ticketmessage"],
    "marketing": ["campaign", "segment", "campaignsend"],
    "settings": ["setting", "sequence"],
}

EXTRA_PERMISSIONS: dict[str, tuple[str, str, str]] = {
    "finance.journal.post": ("finance", "post", "Post journal entries to the ledger"),
    "finance.report.read": ("finance", "report", "View financial statements"),
    "procurement.po.approve": ("procurement", "approve", "Approve purchase orders"),
    "procurement.grn.create": ("procurement", "receive", "Receive goods against a PO"),
    "sales.order.fulfill": ("sales", "fulfill", "Fulfil sales orders"),
    "pos.sale.checkout": ("pos", "checkout", "Complete POS checkouts"),
    "analytics.dashboard.read": ("analytics", "read", "View dashboards and KPIs"),
    "ai.assistant.use": ("ai", "use", "Use the AI assistant"),
    "system.user.manage": ("system", "user", "Manage users"),
    "system.role.manage": ("system", "role", "Manage roles and permissions"),
    "system.audit.read": ("system", "audit", "View audit logs"),
    "system.tenant.manage": ("system", "tenant", "Manage tenants"),
    "system.settings.manage": ("system", "settings", "Manage system settings"),
    "integrations.channel.manage": ("integrations", "manage", "Manage WhatsApp/Meta channels"),
}


def all_permission_specs() -> list[tuple[str, str, str, str]]:
    specs: list[tuple[str, str, str, str]] = []
    for module, resources in MODULE_RESOURCES.items():
        for resource in resources:
            for action in RESOURCE_ACTIONS:
                specs.append(
                    (
                        f"{module}.{resource}.{action}",
                        module,
                        action,
                        f"{action.title()} {resource.replace('_', ' ')} in {module}",
                    )
                )
    for code, (module, action, description) in EXTRA_PERMISSIONS.items():
        specs.append((code, module, action, description))
    return specs


def all_read_permissions() -> set[str]:
    return {code for code, _, action, _ in all_permission_specs() if action == "read"}


def role_templates() -> dict[str, dict]:
    """Default role templates derived from the permission catalog."""
    every = {code for code, _, _, _ in all_permission_specs()}
    reads = all_read_permissions()
    crm = {code for code in every if code.startswith(("crm.", "sales."))}
    inventory = {code for code in every if code.startswith(("inventory.", "warehouse."))}
    finance = {code for code in every if code.startswith(("finance.", "procurement."))}
    hr = {code for code in every if code.startswith("hr.")}
    system = {code for code in every if code.startswith(("system.", "integrations."))}
    common = {
        "analytics.dashboard.read",
        "ai.assistant.use",
    }
    return {
        "superadmin": {"name": "Superadmin", "codes": every | system, "system": True},
        "tenant_admin": {"name": "Administrator", "codes": every | system, "system": True},
        "manager": {
            "name": "Manager",
            "codes": (every - system) | common,
            "system": True,
        },
        "sales": {
            "name": "Sales",
            "codes": crm | reads | common | {"sales.order.fulfill"},
            "system": True,
        },
        "finance": {
            "name": "Finance",
            "codes": finance | reads | common | {"finance.journal.post", "finance.report.read"},
            "system": True,
        },
        "hr": {"name": "HR & Payroll", "codes": hr | reads | common, "system": True},
        "warehouse": {
            "name": "Warehouse",
            "codes": inventory | reads | common | {"sales.order.fulfill"},
            "system": True,
        },
        "viewer": {"name": "Viewer", "codes": reads | common, "system": True},
    }
