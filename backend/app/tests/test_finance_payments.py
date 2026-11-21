from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_payment_creation_posts_to_mapped_bank_account_and_is_idempotent(client, auth):
    accounts_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in accounts_response.json()["items"]}

    invoice_response = await client.post(
        "/api/v1/finance/invoices",
        headers=auth,
        json={
            "issue_date": date.today().isoformat(),
            "status": "draft",
            "subtotal": "250.00",
            "tax": "0.00",
            "total": "250.00",
            "currency": "INR",
        },
    )
    assert invoice_response.status_code == 201, invoice_response.text
    invoice = invoice_response.json()
    posted_invoice = await client.post(
        f"/api/v1/finance/invoices/{invoice['id']}/post",
        headers=auth,
    )
    assert posted_invoice.status_code == 200, posted_invoice.text

    bank_response = await client.post(
        "/api/v1/finance/bank-accounts",
        headers=auth,
        json={
            "name": "Payment test bank",
            "bank_name": "Test Bank",
            "account_number": "0000123456",
            "currency": "INR",
            "ledger_account_id": accounts["1010"],
        },
    )
    assert bank_response.status_code == 201, bank_response.text

    payload = {
        "invoice_id": invoice["id"],
        "amount": "125.00",
        "method": "bank",
        "bank_account_id": bank_response.json()["id"],
        "paid_on": date.today().isoformat(),
        "reference": "BANK-RECEIPT-001",
    }
    key = "test-payment-idempotency-001"
    created = await client.post(
        "/api/v1/finance/payments",
        headers={**auth, "Idempotency-Key": key},
        json=payload,
    )
    assert created.status_code == 201, created.text
    payment = created.json()
    assert payment["journal_entry_id"]
    assert payment["bank_account_id"] == bank_response.json()["id"]

    repeated = await client.post(
        "/api/v1/finance/payments",
        headers={**auth, "Idempotency-Key": key},
        json=payload,
    )
    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["id"] == payment["id"]

    reused_key = await client.post(
        "/api/v1/finance/payments",
        headers={**auth, "Idempotency-Key": key},
        json={**payload, "amount": "100.00"},
    )
    assert reused_key.status_code == 409, reused_key.text

    invoice_after_payment = await client.get(
        f"/api/v1/finance/invoices/{invoice['id']}", headers=auth
    )
    assert invoice_after_payment.status_code == 200, invoice_after_payment.text
    assert Decimal(invoice_after_payment.json()["amount_paid"]) == Decimal("125.00")
    assert invoice_after_payment.json()["status"] == "partially_paid"

    journals = await client.get(
        "/api/v1/finance/journal-entries",
        headers=auth,
        params={"size": 200},
    )
    journal = next(
        entry
        for entry in journals.json()["items"]
        if entry["id"] == payment["journal_entry_id"]
    )
    assert journal["status"] == "posted"
    assert {line["account"]["code"] for line in journal["lines"]} == {"1010", "1100"}
    assert sum(Decimal(line["debit"]) for line in journal["lines"]) == Decimal("125.00")
    assert sum(Decimal(line["credit"]) for line in journal["lines"]) == Decimal("125.00")


@pytest.mark.asyncio
async def test_payment_requires_valid_open_invoice_bank_mapping_and_idempotency(client, auth):
    invoice_response = await client.post(
        "/api/v1/finance/invoices",
        headers=auth,
        json={
            "issue_date": date.today().isoformat(),
            "status": "draft",
            "subtotal": "50.00",
            "tax": "0.00",
            "total": "50.00",
            "currency": "INR",
        },
    )
    assert invoice_response.status_code == 201, invoice_response.text
    invoice = invoice_response.json()
    payload = {
        "invoice_id": invoice["id"],
        "amount": "10.00",
        "method": "bank",
        "paid_on": date.today().isoformat(),
    }
    no_key = await client.post("/api/v1/finance/payments", headers=auth, json=payload)
    assert no_key.status_code == 422, no_key.text

    not_posted = await client.post(
        "/api/v1/finance/payments",
        headers={**auth, "Idempotency-Key": "test-payment-draft-001"},
        json=payload,
    )
    assert not_posted.status_code == 422, not_posted.text

    posted_invoice = await client.post(
        f"/api/v1/finance/invoices/{invoice['id']}/post", headers=auth
    )
    assert posted_invoice.status_code == 200, posted_invoice.text
    no_bank = await client.post(
        "/api/v1/finance/payments",
        headers={**auth, "Idempotency-Key": "test-payment-no-bank-001"},
        json=payload,
    )
    assert no_bank.status_code == 422, no_bank.text


