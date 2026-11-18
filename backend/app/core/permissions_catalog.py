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
    "finance": [
        "account",
        "fiscalperiod",
        "journalentry",
        "invoice",
        "payment",
        "bankaccount",
        "banktransaction",
        "taxregistration",
        "taxcode",
    ],
    "hr": ["department", "employee", "attendance", "leaverequest", "payrollrun", "payslip"],
    "pos": ["session", "sale"],
    "projects": [
        "project",
        "task",
        "portfolio",
        "program",
        "phase",
        "sprint",
        "board",
        "boardcolumn",
        "label",
        "workitem",
        "workitemlink",
        "customfield",
        "fieldvalue",
        "workflow",
        "transition",
        "approval",
        "template",
        "milestone",
        "dependency",
        "baseline",
        "baselinesnapshot",
        "release",
        "changerequest",
        "timeentry",
        "timesheet",
        "timesheetentry",
        "expense",
        "costentry",
        "billingrun",
        "billingline",
        "invoicelink",
        "budget",
        "budgetrevision",
        "resourcerole",
        "employeeskill",
        "capacitycalendar",
        "booking",
        "workload",
        "risk",
        "issue",
        "decision",
        "statusupdate",
        "goal",
        "retrospective",
        "comment",
        "activity",
        "attachment",
        "automation",
        "automationrun",
        "integration",
        "importbatch",
        "aisignal",
        "aiaction",
        "outbox",
    ],
    "support": ["ticket", "ticketmessage"],
    "marketing": ["campaign", "segment", "campaignsend"],
    "settings": ["setting", "sequence"],
}

