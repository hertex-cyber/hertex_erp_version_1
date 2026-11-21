from app.core.exceptions import ValidationError

MENU_MODULES = [
    {"key": "dashboard", "label": "Dashboard"},
    {"key": "assistant", "label": "AI assistant"},
    {"key": "crm", "label": "Relationships"},
    {"key": "sales", "label": "Sales"},
    {"key": "pos", "label": "Point of sale"},
    {"key": "inventory", "label": "Inventory"},
    {"key": "warehouse", "label": "Warehouse"},
    {"key": "procurement", "label": "Procurement"},
    {"key": "finance", "label": "Finance"},
    {"key": "hr", "label": "HR & payroll"},
    {"key": "projects", "label": "Projects"},
    {"key": "support", "label": "Support desk"},
    {"key": "marketing", "label": "Marketing"},
    {"key": "settings", "label": "Settings"},
]

MENU_KEYS = tuple(item["key"] for item in MENU_MODULES)

ROLE_MENU_TEMPLATES: dict[str, list[str]] = {
    "superadmin": ["*"],
    "tenant_admin": ["*"],
    "manager": ["dashboard", "assistant", "projects", "hr", "settings"],
    "sales": ["dashboard", "assistant", "crm", "sales"],
    "finance": ["dashboard", "assistant", "finance", "procurement", "projects", "settings"],
    "hr": ["dashboard", "assistant", "hr", "projects"],
    "projects": ["dashboard", "assistant", "projects", "hr", "finance"],
    "team_member": ["dashboard", "assistant", "projects"],
    "guest": ["dashboard", "projects"],
    "warehouse": ["dashboard", "assistant", "inventory", "warehouse", "procurement", "sales"],
    "viewer": list(MENU_KEYS),
}

PERMISSION_MODULE_TO_MENU = {
    "analytics": "dashboard",
    "ai": "assistant",
    "crm": "crm",
    "inventory": "inventory",
    "warehouse": "warehouse",
    "sales": "sales",
    "procurement": "procurement",
    "finance": "finance",
    "hr": "hr",
    "pos": "pos",
    "projects": "projects",
    "support": "support",
    "marketing": "marketing",
    "settings": "settings",
    "system": "settings",
}


def normalize_menu_keys(values: list[str] | None) -> list[str]:
    if not values:
        return []
    if "*" in values:
        return ["*"]
    unknown = [value for value in values if value not in MENU_KEYS]
    if unknown:
        raise ValidationError(f"Unknown menu keys: {', '.join(sorted(unknown))}")
    return sorted(set(values))


def menus_from_permissions(codes: set[str] | list[str]) -> list[str]:
    menus = set()
    for code in codes:
        module = code.split(".", 1)[0]
        menu = PERMISSION_MODULE_TO_MENU.get(module)
        if menu:
            menus.add(menu)
    return sorted(menus)


def effective_menus(user) -> list[str]:
    if user.is_superuser:
        return ["*"]
    explicit: list[str] = []
    for role in user.roles:
        if not role.is_active:
            continue
        menu_keys = getattr(role, "menu_keys", None)
        if menu_keys:
            explicit.extend(menu_keys)
    if explicit:
        return normalize_menu_keys(explicit)
    return menus_from_permissions(user.permission_codes())