@pytest.mark.asyncio
async def test_vendor_payment_settles_approved_bill_and_posts_ap_journal(
    client, auth, approver_auth
):
    from uuid import uuid4

    marker = uuid4().hex[:8]
    products = await client.get(
        "/api/v1/inventory/products", headers=auth, params={"size": 1}
    )
    product = products.json()["items"][0]
    vendor = await client.post(
        "/api/v1/procurement/vendors",
        headers=auth,
        json={"code": f"VP-{marker}", "name": f"Payment Vendor {marker}"},
    )
    assert vendor.status_code == 201, vendor.text

    po = await client.post(
        "/api/v1/procurement/purchase-orders",
        headers=auth,
        json={
            "vendor_id": vendor.json()["id"],
            "order_date": date.today().isoformat(),
            "lines": [
                {"product_id": product["id"], "quantity": 2, "unit_price": "100.00"}
            ],
        },
    )
    assert po.status_code == 201, po.text
    po_id = po.json()["id"]
    approved_po = await client.post(
        f"/api/v1/procurement/purchase-orders/{po_id}/approve", headers=auth
    )
    assert approved_po.status_code == 200, approved_po.text
    receipt = await client.post(
        f"/api/v1/procurement/purchase-orders/{po_id}/receive",
        headers=auth,
        json={"purchase_order_id": po_id, "received_date": date.today().isoformat()},
    )
    assert receipt.status_code == 200, receipt.text

    invoice = await client.post(
        "/api/v1/procurement/vendor-invoices",
        headers=auth,
        json={
            "vendor_id": vendor.json()["id"],
            "purchase_order_id": po_id,
            "invoice_number": f"VPINV-{marker}",
            "issue_date": date.today().isoformat(),
            "amount": "200.00",
            "tax_amount": "0.00",
        },
    )
    assert invoice.status_code == 201, invoice.text
    invoice_id = invoice.json()["id"]
    approved_invoice = await client.post(
        f"/api/v1/procurement/vendor-invoices/{invoice_id}/approve", headers=auth
    )
    assert approved_invoice.status_code == 200, approved_invoice.text

    accounts_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in accounts_response.json()["items"]}
    bank = await client.post(
        "/api/v1/finance/bank-accounts",
        headers=auth,
        json={
            "name": f"AP test bank {marker}",
            "bank_name": "Test Bank",
            "account_number": marker,
            "currency": "INR",
            "ledger_account_id": accounts["1010"],
        },
    )
    assert bank.status_code == 201, bank.text

    open_bills = await client.get(
        "/api/v1/finance/vendor-payments/outstanding",
        headers=auth,
        params={"q": f"VPINV-{marker}"},
    )
    assert open_bills.status_code == 200, open_bills.text
    assert len(open_bills.json()["items"]) == 1
    assert Decimal(open_bills.json()["items"][0]["outstanding"]) == Decimal("200.00")

    payload = {
        "vendor_invoice_id": invoice_id,
        "amount": "75.00",
        "method": "bank",
        "bank_account_id": bank.json()["id"],
        "paid_on": date.today().isoformat(),
        "reference": f"AP-{marker}",
    }
    key = f"vendor-payment-{marker}"
    overpayment = await client.post(
        "/api/v1/finance/vendor-payments",
        headers={**auth, "Idempotency-Key": f"vendor-overpay-{marker}"},
        json={**payload, "amount": "201.00"},
    )
    assert overpayment.status_code == 422, overpayment.text

    payment = await client.post(
        "/api/v1/finance/vendor-payments",
        headers={**auth, "Idempotency-Key": key},
        json=payload,
    )
    assert payment.status_code == 201, payment.text
    assert payment.json()["status"] == "pending_approval"
    assert payment.json()["journal_entry_id"] is None

    retry = await client.post(
        "/api/v1/finance/vendor-payments",
        headers={**auth, "Idempotency-Key": key},
        json=payload,
    )
    assert retry.status_code == 201, retry.text
    assert retry.json()["id"] == payment.json()["id"]

    reused_key = await client.post(
        "/api/v1/finance/vendor-payments",
        headers={**auth, "Idempotency-Key": key},
        json={**payload, "amount": "50.00"},
    )
    assert reused_key.status_code == 409, reused_key.text

    reserved_balance = await client.get(
        "/api/v1/finance/vendor-payments/outstanding",
        headers=auth,
        params={"q": f"VPINV-{marker}"},
    )
    assert Decimal(reserved_balance.json()["items"][0]["outstanding"]) == Decimal("125.00")
    competing_request = await client.post(
        "/api/v1/finance/vendor-payments",
        headers={**auth, "Idempotency-Key": f"vendor-payment-extra-{marker}"},
        json={**payload, "amount": "126.00"},
    )
    assert competing_request.status_code == 422, competing_request.text

    invoice_after = await client.get(
        f"/api/v1/procurement/vendor-invoices/{invoice_id}", headers=auth
    )
    assert invoice_after.status_code == 200, invoice_after.text
    assert Decimal(invoice_after.json()["paid_amount"]) == Decimal("0.00")
    assert invoice_after.json()["status"] == "approved"
    approvals = await client.get("/api/v1/finance/approvals", headers=auth)
    approval = next(
        row for row in approvals.json()["items"] if row["entity_id"] == payment.json()["id"]
    )
    approved = await client.post(
        f"/api/v1/finance/approvals/{approval['id']}/approve",
        headers=approver_auth,
        json={"reason": "Bank instruction verified"},
    )
    assert approved.status_code == 200, approved.text
    payment_history = await client.get("/api/v1/finance/vendor-payments", headers=auth)
    posted_payment = next(
        row for row in payment_history.json()["items"] if row["id"] == payment.json()["id"]
    )
    assert posted_payment["status"] == "posted"
    assert posted_payment["journal_entry_id"]
    invoice_after = await client.get(
        f"/api/v1/procurement/vendor-invoices/{invoice_id}", headers=auth
    )
    assert Decimal(invoice_after.json()["paid_amount"]) == Decimal("75.00")
    assert invoice_after.json()["status"] == "partially_paid"
    rejected_payment = await client.post(
        "/api/v1/finance/vendor-payments",
        headers={**auth, "Idempotency-Key": f"vendor-payment-reject-{marker}"},
        json={**payload, "amount": "30.00", "reference": f"AP-REJECT-{marker}"},
    )
    assert rejected_payment.status_code == 201, rejected_payment.text
    pending_approvals = await client.get("/api/v1/finance/approvals", headers=auth)
    rejected_approval = next(
        row for row in pending_approvals.json()["items"]
        if row["entity_id"] == rejected_payment.json()["id"]
    )
    rejected_response = await client.post(
        f"/api/v1/finance/approvals/{rejected_approval['id']}/reject",
        headers=approver_auth,
        json={"reason": "Payment instruction needs correction"},
    )
    assert rejected_response.status_code == 200, rejected_response.text
    payment_history = await client.get("/api/v1/finance/vendor-payments", headers=auth)
    rejected_row = next(
        row for row in payment_history.json()["items"] if row["id"] == rejected_payment.json()["id"]
    )
    assert rejected_row["status"] == "rejected"
    invoice_after_rejection = await client.get(
        f"/api/v1/procurement/vendor-invoices/{invoice_id}", headers=auth
    )
    assert Decimal(invoice_after_rejection.json()["paid_amount"]) == Decimal("75.00")
    available_after_rejection = await client.get(
        "/api/v1/finance/vendor-payments/outstanding",
        headers=auth,
        params={"q": f"VPINV-{marker}"},
    )
    assert Decimal(available_after_rejection.json()["items"][0]["outstanding"]) == Decimal("125.00")
    open_after_payment = await client.get(
        "/api/v1/finance/vendor-payments/outstanding",
        headers=auth,
        params={"q": f"VPINV-{marker}"},
    )
    assert Decimal(open_after_payment.json()["items"][0]["outstanding"]) == Decimal("125.00")

    journals = await client.get(
        "/api/v1/finance/journal-entries",
        headers=auth,
        params={"size": 200},
    )
    entry = next(
        row for row in journals.json()["items"] if row["id"] == posted_payment["journal_entry_id"]
    )
    assert entry["status"] == "posted"
    assert {line["account"]["code"] for line in entry["lines"]} == {"1010", "2000"}
    assert sum(Decimal(line["debit"]) for line in entry["lines"]) == Decimal("75.00")
    assert sum(Decimal(line["credit"]) for line in entry["lines"]) == Decimal("75.00")


