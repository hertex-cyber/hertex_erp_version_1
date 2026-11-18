from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select

from app.db.session import AsyncSessionLocal
from app.modules.finance.models import Account, FinanceApproval, JournalEntry, JournalLine
from app.modules.inventory.models import Product, StockMove


@pytest.mark.asyncio
async def test_inventory_adjustments_post_balanced_idempotent_journals(
    client, auth, approver_auth
):
    marker = uuid4().hex[:10].upper()
    idempotency_key = uuid4().hex
    reverse_idempotency_key = uuid4().hex
    product_id = None
    move_ids = []
    journal_ids = []

    try:
        product = await client.post(
            "/api/v1/inventory/products",
            headers=auth,
            json={
                "sku": f"ADJ-{marker}",
                "name": f"Adjustment test product {marker}",
                "purchase_price": "25.00",
            },
        )
        assert product.status_code == 201, product.text
        product_id = product.json()["id"]

        payload = {
            "product_id": product_id,
            "quantity": "2",
            "unit_cost": "25.00",
            "adjustment_date": "2026-11-18",
            "reason": "Physical count surplus",
            "reference": f"COUNT-{marker}",
        }
        response = await client.post(
            "/api/v1/inventory/stock-adjustments",
            headers={**auth, "Idempotency-Key": idempotency_key},
            json=payload,
        )
        assert response.status_code == 201, response.text
        increase = response.json()
        move_ids.append(increase["id"])
        assert increase["movement_type"] == "adjustment"
        assert increase["status"] == "pending_approval"
        assert increase["journal_entry_id"] is None
        levels = await client.get("/api/v1/inventory/stock-levels", headers=auth)
        assert Decimal(
            next(row for row in levels.json() if row["product_id"] == product_id)["on_hand"]
        ) == Decimal("0")

        approvals = await client.get("/api/v1/finance/approvals", headers=auth)
        increase_approval = next(
            row for row in approvals.json()["items"] if row["entity_id"] == increase["id"]
        )
        approved_increase = await client.post(
            f"/api/v1/finance/approvals/{increase_approval['id']}/approve",
            headers=approver_auth,
            json={"reason": "Count sheet reviewed"},
        )
        assert approved_increase.status_code == 200, approved_increase.text
        increase = (
            await client.get(f"/api/v1/inventory/stock-moves/{increase['id']}", headers=auth)
        ).json()
        journal_ids.append(increase["journal_entry_id"])
        assert increase["status"] == "posted"
        levels = await client.get("/api/v1/inventory/stock-levels", headers=auth)
        assert Decimal(
            next(row for row in levels.json() if row["product_id"] == product_id)["on_hand"]
        ) == Decimal("2")

        retry = await client.post(
            "/api/v1/inventory/stock-adjustments",
            headers={**auth, "Idempotency-Key": idempotency_key},
            json=payload,
        )
        assert retry.status_code == 201, retry.text
        assert retry.json()["id"] == increase["id"]

        conflict = await client.post(
            "/api/v1/inventory/stock-adjustments",
            headers={**auth, "Idempotency-Key": idempotency_key},
            json={**payload, "quantity": "-2"},
        )
        assert conflict.status_code == 409, conflict.text

        decrease = await client.post(
            "/api/v1/inventory/stock-adjustments",
            headers={**auth, "Idempotency-Key": reverse_idempotency_key},
            json={**payload, "quantity": "-1", "reason": "Damaged stock write-off"},
        )
        assert decrease.status_code == 201, decrease.text
        move_ids.append(decrease.json()["id"])
        assert decrease.json()["status"] == "pending_approval"
        approvals = await client.get("/api/v1/finance/approvals", headers=auth)
        decrease_approval = next(
            row for row in approvals.json()["items"] if row["entity_id"] == decrease.json()["id"]
        )
        approved_decrease = await client.post(
            f"/api/v1/finance/approvals/{decrease_approval['id']}/approve",
            headers=approver_auth,
            json={"reason": "Write-off documentation reviewed"},
        )
        assert approved_decrease.status_code == 200, approved_decrease.text
        decrease = (
            await client.get(
                f"/api/v1/inventory/stock-moves/{decrease.json()['id']}", headers=auth
            )
        ).json()
        journal_ids.append(decrease["journal_entry_id"])
        levels = await client.get("/api/v1/inventory/stock-levels", headers=auth)
        assert Decimal(
            next(row for row in levels.json() if row["product_id"] == product_id)["on_hand"]
        ) == Decimal("1")

        rejected = await client.post(
            "/api/v1/inventory/stock-adjustments",
            headers={**auth, "Idempotency-Key": uuid4().hex},
            json={**payload, "quantity": "3", "reason": "Unverified count"},
        )
        assert rejected.status_code == 201, rejected.text
        move_ids.append(rejected.json()["id"])
        approvals = await client.get("/api/v1/finance/approvals", headers=auth)
        rejected_approval = next(
            row for row in approvals.json()["items"] if row["entity_id"] == rejected.json()["id"]
        )
        rejected_response = await client.post(
            f"/api/v1/finance/approvals/{rejected_approval['id']}/reject",
            headers=approver_auth,
            json={"reason": "Count evidence does not reconcile"},
        )
        assert rejected_response.status_code == 200, rejected_response.text
        rejected_move = await client.get(
            f"/api/v1/inventory/stock-moves/{rejected.json()['id']}", headers=auth
        )
        assert rejected_move.json()["status"] == "rejected"
        assert rejected_move.json()["journal_entry_id"] is None
        levels = await client.get("/api/v1/inventory/stock-levels", headers=auth)
        assert Decimal(
            next(row for row in levels.json() if row["product_id"] == product_id)["on_hand"]
        ) == Decimal("1")

        direct_move = await client.post(
            "/api/v1/inventory/stock-moves",
            headers=auth,
            json={
                "product_id": product_id,
                "movement_type": "adjustment",
                "quantity": "1",
                "unit_cost": "25.00",
            },
        )
        assert direct_move.status_code == 405, direct_move.text
        direct_update = await client.patch(
            f"/api/v1/inventory/stock-moves/{increase['id']}",
            headers=auth,
            json={"reason": "Changed reason"},
        )
        assert direct_update.status_code == 405, direct_update.text
        direct_delete = await client.delete(
            f"/api/v1/inventory/stock-moves/{increase['id']}",
            headers=auth,
        )
        assert direct_delete.status_code == 405, direct_delete.text

        async with AsyncSessionLocal() as db:
            increase_entry = await db.scalar(
                select(JournalEntry).where(JournalEntry.id == UUID(increase["journal_entry_id"]))
            )
            decrease_entry = await db.scalar(
                select(JournalEntry).where(JournalEntry.id == UUID(decrease["journal_entry_id"]))
            )
            assert increase_entry is not None and increase_entry.status == "posted"
            assert decrease_entry is not None and decrease_entry.status == "posted"
            increase_rows = (
                await db.execute(
                    select(JournalLine, Account.code)
                    .join(Account, Account.id == JournalLine.account_id)
                    .where(JournalLine.journal_entry_id == increase_entry.id)
                )
            ).all()
            decrease_rows = (
                await db.execute(
                    select(JournalLine, Account.code)
                    .join(Account, Account.id == JournalLine.account_id)
                    .where(JournalLine.journal_entry_id == decrease_entry.id)
                )
            ).all()
            increase_accounts = {code: (line.debit, line.credit) for line, code in increase_rows}
            decrease_accounts = {code: (line.debit, line.credit) for line, code in decrease_rows}
            assert increase_accounts == {"1200": (50, 0), "5000": (0, 50)}
            assert decrease_accounts == {"1200": (0, 25), "5000": (25, 0)}
    finally:
        async with AsyncSessionLocal() as db:
            move_uuids = [UUID(item) for item in move_ids]
            journal_uuids = [UUID(item) for item in journal_ids]
            if move_uuids:
                await db.execute(
                    delete(FinanceApproval).where(FinanceApproval.entity_id.in_(move_uuids))
                )
            if move_uuids:
                await db.execute(delete(StockMove).where(StockMove.id.in_(move_uuids)))
            if journal_uuids:
                await db.execute(delete(JournalLine).where(JournalLine.journal_entry_id.in_(journal_uuids)))
                await db.execute(delete(JournalEntry).where(JournalEntry.id.in_(journal_uuids)))
            if product_id:
                await db.execute(delete(Product).where(Product.id == UUID(product_id)))
            await db.commit()
