import asyncio
import logging
from datetime import date
from uuid import UUID

from sqlalchemy import func, select

from app.workers.celery_app import celery_app

logger = logging.getLogger("hertex.workers")


def _run(coroutine):
    return asyncio.run(coroutine)


@celery_app.task(name="hertex.send_notification", bind=True, max_retries=3)
def send_notification(self, channel: str, recipient: str, message: str) -> dict[str, str]:
    """Delivery seam for email, WhatsApp and SMS providers."""
    logger.info("notification.queued", extra={"channel": channel, "recipient": recipient})
    return {"status": "queued", "channel": channel, "recipient": recipient, "message": message}


@celery_app.task(name="hertex.refresh_analytics")
def refresh_analytics(tenant_id: str | None = None) -> dict[str, int]:
    return _run(_refresh_analytics(tenant_id))


async def _refresh_analytics(tenant_id: str | None) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal
    from app.modules.finance.models import Invoice, Payment
    from app.modules.inventory.models import Product

    async with AsyncSessionLocal() as db:
        invoice_stmt = select(func.count(Invoice.id))
        payment_stmt = select(func.count(Payment.id))
        product_stmt = select(func.count(Product.id))
        if tenant_id:
            invoice_stmt = invoice_stmt.where(Invoice.tenant_id == tenant_id)
            payment_stmt = payment_stmt.where(Payment.tenant_id == tenant_id)
            product_stmt = product_stmt.where(Product.tenant_id == tenant_id)
        counts = {
            "invoices": int(await db.scalar(invoice_stmt) or 0),
            "payments": int(await db.scalar(payment_stmt) or 0),
            "products": int(await db.scalar(product_stmt) or 0),
        }
    logger.info("analytics.refreshed", extra={"tenant_id": tenant_id, **counts})
    return counts


@celery_app.task(name="hertex.scan_overdue_invoices")
def scan_overdue_invoices() -> dict[str, int]:
    return _run(_scan_overdue_invoices())


async def _scan_overdue_invoices() -> dict[str, int]:
    from app.db.session import AsyncSessionLocal
    from app.modules.finance.models import Invoice

    today = date.today()
    stmt = select(Invoice).where(
        Invoice.is_active.is_(True),
        Invoice.due_date.is_not(None),
        Invoice.due_date < today,
        Invoice.status.in_(("posted", "sent", "partially_paid")),
        Invoice.amount_paid < Invoice.total,
    )
    async with AsyncSessionLocal() as db:
        invoices = (await db.scalars(stmt)).all()
        for invoice in invoices:
            invoice.status = "overdue"
        await db.commit()
    logger.info("invoices.overdue.scanned", extra={"count": len(invoices)})
    return {"marked_overdue": len(invoices)}


@celery_app.task(name="hertex.dispatch_project_outbox", bind=True, max_retries=3)
def dispatch_project_outbox(self, tenant_id: str, limit: int = 50) -> dict[str, int]:
    return _run(_dispatch_project_outbox(UUID(str(tenant_id)), limit))


async def _dispatch_project_outbox(tenant_id: UUID, limit: int) -> dict[str, int]:
    from app.db.session import AsyncSessionLocal
    from app.modules.projects.services import dispatch_outbox

    async with AsyncSessionLocal() as db:
        result = await dispatch_outbox(db, limit=limit, tenant_id=tenant_id)
        await db.commit()
    logger.info(
        "project.outbox.dispatched",
        extra={"tenant_id": str(tenant_id), **result},
    )
    return result


@celery_app.task(name="hertex.process_campaign_send")
def process_campaign_send(send_id: str, channel: str = "whatsapp") -> dict[str, str]:
    """Fan-out placeholder that a provider adapter can replace."""
    logger.info("campaign.send.queued", extra={"send_id": send_id, "channel": channel})
    return {"status": "queued", "send_id": send_id, "channel": channel}