@pytest.mark.asyncio
async def test_bank_statement_import_deduplicates_and_requires_match_before_reconcile(
    client, auth, approver_auth
):
    accounts_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in accounts_response.json()["items"]}
    bank = await client.post(
        "/api/v1/finance/bank-accounts",
        headers=auth,
        json={
            "name": "Reconciliation test bank",
            "bank_name": "Test Bank",
            "account_number": "RECON-001",
            "currency": "INR",
            "ledger_account_id": accounts["1010"],
        },
    )
    assert bank.status_code == 201, bank.text

    journal = await client.post(
        "/api/v1/finance/journal-entries",
        headers=auth,
        json={
            "entry_date": date.today().isoformat(),
            "reference": "BANK-RECON-001",
            "memo": "Test receipt for reconciliation",
            "lines": [
                {"account_id": accounts["1010"], "debit": "45.00", "credit": "0"},
                {"account_id": accounts["4000"], "debit": "0", "credit": "45.00"},
            ],
        },
    )
    assert journal.status_code == 201, journal.text
    posted = await client.post(
        f"/api/v1/finance/journal-entries/{journal.json()['id']}/post",
        headers=auth,
    )
    assert posted.status_code == 200, posted.text
    approvals = await client.get("/api/v1/finance/approvals", headers=auth)
    approval = next(
        row for row in approvals.json()["items"] if row["entity_id"] == journal.json()["id"]
    )
    approved = await client.post(
        f"/api/v1/finance/approvals/{approval['id']}/approve",
        headers=approver_auth,
        json={"reason": "Reconciliation journal reviewed"},
    )
    assert approved.status_code == 200, approved.text
    posted_journal = await client.get("/api/v1/finance/journal-entries", headers=auth)
    posted = next(
        row for row in posted_journal.json()["items"] if row["id"] == journal.json()["id"]
    )
    line_id = next(
        line["id"]
        for line in posted["lines"]
        if line["account"]["code"] == "1010"
    )

    csv_content = (
        "date,amount,narration,reference\n"
        f"{date.today().isoformat()},45.00,Customer deposit,BANK-RECON-001\n"
    )
    imported = await client.post(
        "/api/v1/finance/bank-transactions/import",
        headers=auth,
        data={"bank_account_id": bank.json()["id"]},
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    assert imported.json() == {"rows_received": 1, "imported": 1, "duplicates": 0}
    repeated_import = await client.post(
        "/api/v1/finance/bank-transactions/import",
        headers=auth,
        data={"bank_account_id": bank.json()["id"]},
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )
    assert repeated_import.status_code == 200, repeated_import.text
    assert repeated_import.json() == {"rows_received": 1, "imported": 0, "duplicates": 1}

    transactions = await client.get(
        "/api/v1/finance/bank-transactions",
        headers=auth,
        params={"bank_account_id": bank.json()["id"]},
    )
    transaction = transactions.json()["items"][0]
    cannot_reconcile_unmatched = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/reconcile",
        headers=auth,
    )
    assert cannot_reconcile_unmatched.status_code == 409

    suggestions = await client.get(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/matches",
        headers=auth,
    )
    assert suggestions.status_code == 200, suggestions.text
    assert suggestions.json()[0]["journal_line_id"] == line_id
    matched = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/match",
        headers=auth,
        json={"journal_line_id": line_id},
    )
    assert matched.status_code == 200, matched.text
    reconciled = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/reconcile",
        headers=auth,
    )
    assert reconciled.status_code == 200, reconciled.text
    assert reconciled.json()["reconciled"] is True

    summary = await client.get(
        f"/api/v1/finance/bank-accounts/{bank.json()['id']}/reconciliation-summary",
        headers=auth,
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["reconciled_count"] == 1
    assert Decimal(summary.json()["difference"]) == Decimal("0.00")

    no_reason = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/unreconcile",
        headers=auth,
        json={"reason": "  "},
    )
    assert no_reason.status_code == 422, no_reason.text
    reversed_reconciliation = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/unreconcile",
        headers=auth,
        json={"reason": "Wrong statement period"},
    )
    assert reversed_reconciliation.status_code == 200, reversed_reconciliation.text
    assert reversed_reconciliation.json()["reconciled"] is False
    assert reversed_reconciliation.json()["matched_journal_line_id"] == line_id
    unlinked = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/unmatch",
        headers=auth,
    )
    assert unlinked.status_code == 200, unlinked.text
    assert unlinked.json()["matched_journal_line_id"] is None


