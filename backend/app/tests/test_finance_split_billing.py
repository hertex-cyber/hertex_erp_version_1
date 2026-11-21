from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest


async def _setup_received_purchase_order(client, auth):
    marker = uuid4().hex[:8]
    products = await client.get("/api/v1/inventory/products", headers=auth, params={"size": 1})
    product = products.json()["items"][0]
    vendor = await client.post(
        "/api/v1/procurement/vendors",
        headers=auth,
        json={"code": f"V-{marker}", "name": f"Split billing vendor {marker}"},
    )
    assert vendor.status_code == 201, vendor.text
    po = await client.post(
        "/api/v1/procurement/purchase-orders",
        headers=auth,
        json={
            "vendor_id": vendor.json()["id"],
            "order_date": date.today().isoformat(),
            "lines": [{"product_id": product["id"], "quantity": 2, "unit_price": "100.00"}],
        },
    )
    assert po.status_code == 201, po.text
    approved = await client.post(
        f"/api/v1/procurement/purchase-orders/{po.json()['id']}/approve", headers=auth
    )
    assert approved.status_code == 200, approved.text
    receipt = await client.post(
        f"/api/v1/procurement/purchase-orders/{po.json()['id']}/receive",
        headers=auth,
        json={
            "purchase_order_id": po.json()["id"],
            "received_date": date.today().isoformat(),
        },
    )
    assert receipt.status_code == 200, receipt.text
    return vendor.json()["id"], po.json()["id"], receipt.json()


async def _create_vendor_invoice(client, auth, vendor_id, po_id, amount, marker):
    response = await client.post(
        "/api/v1/procurement/vendor-invoices",
        headers=auth,
        json={
            "vendor_id": vendor_id,
            "purchase_order_id": po_id,
            "invoice_number": f"SPLIT-{marker}",
            "issue_date": date.today().isoformat(),
            "amount": str(amount),
            "tax_amount": "0.00",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.asyncio
async def test_split_billing_clears_grn_accrual_across_multiple_invoices(client, auth):
    baseline_grni = await client.get("/api/v1/finance/reports/grni", headers=auth)
    baseline_count = baseline_grni.json()["receipt_count"]
    baseline_total = Decimal(baseline_grni.json()["outstanding_total"])
    vendor_id, po_id, grn = await _setup_received_purchase_order(client, auth)
    first = await _create_vendor_invoice(client, auth, vendor_id, po_id, "80.00", uuid4().hex[:6])
    candidates = await client.get(
        f"/api/v1/procurement/vendor-invoices/{first['id']}/receipt-accrual-candidates",
        headers=auth,
    )
    assert candidates.status_code == 200, candidates.text
    assert len(candidates.json()) == 1
    accrual_id = candidates.json()[0]["grn_accrual_id"]
    allocated = await client.put(
        f"/api/v1/procurement/vendor-invoices/{first['id']}/receipt-allocations",
        headers=auth,
        json={
            "allocations": [
                {"grn_accrual_id": accrual_id, "allocated_amount": "80.00"}
            ]
        },
    )
    assert allocated.status_code == 200, allocated.text
    approved = await client.post(
        f"/api/v1/procurement/vendor-invoices/{first['id']}/approve", headers=auth
    )
    assert approved.status_code == 200, approved.text

    entries = await client.get(
        "/api/v1/finance/journal-entries", headers=auth, params={"size": 200}
    )
    entry = next(
        row for row in entries.json()["items"] if row["reference"] == f"VINV:{first['invoice_number']}"
    )
    grni_line = next(line for line in entry["lines"] if line["account"]["code"] == "2100")
    assert grni_line["debit"] == "80.00"
    grni = await client.get("/api/v1/finance/reports/grni", headers=auth)
    assert grni.json()["receipt_count"] == baseline_count + 1
    assert Decimal(grni.json()["outstanding_total"]) == baseline_total + Decimal("120.00")

    second = await _create_vendor_invoice(client, auth, vendor_id, po_id, "120.00", uuid4().hex[:6])
    allocated = await client.put(
        f"/api/v1/procurement/vendor-invoices/{second['id']}/receipt-allocations",
        headers=auth,
        json={
            "allocations": [
                {"grn_accrual_id": accrual_id, "allocated_amount": "120.00"}
            ]
        },
    )
    assert allocated.status_code == 200, allocated.text
    approved = await client.post(
        f"/api/v1/procurement/vendor-invoices/{second['id']}/approve", headers=auth
    )
    assert approved.status_code == 200, approved.text
    grni = await client.get("/api/v1/finance/reports/grni", headers=auth)
    assert grni.json()["receipt_count"] == baseline_count
    assert Decimal(grni.json()["outstanding_total"]) == baseline_total
    assert grn["grn_number"]


@pytest.mark.asyncio
async def test_split_billing_rejects_over_allocation(client, auth):
    vendor_id, po_id, _ = await _setup_received_purchase_order(client, auth)
    invoice = await _create_vendor_invoice(client, auth, vendor_id, po_id, "250.00", uuid4().hex[:6])
    candidates = await client.get(
        f"/api/v1/procurement/vendor-invoices/{invoice['id']}/receipt-accrual-candidates",
        headers=auth,
    )
    accrual_id = candidates.json()[0]["grn_accrual_id"]
    allocated = await client.put(
        f"/api/v1/procurement/vendor-invoices/{invoice['id']}/receipt-allocations",
        headers=auth,
        json={
            "allocations": [
                {"grn_accrual_id": accrual_id, "allocated_amount": "250.00"}
            ]
        },
    )
    assert allocated.status_code == 409, allocated.text
