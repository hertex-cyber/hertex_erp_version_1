from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_vendor_invoice_approval_posts_accounts_payable(client, auth):
    marker = uuid4().hex[:8]
    products = await client.get(
        "/api/v1/inventory/products", headers=auth, params={"size": 1}
    )
    product = products.json()["items"][0]

    vendor = await client.post(
        "/api/v1/procurement/vendors",
        headers=auth,
        json={"code": f"V-{marker}", "name": f"Pytest Vendor {marker}"},
    )
    assert vendor.status_code == 201, vendor.text
    vendor_id = vendor.json()["id"]

    po = await client.post(
        "/api/v1/procurement/purchase-orders",
        headers=auth,
        json={
            "vendor_id": vendor_id,
            "order_date": date.today().isoformat(),
            "lines": [
                {"product_id": product["id"], "quantity": 2, "unit_price": "100.00"}
            ],
        },
    )
    assert po.status_code == 201, po.text
    po_body = po.json()

    approved = await client.post(
        f"/api/v1/procurement/purchase-orders/{po_body['id']}/approve", headers=auth
    )
    assert approved.status_code == 200, approved.text

    receipt = await client.post(
        f"/api/v1/procurement/purchase-orders/{po_body['id']}/receive",
        headers=auth,
        json={
            "purchase_order_id": po_body["id"],
            "received_date": date.today().isoformat(),
        },
    )
    assert receipt.status_code == 201, receipt.text

    invoice_number = f"VINV-{marker}"
    vendor_invoice = await client.post(
        "/api/v1/procurement/vendor-invoices",
        headers=auth,
        json={
            "vendor_id": vendor_id,
            "purchase_order_id": po_body["id"],
            "invoice_number": invoice_number,
            "issue_date": date.today().isoformat(),
            "amount": "200.00",
            "tax_amount": "0.00",
        },
    )
    assert vendor_invoice.status_code == 201, vendor_invoice.text

    approved_invoice = await client.post(
        f"/api/v1/procurement/vendor-invoices/{vendor_invoice.json()['id']}/approve",
        headers=auth,
    )
    assert approved_invoice.status_code == 200, approved_invoice.text
    assert approved_invoice.json()["status"] == "approved"

    entries = await client.get(
        "/api/v1/finance/journal-entries", headers=auth, params={"size": 200}
    )
    assert entries.status_code == 200
    entry = next(
        (
            row
            for row in entries.json()["items"]
            if row["reference"] == f"VINV:{invoice_number}"
        ),
        None,
    )
    assert entry is not None
    assert entry["status"] == "posted"
    debit = sum(Decimal(line["debit"]) for line in entry["lines"])
    credit = sum(Decimal(line["credit"]) for line in entry["lines"])
    assert debit == credit == Decimal("200.00")
    codes = {line["account"]["code"] for line in entry["lines"]}
    assert {"1200", "2000"} <= codes


TALLY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<ENVELOPE>
  <BODY>
    <DATA>
      <TALLYMESSAGE>
        <LEDGER NAME="Pytest Import Cash">
          <PARENT>Cash-in-Hand</PARENT>
          <OPENINGBALANCE>5000.00</OPENINGBALANCE>
        </LEDGER>
        <LEDGER NAME="Pytest Import Sole Trader">
          <PARENT>Capital Account</PARENT>
          <OPENINGBALANCE>-5000.00</OPENINGBALANCE>
        </LEDGER>
        <LEDGER NAME="Pytest Import Debtors">
          <PARENT>Sundry Debtors</PARENT>
          <OPENINGBALANCE>0.00</OPENINGBALANCE>
        </LEDGER>
      </TALLYMESSAGE>
    </DATA>
  </BODY>
</ENVELOPE>
"""


@pytest.mark.asyncio
async def test_tally_import_creates_accounts_and_opening_journal(client, auth):
    response = await client.post(
        "/api/v1/finance/tally/import",
        headers=auth,
        files={"file": ("tally.xml", TALLY_XML.encode(), "application/xml")},
        data={"opening_date": "2026-04-01", "post_opening_balance": "true"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["accounts_seen"] == 3
    assert body["accounts_created"] >= 3
    assert body["opening_balance_posted"] is True
    assert body["journal_entry_id"]

    accounts = await client.get(
        "/api/v1/finance/accounts", headers=auth, params={"q": "Pytest Import"}
    )
    assert accounts.status_code == 200
    names = {row["name"] for row in accounts.json()["items"]}
    assert {"Pytest Import Cash", "Pytest Import Sole Trader"} <= names

    entries = await client.get(
        "/api/v1/finance/journal-entries", headers=auth, params={"size": 200}
    )
    opening = next(
        (
            row
            for row in entries.json()["items"]
            if row["reference"] == "TALLY:OPENING"
        ),
        None,
    )
    assert opening is not None
    assert opening["status"] == "posted"
    debit = sum(Decimal(line["debit"]) for line in opening["lines"])
    credit = sum(Decimal(line["credit"]) for line in opening["lines"])
    assert debit == credit == Decimal("5000.00")

    repeated = await client.post(
        "/api/v1/finance/tally/import",
        headers=auth,
        files={"file": ("tally.xml", TALLY_XML.encode(), "application/xml")},
        data={"opening_date": "2026-04-01", "post_opening_balance": "true"},
    )
    assert repeated.status_code == 200, repeated.text
    repeated_body = repeated.json()
    assert repeated_body["accounts_created"] == 0
    assert repeated_body["opening_balance_posted"] is False
    assert any("already exists" in warning for warning in repeated_body["warnings"]), repeated_body