@pytest.mark.asyncio
async def test_statement_signoff_requires_reconciled_balanced_ledger(client, auth):
    accounts_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in accounts_response.json()["items"]}
    invoice = await client.post(
        "/api/v1/finance/invoices",
        headers=auth,
        json={
            "issue_date": date.today().isoformat(),
            "status": "draft",
            "subtotal": "75.00",
            "tax": "0.00",
            "total": "75.00",
            "currency": "INR",
        },
    )
    assert invoice.status_code == 201, invoice.text
    posted_invoice = await client.post(
        f"/api/v1/finance/invoices/{invoice.json()['id']}/post",
        headers=auth,
    )
    assert posted_invoice.status_code == 200, posted_invoice.text

    bank = await client.post(
        "/api/v1/finance/bank-accounts",
        headers=auth,
        json={
            "name": "Statement signoff bank",
            "bank_name": "Test Bank",
            "account_number": uuid4().hex[:12],
            "currency": "INR",
            "ledger_account_id": accounts["1010"],
        },
    )
    assert bank.status_code == 201, bank.text
    payment = await client.post(
        "/api/v1/finance/payments",
        headers={**auth, "Idempotency-Key": f"statement-pay-{uuid4().hex[:16]}"},
        json={
            "invoice_id": invoice.json()["id"],
            "amount": "75.00",
            "method": "bank",
            "bank_account_id": bank.json()["id"],
            "paid_on": date.today().isoformat(),
            "reference": "STATEMENT-RECEIPT",
        },
    )
    assert payment.status_code == 201, payment.text

    statement = await client.post(
        "/api/v1/finance/bank-statements",
        headers=auth,
        json={
            "bank_account_id": bank.json()["id"],
            "statement_reference": "STMT-2026-01",
            "period_start": date.today().isoformat(),
            "period_end": date.today().isoformat(),
            "opening_balance": "100.00",
            "closing_balance": "175.00",
        },
    )
    assert statement.status_code == 201, statement.text
    csv_content = (
        "date,amount,description,reference\n"
        f"{date.today().isoformat()},75.00,Customer receipt,STATEMENT-RECEIPT\n"
    )
    imported = await client.post(
        "/api/v1/finance/bank-transactions/import",
        headers=auth,
        data={
            "bank_account_id": bank.json()["id"],
            "statement_id": statement.json()["id"],
        },
        files={"file": ("statement.csv", csv_content, "text/csv")},
    )
    assert imported.status_code == 200, imported.text

    entries = await client.get(
        "/api/v1/finance/journal-entries",
        headers=auth,
        params={"size": 200},
    )
    assert entries.status_code == 200, entries.text
    entry = next(
        row
        for row in entries.json()["items"]
        if row["id"] == payment.json()["journal_entry_id"]
    )
    bank_line = next(
        line for line in entry["lines"] if line["account_id"] == accounts["1010"]
    )
    transactions = await client.get(
        "/api/v1/finance/bank-transactions",
        headers=auth,
        params={"bank_account_id": bank.json()["id"]},
    )
    transaction = next(
        row for row in transactions.json()["items"] if row["statement_id"] == statement.json()["id"]
    )
    unmatched_signoff = await client.post(
        f"/api/v1/finance/bank-statements/{statement.json()['id']}/sign-off",
        headers=auth,
        json={"reason": "Not yet reconciled"},
    )
    assert unmatched_signoff.status_code == 409, unmatched_signoff.text

    matched = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/match",
        headers=auth,
        json={"journal_line_id": bank_line["id"]},
    )
    assert matched.status_code == 200, matched.text
    reconciled = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/reconcile",
        headers=auth,
    )
    assert reconciled.status_code == 200, reconciled.text
    summary = await client.get(
        f"/api/v1/finance/bank-statements/{statement.json()['id']}/summary",
        headers=auth,
    )
    assert summary.status_code == 200, summary.text
    assert summary.json()["signable"] is True, summary.text
    assert summary.json()["difference"] == "0.00"

    signed_off = await client.post(
        f"/api/v1/finance/bank-statements/{statement.json()['id']}/sign-off",
        headers=auth,
        json={"reason": "Statement movement reconciled to the ledger"},
    )
    assert signed_off.status_code == 200, signed_off.text
    assert signed_off.json()["status"] == "signed_off"
    cannot_unmatch = await client.post(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/unmatch",
        headers=auth,
    )
    assert cannot_unmatch.status_code == 409, cannot_unmatch.text


