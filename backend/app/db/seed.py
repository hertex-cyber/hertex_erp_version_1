"""Idempotent RBAC + bootstrap seed.

Run with ``python -m app.db.seed`` after the schema exists. Safe to re-run: it
upserts permissions, refreshes system role templates, and only creates the admin
and demo tenant when missing.
"""

import asyncio
import re
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.core.config import settings
from app.core.permissions_catalog import all_permission_specs, role_templates
from app.core.security import hash_password
from app.db.registry import Base  # noqa: F401  (ensures metadata is complete)
from app.db.session import AsyncSessionLocal, engine
from app.modules.crm.models import Company, Contact, Deal, Lead
from app.modules.finance.models import Account, Invoice, Payment
from app.modules.hr.models import Department, Employee
from app.modules.identity.models import Permission, Role, Tenant, User
from app.modules.inventory.models import Category, Product, StockMove
from app.modules.marketing.models import Campaign, Segment
from app.modules.procurement.models import Vendor, VendorInvoice
from app.modules.projects.models import Project, Task
from app.modules.sales.models import Customer, SalesOrder, SalesOrderLine
from app.modules.settings.models import AppSetting, NumberSequence
from app.modules.support.models import Ticket
from app.modules.warehouse.models import Bin, Warehouse

SEQUENCES = [
    ("sales_order", "SO", 5),
    ("invoice", "INV", 5),
    ("payment", "PAY", 5),
    ("purchase_order", "PO", 5),
    ("goods_receipt", "GRN", 5),
    ("vendor_invoice", "VB", 5),
    ("journal_entry", "JE", 5),
    ("ticket", "TKT", 5),
    ("project", "PRJ", 5),
    ("payroll_run", "PR", 5),
]