EXTRA_PERMISSIONS: dict[str, tuple[str, str, str]] = {
    "finance.journal.post": ("finance", "post", "Post journal entries to the ledger"),
    "finance.journal.reverse": ("finance", "reverse", "Reverse posted journal entries"),
    "finance.period.close": ("finance", "close", "Close a financial period"),
    "finance.period.reopen": ("finance", "reopen", "Reopen a financial period"),
    "finance.report.read": ("finance", "report", "View financial statements"),
    "finance.approval.read": ("finance", "read", "View accounting approvals"),
    "finance.approval.approve": ("finance", "approve", "Approve accounting transactions"),
    "finance.approval.reject": ("finance", "reject", "Reject accounting transactions"),
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
    "projects.finance.read": ("projects", "read", "Read project finance data"),
    "projects.billing.review": ("projects", "review", "Review project billing runs"),
    "projects.billing.approve": ("projects", "approve", "Approve project billing runs"),
    "projects.billing.post": ("projects", "post", "Post project billing runs to finance"),
    "projects.resource.read": ("projects", "read", "Read project resource capacity"),
    "projects.resource.update": ("projects", "update", "Manage project resource capacity"),
    "projects.schedule.read": ("projects", "read", "Read project schedules"),
    "projects.schedule.create": ("projects", "create", "Create project schedule links"),
    "projects.schedule.update": ("projects", "update", "Update project schedules"),
    "projects.schedule.delete": ("projects", "delete", "Delete project schedule links"),
    "projects.report.read": ("projects", "read", "Read project reports"),
    "projects.ai.review": ("projects", "review", "Review AI project recommendations"),
    "projects.ai.execute": ("projects", "execute", "Execute approved AI project actions"),
    "projects.ai.reverse": ("projects", "reverse", "Reverse executed AI project actions"),
    "projects.automation.run": ("projects", "run", "Run project automation rules"),
    "projects.outbox.dispatch": ("projects", "dispatch", "Dispatch project outbox events"),
    "projects.timeentry.approve": ("projects", "approve", "Approve project time entries"),
    "projects.timesheet.approve": ("projects", "approve", "Approve project timesheets"),
    "projects.billing.read": ("projects", "read", "Read project billing runs and unbilled items"),
    "projects.billing.create": ("projects", "create", "Create project billing runs"),
    "projects.billing.update": ("projects", "update", "Review and update project billing runs"),
    "projects.ai.read": ("projects", "read", "Read project AI signals and actions"),
    "projects.ai.create": ("projects", "create", "Propose project AI signals and actions"),
    "projects.ai.update": ("projects", "update", "Refresh project AI signals"),
    "projects.settings.manage": ("projects", "manage", "Manage project workflow and custom-field settings"),
    "projects.import.manage": ("projects", "manage", "Run and correct project imports"),
    "projects.comment.create": ("projects", "create", "Create project comments"),
    "projects.comment.read": ("projects", "read", "Read project comments"),
    "projects.comment.update": ("projects", "update", "Update own project comments"),
    "projects.comment.delete": ("projects", "delete", "Delete own project comments"),
    "projects.governance.read": ("projects", "read", "Read project governance records"),
    "projects.change.read": ("projects", "read", "Read project change requests"),
    "projects.status.read": ("projects", "read", "Read project status updates"),
    "projects.import.read": ("projects", "read", "Read project import batches"),
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


def _prefixed(every: set[str], *prefixes: str) -> set[str]:
    return {code for code in every if code.startswith(prefixes)}


def role_templates() -> dict[str, dict]:
    """Least-privilege role templates derived from the permission catalog."""
    every = {code for code, _, _, _ in all_permission_specs()}
    reads = all_read_permissions()
    crm = _prefixed(every, "crm.", "sales.")
    inventory = _prefixed(every, "inventory.", "warehouse.")
    finance = _prefixed(every, "finance.", "procurement.")
    hr = _prefixed(every, "hr.")
    projects = _prefixed(every, "projects.")
    common = {
        "analytics.dashboard.read",
        "ai.assistant.use",
    }
    safe_reads = reads - {
        "projects.finance.read",
        "hr.payrollrun.read",
        "hr.payslip.read",
        "system.audit.read",
    }
    hr_reads = {
        "hr.employee.read",
        "hr.leaverequest.read",
        "hr.attendance.read",
        "hr.department.read",
    }
    pmo = (projects - {"projects.billing.post"}) | common | hr_reads | {
        "finance.report.read",
    }
    manager = {
        "projects.project.read", "projects.project.create", "projects.project.update",
        "projects.task.read", "projects.task.create", "projects.task.update",
        "projects.workitem.read", "projects.workitem.create", "projects.workitem.update",
        "projects.portfolio.read", "projects.program.read", "projects.phase.read",
        "projects.phase.create", "projects.phase.update",
        "projects.sprint.read", "projects.sprint.create", "projects.sprint.update",
        "projects.board.read", "projects.boardcolumn.read",
        "projects.label.read", "projects.label.create", "projects.label.update",
        "projects.milestone.read", "projects.milestone.update",
        "projects.dependency.read", "projects.dependency.create", "projects.dependency.update",
        "projects.schedule.read", "projects.schedule.create", "projects.schedule.update",
        "projects.timeentry.read", "projects.timeentry.create", "projects.timeentry.update",
        "projects.timeentry.approve", "projects.timesheet.read", "projects.timesheet.approve",
        "projects.billing.read", "projects.billing.review",
        "projects.resource.read", "projects.resource.update",
        "projects.booking.read", "projects.booking.create", "projects.booking.update",
        "projects.risk.read", "projects.risk.create", "projects.risk.update",
        "projects.issue.read", "projects.issue.create", "projects.issue.update",
        "projects.changerequest.read", "projects.changerequest.create", "projects.changerequest.update",
        "projects.statusupdate.read", "projects.statusupdate.create", "projects.statusupdate.update",
        "projects.goal.read", "projects.goal.create", "projects.goal.update",
        "projects.comment.read", "projects.comment.create", "projects.comment.update",
        "projects.attachment.read", "projects.attachment.create",
        "projects.approval.read", "projects.approval.create",
        "projects.ai.read", "projects.report.read",
    } | common | hr_reads
    finance_role = finance | common | {
        "projects.finance.read",
        "projects.billing.read", "projects.billing.create", "projects.billing.update",
        "projects.billing.review", "projects.billing.approve", "projects.billing.post",
        "projects.billingrun.read", "projects.billingline.read", "projects.invoicelink.read",
        "projects.project.read", "projects.budget.read", "projects.budgetrevision.read",
        "projects.timeentry.read", "projects.expense.read", "projects.report.read",
        "finance.report.read",
    }
    hr_role = hr | common | {
        "projects.resource.read",
        "projects.capacitycalendar.read",
        "projects.workload.read",
    }
    team_member = {
        "projects.project.read",
        "projects.task.read",
        "projects.workitem.read", "projects.workitem.create", "projects.workitem.update",
        "projects.sprint.read", "projects.milestone.read", "projects.board.read",
        "projects.timeentry.read", "projects.timeentry.create", "projects.timeentry.update",
        "projects.timesheet.read", "projects.timesheet.create", "projects.timesheet.update",
        "projects.comment.read", "projects.comment.create", "projects.comment.update",
        "projects.statusupdate.read", "projects.attachment.read", "projects.attachment.create",
        "projects.approval.read", "projects.ai.read",
    } | common
    guest = {
        "projects.project.read",
        "projects.milestone.read",
        "projects.statusupdate.read",
        "projects.comment.read", "projects.comment.create", "projects.comment.update",
    }
    return {
        "superadmin": {"name": "Superadmin", "codes": every, "system": True},
        "tenant_admin": {"name": "Administrator", "codes": every, "system": True},
        "manager": {"name": "Manager", "codes": manager, "system": True},
        "sales": {
            "name": "Sales",
            "codes": crm | common | {"sales.order.fulfill"},
            "system": True,
        },
        "finance": {"name": "Finance", "codes": finance_role, "system": True},
        "hr": {"name": "HR & Payroll", "codes": hr_role, "system": True},
        "projects": {"name": "Project Management (PMO)", "codes": pmo, "system": True},
        "team_member": {"name": "Team Member", "codes": team_member, "system": True},
        "guest": {"name": "Guest", "codes": guest, "system": True},
        "warehouse": {
            "name": "Warehouse",
            "codes": inventory | common | {"sales.order.fulfill"},
            "system": True,
        },
        "viewer": {"name": "Viewer", "codes": safe_reads | common, "system": True},
    }