async def _bank_match_setup(
    client,
    auth,
    approver_auth,
    *,
    amount: str,
    entry_date: date,
    reference: str,
):
    accounts_response = await client.get("/api/v1/finance/accounts", headers=auth)
    accounts = {row["code"]: row["id"] for row in accounts_response.json()["items"]}
    bank = await client.post(
        "/api/v1/finance/bank-accounts",
        headers=auth,
        json={
            "name": f"Bank match setup {uuid4().hex[:8]}",
            "bank_name": "Test Bank",
            "account_number": uuid4().hex[:16],
            "currency": "INR",
            "ledger_account_id": accounts["1010"],
        },
    )
    assert bank.status_code == 201, bank.text
    journal = await client.post(
        "/api/v1/finance/journal-entries",
        headers=auth,
        json={
            "entry_date": entry_date.isoformat(),
            "reference": reference,
            "memo": "Bank match configurable rules test",
            "lines": [
                {"account_id": accounts["1010"], "debit": amount, "credit": "0"},
                {"account_id": accounts["4000"], "debit": "0", "credit": amount},
            ],
        },
    )
    assert journal.status_code == 201, journal.text
    posted = await client.post(
        f"/api/v1/finance/journal-entries/{journal.json()['id']}/post",
        headers=auth,
    )
    assert posted.status_code == 200, posted.text
    approvals = await client.get("/api/v1/finance/approvals", headers=auth)
    approval = next(
        row for row in approvals.json()["items"] if row["entity_id"] == journal.json()["id"]
    )
    approved = await client.post(
        f"/api/v1/finance/approvals/{approval['id']}/approve",
        headers=approver_auth,
        json={"reason": "Bank match test approval"},
    )
    assert approved.status_code == 200, approved.text
    journals = await client.get("/api/v1/finance/journal-entries", headers=auth)
    posted_journal = next(
        row for row in journals.json()["items"] if row["id"] == journal.json()["id"]
    )
    line_id = next(
        line["id"]
        for line in posted_journal["lines"]
        if line["account"]["code"] == "1010"
    )
    return bank.json()["id"], line_id