def _slugify(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "tenant"


async def seed_permissions(db) -> dict[str, Permission]:
    existing = {
        perm.code: perm for perm in (await db.scalars(select(Permission))).all()
    }
    for code, module, action, description in all_permission_specs():
        perm = existing.get(code)
        if perm is None:
            perm = Permission(code=code, module=module, action=action, description=description)
            db.add(perm)
            existing[code] = perm
        else:
            perm.module = module
            perm.action = action
            perm.description = description
    await db.flush()
    return existing


async def seed_roles(db, permissions: dict[str, Permission]) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for slug, template in role_templates().items():
        role = await db.scalar(select(Role).where(Role.slug == slug, Role.tenant_id.is_(None)))
        if role is None:
            role = Role(
                tenant_id=None,
                name=template["name"],
                slug=slug,
                description=f"Built-in {template['name']} role",
                is_system=template.get("system", True),
                permissions=[permissions[code] for code in template["codes"] if code in permissions],
            )
            db.add(role)
            await db.flush()
        else:
            role.permissions = [
                permissions[code] for code in template["codes"] if code in permissions
            ]
            role.is_system = template.get("system", True)
        roles[slug] = role
    await db.flush()
    return roles


async def seed_tenant_and_admin(db, roles: dict[str, Role]) -> tuple[Tenant, User]:
    tenant = await db.scalar(select(Tenant).where(Tenant.name == settings.SEED_DEMO_TENANT))
    if tenant is None:
        slug = _slugify(settings.SEED_DEMO_TENANT)
        if await db.scalar(select(Tenant).where(Tenant.slug == slug)):
            slug = f"{slug}-main"
        tenant = Tenant(name=settings.SEED_DEMO_TENANT, slug=slug, plan="enterprise")
        db.add(tenant)
        await db.flush()

    admin = await db.scalar(select(User).where(User.email == settings.SEED_ADMIN_EMAIL.lower()))
    if admin is None:
        admin = User(
            tenant_id=tenant.id,
            email=settings.SEED_ADMIN_EMAIL.lower(),
            hashed_password=hash_password(settings.SEED_ADMIN_PASSWORD),
            full_name="Hertex Admin",
            is_superuser=True,
            is_verified=True,
            roles=[roles["superadmin"]],
        )
        db.add(admin)
    else:
        admin.is_superuser = True
        admin.is_active = True
        admin.tenant_id = admin.tenant_id or tenant.id
        if roles["superadmin"] not in admin.roles:
            admin.roles.append(roles["superadmin"])
    await db.flush()
    return tenant, admin


async def seed_settings(db, tenant: Tenant) -> None:
    defaults = [
        (
            "company.profile",
            {
                "name": tenant.name,
                "email": settings.SEED_ADMIN_EMAIL,
                "country": "India",
                "currency": "INR",
                "timezone": "Asia/Kolkata",
            },
            "company",
        ),
        (
            "finance.defaults",
            {"currency": "INR", "tax_rate": 18, "invoice_due_days": 15},
            "finance",
        ),
        (
            "sales.defaults",
            {"default_channel": "direct", "quote_validity_days": 14},
            "sales",
        ),
        (
            "support.sla",
            {"first_response_hours": 4, "resolution_hours": 48},
            "support",
        ),
    ]
    for key, value, category in defaults:
        existing = await db.scalar(
            select(AppSetting).where(AppSetting.tenant_id == tenant.id, AppSetting.key == key)
        )
        if existing is None:
            db.add(AppSetting(tenant_id=tenant.id, key=key, value=value, category=category))

    for key, prefix, padding in SEQUENCES:
        existing = await db.scalar(
            select(NumberSequence).where(
                NumberSequence.tenant_id == tenant.id, NumberSequence.key == key
            )
        )
        if existing is None:
            db.add(
                NumberSequence(
                    tenant_id=tenant.id, key=key, prefix=prefix, next_number=1, padding=padding
                )
            )


async def seed_demo(db, tenant: Tenant, admin: User) -> None:
    """Create a small, realistic dataset so the UI has something to show."""
    if not settings.SEED_DEMO_DATA:
        return
    existing = await db.scalar(select(Product).where(Product.tenant_id == tenant.id))
    if existing is not None:
        return

    today = date.today()
    common = {"tenant_id": tenant.id, "created_by_id": admin.id}

    warehouse = Warehouse(name="Main Warehouse", code="WH-MAIN", city="Bengaluru", state="Karnataka", **common)
    db.add(warehouse)
    await db.flush()
    db.add(Bin(warehouse_id=warehouse.id, code="A-01", name="Fast moving", **common))

    apparel = Category(name="Apparel", description="Finished garments", **common)
    accessories = Category(name="Accessories", description="Add-on merchandise", **common)
    db.add_all([apparel, accessories])
    await db.flush()

    products = [
        Product(sku="TSH-001", name="Hertex Classic Tee", category_id=apparel.id, uom="pcs", sale_price=Decimal("799"), purchase_price=Decimal("320"), tax_rate=Decimal("5"), reorder_level=Decimal("40"), **common),
        Product(sku="SHIRT-002", name="Linen Weekend Shirt", category_id=apparel.id, uom="pcs", sale_price=Decimal("1899"), purchase_price=Decimal("780"), tax_rate=Decimal("5"), reorder_level=Decimal("25"), **common),
        Product(sku="HOOD-003", name="Fleece Hoodie", category_id=apparel.id, uom="pcs", sale_price=Decimal("2499"), purchase_price=Decimal("1100"), tax_rate=Decimal("5"), reorder_level=Decimal("20"), **common),
        Product(sku="CAP-004", name="Canvas Cap", category_id=accessories.id, uom="pcs", sale_price=Decimal("599"), purchase_price=Decimal("210"), tax_rate=Decimal("18"), reorder_level=Decimal("30"), **common),
    ]
    db.add_all(products)
    await db.flush()

    stock = [(products[0], 120), (products[1], 64), (products[2], 18), (products[3], 90)]
    for product, qty in stock:
        db.add(
            StockMove(
                product_id=product.id,
                warehouse_id=warehouse.id,
                movement_type="receipt",
                quantity=Decimal(qty),
                unit_cost=product.purchase_price,
                reason="Opening stock",
                reference="SEED-OPENING",
                **common,
            )
        )

    customers = [
        Customer(code="CUST-001", name="Aurora Boutique", email="orders@auroraboutique.in", phone="+91 98450 11223", billing_address="Indiranagar, Bengaluru", credit_limit=Decimal("150000"), **common),
        Customer(code="CUST-002", name="Nova Retail", email="buying@novaretail.in", phone="+91 99001 44556", billing_address="Koramangala, Bengaluru", credit_limit=Decimal("250000"), **common),
        Customer(code="CUST-003", name="The Wardrobe Co.", email="hello@wardrobe.co.in", billing_address="Jubilee Hills, Hyderabad", credit_limit=Decimal("80000"), **common),
    ]
    db.add_all(customers)
    await db.flush()

    order = SalesOrder(
        order_number="SO-00001",
        customer_id=customers[0].id,
        order_date=today - timedelta(days=3),
        status="confirmed",
        channel="whatsapp",
        warehouse_id=warehouse.id,
        subtotal=Decimal("5397"),
        tax=Decimal("270"),
        total=Decimal("5667"),
        **common,
    )
    db.add(order)
    await db.flush()
    db.add_all(
        [
            SalesOrderLine(order_id=order.id, product_id=products[0].id, quantity=Decimal("3"), unit_price=Decimal("799"), tax_rate=Decimal("5"), line_total=Decimal("2517"), **common),
            SalesOrderLine(order_id=order.id, product_id=products[1].id, quantity=Decimal("2"), unit_price=Decimal("1899"), tax_rate=Decimal("5"), line_total=Decimal("3988"), **common),
        ]
    )

    vendors = [
        Vendor(code="VEND-001", name="Loom Textiles", email="sales@loomtextiles.in", payment_terms="net_30", rating=Decimal("4.5"), address="Tiruppur, Tamil Nadu", **common),
        Vendor(code="VEND-002", name="Metro Trims", email="hello@metrotrims.in", payment_terms="net_15", rating=Decimal("4.0"), address="Surat, Gujarat", **common),
    ]
    db.add_all(vendors)
    await db.flush()
    db.add(
        VendorInvoice(
            vendor_id=vendors[0].id,
            invoice_number="LT-2026-014",
            issue_date=today - timedelta(days=12),
            due_date=today + timedelta(days=18),
            amount=Decimal("86400"),
            tax_amount=Decimal("15552"),
            status="pending",
            **common,
        )
    )

    accounts = [
        Account(code="1010", name="Cash", account_type="asset", **common),
        Account(code="1100", name="Accounts Receivable", account_type="asset", **common),
        Account(code="1200", name="Inventory", account_type="asset", **common),
        Account(code="2000", name="Accounts Payable", account_type="liability", **common),
        Account(code="2100", name="Goods Received Not Invoiced", account_type="liability", **common),
        Account(code="3000", name="Owner Equity", account_type="equity", **common),
        Account(code="4000", name="Sales Revenue", account_type="income", **common),
        Account(code="5000", name="Cost of Goods Sold", account_type="expense", **common),
        Account(code="5100", name="Rent", account_type="expense", **common),
        Account(code="5200", name="Salaries", account_type="expense", **common),
        Account(code="2210", name="Provident Fund Payable", account_type="liability", **common),
        Account(code="2220", name="Employee State Insurance Payable", account_type="liability", **common),
        Account(code="2230", name="Payroll TDS Payable", account_type="liability", **common),
        Account(code="2240", name="Net Salaries Payable", account_type="liability", **common),
    ]
    db.add_all(accounts)
    await db.flush()

    invoice = Invoice(
        invoice_number="INV-1001",
        customer_id=customers[0].id,
        issue_date=today - timedelta(days=8),
        due_date=today + timedelta(days=7),
        status="sent",
        subtotal=Decimal("5667"),
        tax=Decimal("283"),
        total=Decimal("5950"),
        currency="INR",
        source_order_id=order.id,
        **common,
    )
    paid_invoice = Invoice(
        invoice_number="INV-1002",
        customer_id=customers[1].id,
        issue_date=today - timedelta(days=22),
        due_date=today - timedelta(days=2),
        status="paid",
        subtotal=Decimal("11800"),
        tax=Decimal("590"),
        total=Decimal("12390"),
        amount_paid=Decimal("12390"),
        currency="INR",
        **common,
    )
    db.add_all([invoice, paid_invoice])
    await db.flush()
    db.add(
        Payment(
            invoice_id=paid_invoice.id,
            amount=Decimal("12390"),
            method="bank",
            paid_on=today - timedelta(days=10),
            reference="NEFT-9921",
            **common,
        )
    )

    company = Company(
        name="Aurora Boutique Pvt Ltd",
        industry="Retail",
        website="https://auroraboutique.in",
        email="orders@auroraboutique.in",
        phone="+91 98450 11223",
        city="Bengaluru",
        state="Karnataka",
        annual_revenue=Decimal("8200000"),
        **common,
    )
    db.add(company)
    await db.flush()
    db.add_all(
        [
            Contact(company_id=company.id, first_name="Meera", last_name="Rao", email="meera@auroraboutique.in", phone="+91 98450 11223", title="Founder", whatsapp_opt_in=True, **common),
            Lead(name="Rahul Menon", company_name="Dapper Studio", email="rahul@dapperstudio.in", source="instagram", status="qualified", score=78, estimated_value=Decimal("125000"), whatsapp_opt_in=True, next_follow_up=today + timedelta(days=2), **common),
            Lead(name="Sana Kapoor", company_name="Threadline", email="sana@threadline.in", source="referral", status="new", score=55, estimated_value=Decimal("64000"), **common),
        ]
    )
    db.add(
        Deal(
            name="Aurora Festive Drop",
            company_id=company.id,
            stage="negotiation",
            amount=Decimal("450000"),
            probability=65,
            expected_close_date=today + timedelta(days=20),
            owner_id=admin.id,
            **common,
        )
    )

    department = Department(name="Operations", description="Warehouse and fulfilment", **common)
    db.add(department)
    await db.flush()
    db.add_all(
        [
            Employee(employee_code="EMP-001", first_name="Ananya", last_name="Sharma", email="ananya@hertex.dev", designation="Operations Lead", department_id=department.id, date_of_joining=today - timedelta(days=400), salary=Decimal("85000"), **common),
            Employee(employee_code="EMP-002", first_name="Vikram", last_name="Iyer", email="vikram@hertex.dev", designation="Sales Manager", department_id=department.id, date_of_joining=today - timedelta(days=210), salary=Decimal("95000"), **common),
        ]
    )

    project = Project(
        name="Festive Storefront",
        code="PRJ-FEST",
        number="PRJ-00001",
        description="Seasonal storefront refresh and campaign assets",
        status="active",
        start_date=today - timedelta(days=15),
        end_date=today + timedelta(days=30),
        budget=Decimal("350000"),
        client_name="Aurora Boutique",
        manager_id=admin.id,
        **common,
    )
    db.add(project)
    await db.flush()
    db.add_all(
        [
            Task(project_id=project.id, title="Design landing page", number="PRJ-T00001", status="done", priority="high", estimated_hours=Decimal("24"), actual_hours=Decimal("22"), billable_rate=Decimal("2500"), budget_amount=Decimal("60000"), is_billable=True, **common),
            Task(project_id=project.id, title="Shoot campaign photography", number="PRJ-T00002", status="in_progress", priority="high", estimated_hours=Decimal("16"), actual_hours=Decimal("6"), billable_rate=Decimal("3000"), budget_amount=Decimal("48000"), due_date=today + timedelta(days=6), is_billable=True, **common),
            Task(project_id=project.id, title="Publish social cut-downs", number="PRJ-T00003", status="todo", priority="medium", estimated_hours=Decimal("12"), billable_rate=Decimal("1800"), budget_amount=Decimal("21600"), due_date=today + timedelta(days=12), is_billable=True, **common),
        ]
    )

    db.add(
        Ticket(
            ticket_number="TKT-1001",
            subject="Wholesale order sizing query",
            description="Aurora asked for a size breakdown before dispatch.",
            customer_id=customers[0].id,
            requester_name="Meera Rao",
            requester_email="meera@auroraboutique.in",
            channel="whatsapp",
            priority="high",
            status="open",
            assignee_id=admin.id,
            sla_due_at=None,
            **common,
        )
    )

    segment = Segment(name="WhatsApp VIP buyers", description="Opted-in contacts with recent orders", filters={"whatsapp_opt_in": True}, **common)
    db.add(segment)
    await db.flush()
    db.add(
        Campaign(
            name="Festive WhatsApp Drop",
            channel="whatsapp",
            status="scheduled",
            start_date=today + timedelta(days=3),
            end_date=today + timedelta(days=17),
            budget=Decimal("75000"),
            spend=Decimal("12000"),
            goal="Drive repeat orders for the festive capsule",
            **common,
        )
    )


async def seed_all() -> None:
    async with AsyncSessionLocal() as db:
        permissions = await seed_permissions(db)
        roles = await seed_roles(db, permissions)
        tenant, admin = await seed_tenant_and_admin(db, roles)
        await seed_settings(db, tenant)
        await seed_demo(db, tenant, admin)
        await db.commit()


async def main() -> None:
    from app.db.registry import Base as _Base

    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    await seed_all()
    await engine.dispose()
    print(f"Seed complete. Sign in as {settings.SEED_ADMIN_EMAIL} / {settings.SEED_ADMIN_PASSWORD}")


if __name__ == "__main__":
    asyncio.run(main())