async def _import_bank_row(client, auth, bank_id, *, txn_date, amount, reference):
    csv_content = (
        "date,amount,narration,reference\n"
        f"{txn_date.isoformat()},{amount},Configurable rules,{reference}\n"
    )
    imported = await client.post(
        "/api/v1/finance/bank-transactions/import",
        headers=auth,
        data={"bank_account_id": bank_id},
        files={"file": ("rules.csv", csv_content, "text/csv")},
    )
    assert imported.status_code == 200, imported.text
    transactions = await client.get(
        "/api/v1/finance/bank-transactions",
        headers=auth,
        params={"bank_account_id": bank_id},
    )
    return transactions.json()["items"][0]


async def _set_match_rule(client, auth, key, value):
    response = await client.put(
        f"/api/v1/settings/values/{key}",
        headers=auth,
        json={"value": value, "reason": "Configurable bank matching test"},
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_bank_match_date_tolerance_is_configurable(client, auth, approver_auth):
    txn_date = date.today() - timedelta(days=20)
    bank_id, line_id = await _bank_match_setup(
        client,
        auth,
        approver_auth,
        amount="55.00",
        entry_date=date.today(),
        reference="DATE-TOL-001",
    )
    transaction = await _import_bank_row(
        client, auth, bank_id, txn_date=txn_date, amount="55.00", reference="DATE-TOL-001"
    )
    rules = await client.get("/api/v1/finance/bank-transactions/match-rules", headers=auth)
    assert rules.status_code == 200, rules.text
    assert rules.json()["date_tolerance_days"] == 14
    suggestions = await client.get(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/matches", headers=auth
    )
    assert suggestions.status_code == 200, suggestions.text
    assert suggestions.json() == []
    await _set_match_rule(client, auth, "finance.bank.match.date_tolerance_days", 30)
    try:
        suggestions = await client.get(
            f"/api/v1/finance/bank-transactions/{transaction['id']}/matches", headers=auth
        )
        assert suggestions.status_code == 200, suggestions.text
        assert suggestions.json()[0]["journal_line_id"] == line_id
        matched = await client.post(
            f"/api/v1/finance/bank-transactions/{transaction['id']}/match",
            headers=auth,
            json={"journal_line_id": line_id},
        )
        assert matched.status_code == 200, matched.text
    finally:
        await _set_match_rule(client, auth, "finance.bank.match.date_tolerance_days", 14)


@pytest.mark.asyncio
async def test_bank_match_amount_mode_absolute_is_configurable(client, auth, approver_auth):
    txn_date = date.today()
    bank_id, line_id = await _bank_match_setup(
        client,
        auth,
        approver_auth,
        amount="60.00",
        entry_date=txn_date,
        reference="AMOUNT-MODE-001",
    )
    transaction = await _import_bank_row(
        client, auth, bank_id, txn_date=txn_date, amount="-60.00", reference="AMOUNT-MODE-001"
    )
    suggestions = await client.get(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/matches", headers=auth
    )
    assert suggestions.json() == []
    await _set_match_rule(client, auth, "finance.bank.match.amount_mode", "absolute")
    try:
        suggestions = await client.get(
            f"/api/v1/finance/bank-transactions/{transaction['id']}/matches", headers=auth
        )
        assert suggestions.json()[0]["journal_line_id"] == line_id
        matched = await client.post(
            f"/api/v1/finance/bank-transactions/{transaction['id']}/match",
            headers=auth,
            json={"journal_line_id": line_id},
        )
        assert matched.status_code == 200, matched.text
    finally:
        await _set_match_rule(client, auth, "finance.bank.match.amount_mode", "signed")


@pytest.mark.asyncio
async def test_bank_match_reference_required_is_configurable(client, auth, approver_auth):
    txn_date = date.today()
    bank_id, line_id = await _bank_match_setup(
        client,
        auth,
        approver_auth,
        amount="70.00",
        entry_date=txn_date,
        reference="LEDGER-REF-001",
    )
    transaction = await _import_bank_row(
        client, auth, bank_id, txn_date=txn_date, amount="70.00", reference="BANK-REF-001"
    )
    suggestions = await client.get(
        f"/api/v1/finance/bank-transactions/{transaction['id']}/matches", headers=auth
    )
    assert suggestions.json()[0]["journal_line_id"] == line_id
    await _set_match_rule(client, auth, "finance.bank.match.reference_required", True)
    try:
        suggestions = await client.get(
            f"/api/v1/finance/bank-transactions/{transaction['id']}/matches", headers=auth
        )
        assert suggestions.json() == []
        rejected = await client.post(
            f"/api/v1/finance/bank-transactions/{transaction['id']}/match",
            headers=auth,
            json={"journal_line_id": line_id},
        )
        assert rejected.status_code == 422, rejected.text
    finally:
        await _set_match_rule(client, auth, "finance.bank.match.reference_required", False)
