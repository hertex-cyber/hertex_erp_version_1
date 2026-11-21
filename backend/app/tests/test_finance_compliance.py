from datetime import date, timedelta
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select

from app.db.session import AsyncSessionLocal
from app.modules.finance.compliance_models import (
    Budget,
    BudgetLine,
    EInvoice,
    EWaybill,
    FinanceAuditLog,
    GstReturn,
    IntercompanyTransaction,
    LedgerBalance,
    OutboxEvent,
)
from app.modules.finance.control_service import sign_payload, verify_signature
from app.modules.finance.models import (
    Account,
    BankAccount,
    BankTransaction,
    FinancialPeriod,
    FixedAsset,
    Invoice,
    InvoiceTaxLine,
    JournalEntry,
    JournalLine,
    TaxCode,
    TaxRegistration,
)
from app.modules.identity.models import User


async def _account(client, auth, marker: str, suffix: str, account_type: str) -> str:
    response = await client.post(
        "/api/v1/finance/accounts",
        headers=auth,
        json={
            "code": f"CMP-{marker}-{suffix}",
            "name": f"Compliance {suffix} {marker}",
            "account_type": account_type,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest_asyncio.fixture
async def temporary_period():
    marker = uuid4().hex[:8]
    start = date.today() - timedelta(days=30)
    async with AsyncSessionLocal() as db:
        admin = await db.scalar(
            select(User).where(User.email == "admin@hertex.dev")
        )
        assert admin is not None
        db.add(
            FinancialPeriod(
                tenant_id=admin.tenant_id,
                created_by_id=admin.id,
                name=f"Compliance control {marker}",
                start_date=start,
                end_date=date.today() + timedelta(days=30),
                status="open",
            )
        )
        await db.commit()
    yield
    async with AsyncSessionLocal() as db:
        await db.execute(
            delete(FinancialPeriod).where(FinancialPeriod.name == f"Compliance control {marker}")
        )
        await db.commit()


@pytest.mark.asyncio
async def test_journal_posting_emits_audit_outbox_and_ledger_balance(
    client, auth, approver_auth, temporary_period
):
    marker = uuid4().hex[:8]
    accounts = await client.get("/api/v1/finance/accounts", headers=auth)
    account_ids = {row["code"]: row["id"] for row in accounts.json()["items"]}
    reference = f"CONTROL-TEST:{marker}"
    created = await client.post(
        "/api/v1/finance/journal-entries",
        headers=auth,
        json={
            "entry_date": date.today().isoformat(),
            "reference": reference,
            "lines": [
                {"account_id": account_ids["1010"], "debit": "75.00", "credit": "0"},
                {"account_id": account_ids["4000"], "debit": "0", "credit": "75.00"},
            ],
        },
    )
    assert created.status_code == 201, created.text
    entry_id = created.json()["id"]

    requested = await client.post(
        f"/api/v1/finance/journal-entries/{entry_id}/post", headers=auth
    )
    assert requested.status_code == 200, requested.text
    approvals = await client.get("/api/v1/finance/approvals", headers=auth, params={"size": 200})
    approval = next(row for row in approvals.json()["items"] if row["entity_id"] == entry_id)
    approved = await client.post(
        f"/api/v1/finance/approvals/{approval['id']}/approve",
        headers=approver_auth,
        json={"reason": "Control-plane verification"},
    )
    assert approved.status_code == 200, approved.text

    audit = await client.get("/api/v1/finance/control/audit", headers=auth, params={"size": 500})
    assert audit.status_code == 200, audit.text
    audit_row = next(
        (
            row for row in audit.json()["items"]
            if row["entity_type"] == "journal_entry" and row["entity_id"] == entry_id
        ),
        None,
    )
    assert audit_row is not None
    assert audit_row["action"] == "post"
    assert audit_row["after_state"]["status"] == "posted"

    outbox = await client.get("/api/v1/finance/control/outbox", headers=auth, params={"size": 500})
    assert outbox.status_code == 200, outbox.text
    outbox_row = next(
        (
            row for row in outbox.json()["items"]
            if row["event_type"] == "journal.posted" and row["aggregate_id"] == entry_id
        ),
        None,
    )
    assert outbox_row is not None
    assert outbox_row["status"] in {"pending", "published"}

    async with AsyncSessionLocal() as db:
        balance = await db.scalar(
            select(LedgerBalance).where(
                LedgerBalance.account_id == UUID(account_ids["1010"]),
                LedgerBalance.debit_total >= 75,
            )
        )
        assert balance is not None
        await db.execute(delete(JournalLine).where(JournalLine.journal_entry_id == UUID(entry_id)))
        await db.execute(delete(JournalEntry).where(JournalEntry.id == UUID(entry_id)))
        await db.execute(
            delete(OutboxEvent).where(
                OutboxEvent.event_type == "journal.posted",
                OutboxEvent.aggregate_id == UUID(entry_id),
            )
        )
        await db.execute(
            delete(FinanceAuditLog).where(FinanceAuditLog.entity_id == UUID(entry_id))
        )
        await db.commit()


@pytest.mark.asyncio
async def test_outbox_webhook_signature_is_verified():
    secret = "0123456789abcdef0123456789abcdef"
    body = b'{"type":"journal.posted"}'
    signature = sign_payload(secret, body)
    assert verify_signature(secret, body, signature) is True
    assert verify_signature(secret, body, signature[:-1] + "0") is False
    assert verify_signature(secret, body, None) is False


@pytest.mark.asyncio
async def test_gst_return_einvoice_and_waybill_lifecycle(client, auth):
    marker = uuid4().hex[:8].upper()
    numeric_marker = str(uuid4().int % 10000).zfill(4)
    gstin = f"29ABCDE{numeric_marker}F1Z5"
    account_ids = []
    tax_code_id = None
    registration_id = None
    invoice_id = None
    invoice_number = None
    journal_ids = []
    gst_return_id = None
    try:
        output_cgst = await _account(client, auth, marker, "OUTCGST", "liability")
        output_sgst = await _account(client, auth, marker, "OUTSGST", "liability")
        output_igst = await _account(client, auth, marker, "OUTIGST", "liability")
        input_cgst = await _account(client, auth, marker, "INCGST", "asset")
        input_sgst = await _account(client, auth, marker, "INSGST", "asset")
        input_igst = await _account(client, auth, marker, "INIGST", "asset")
        account_ids.extend(
            [output_cgst, output_sgst, output_igst, input_cgst, input_sgst, input_igst]
        )

        registration = await client.post(
            "/api/v1/finance/tax/registrations",
            headers=auth,
            json={
                "legal_name": f"Compliance GST {marker}",
                "gstin": gstin,
                "state_code": "29",
                "is_default": False,
            },
        )
        assert registration.status_code == 201, registration.text
        registration_id = registration.json()["id"]

        tax_code = await client.post(
            "/api/v1/finance/tax/codes",
            headers=auth,
            json={
                "code": f"CMP18-{marker}",
                "description": "Compliance 18% GST",
                "cgst_rate": "9",
                "sgst_rate": "9",
                "igst_rate": "18",
                "can_claim_itc": True,
                "output_cgst_account_id": output_cgst,
                "output_sgst_account_id": output_sgst,
                "output_igst_account_id": output_igst,
                "input_cgst_account_id": input_cgst,
                "input_sgst_account_id": input_sgst,
                "input_igst_account_id": input_igst,
            },
        )
        assert tax_code.status_code == 201, tax_code.text
        tax_code_id = tax_code.json()["id"]

        invoice = await client.post(
            "/api/v1/finance/invoices",
            headers=auth,
            json={
                "issue_date": date.today().isoformat(),
                "subtotal": "100.00",
                "tax": "18.00",
                "total": "118.00",
            },
        )
        assert invoice.status_code == 201, invoice.text
        invoice_id = invoice.json()["id"]
        invoice_number = invoice.json()["invoice_number"]

        tax_lines = await client.put(
            f"/api/v1/finance/invoices/{invoice_id}/tax-lines",
            headers=auth,
            json={
                "lines": [
                    {
                        "tax_code_id": tax_code_id,
                        "registration_id": registration_id,
                        "place_of_supply_state_code": "29",
                        "taxable_amount": "100.00",
                    }
                ]
            },
        )
        assert tax_lines.status_code == 200, tax_lines.text

        posted = await client.post(
            f"/api/v1/finance/invoices/{invoice_id}/post", headers=auth
        )
        assert posted.status_code == 200, posted.text

        filing_period = date.today().strftime("%Y-%m")
        built = await client.post(
            "/api/v1/finance/gst/returns/build",
            headers=auth,
            json={
                "registration_id": registration_id,
                "return_type": "GSTR1",
                "filing_period": filing_period,
            },
        )
        assert built.status_code == 200, built.text
        gst_return_id = built.json()["id"]
        assert built.json()["summary"]["outward_supply"]["tax_total"] == "18.00"

        filed = await client.post(
            f"/api/v1/finance/gst/returns/{gst_return_id}/file",
            headers=auth,
            json={"acknowledgement_number": f"ACK-{marker}"},
        )
        assert filed.status_code == 200, filed.text
        assert filed.json()["status"] == "filed"

        e_invoice = await client.post(
            "/api/v1/finance/e-invoices/generate",
            headers=auth,
            json={"invoice_id": invoice_id},
        )
        assert e_invoice.status_code == 200, e_invoice.text
        assert e_invoice.json()["status"] == "generated"
        assert e_invoice.json()["irn"]

        waybill = await client.post(
            "/api/v1/finance/e-waybills",
            headers=auth,
            json={"invoice_id": invoice_id, "transport_mode": "road"},
        )
        assert waybill.status_code == 200, waybill.text
        assert waybill.json()["waybill_number"].startswith("EWB/")

        outbox = await client.get("/api/v1/finance/control/outbox", headers=auth, params={"size": 500})
        assert outbox.status_code == 200, outbox.text
        event_types = {row["event_type"] for row in outbox.json()["items"]}
        assert {"gst.return.filed", "einvoice.generated", "journal.posted"} <= event_types
    finally:
        async with AsyncSessionLocal() as db:
            if invoice_id:
                await db.execute(delete(EWaybill).where(EWaybill.invoice_id == UUID(invoice_id)))
                await db.execute(delete(EInvoice).where(EInvoice.invoice_id == UUID(invoice_id)))
                await db.execute(
                    delete(InvoiceTaxLine).where(InvoiceTaxLine.invoice_id == UUID(invoice_id))
                )
                await db.execute(delete(Invoice).where(Invoice.id == UUID(invoice_id)))
                journal_ids = list(
                    (
                        await db.scalars(
                            select(JournalEntry.id).where(
                                JournalEntry.reference == f"INV:{invoice_number}"
                            )
                        )
                    ).all()
                )
                if journal_ids:
                    await db.execute(
                        delete(JournalLine).where(JournalLine.journal_entry_id.in_(journal_ids))
                    )
                    await db.execute(delete(JournalEntry).where(JournalEntry.id.in_(journal_ids)))
            if gst_return_id:
                await db.execute(delete(GstReturn).where(GstReturn.id == UUID(gst_return_id)))
            if tax_code_id:
                await db.execute(delete(TaxCode).where(TaxCode.id == UUID(tax_code_id)))
            if registration_id:
                await db.execute(
                    delete(TaxRegistration).where(TaxRegistration.id == UUID(registration_id))
                )
            if account_ids:
                await db.execute(delete(Account).where(Account.id.in_([UUID(item) for item in account_ids])))
            await db.commit()


@pytest.mark.asyncio
async def test_bank_feed_import_is_idempotent_and_deduplicates(client, auth):
    marker = uuid4().hex[:8].upper()
    account = await client.post(
        "/api/v1/finance/bank-accounts",
        headers=auth,
        json={
            "name": f"Feed account {marker}",
            "bank_name": "Test Bank",
            "account_number": f"FEED-{marker}",
        },
    )
    assert account.status_code == 201, account.text
    bank_account_id = account.json()["id"]
    feed = await client.post(
        "/api/v1/finance/bank-feeds",
        headers=auth,
        json={
            "name": f"Feed {marker}",
            "provider": "csv",
            "bank_account_id": bank_account_id,
        },
    )
    assert feed.status_code == 201, feed.text
    feed_id = feed.json()["id"]

    content = (
        "date,amount,description,reference\n"
        f"2026-01-01,100.00,Opening receipt,{marker}-1\n"
        f"2026-01-02,-25.00,Vendor payment,{marker}-2\n"
    )
    first = await client.post(
        f"/api/v1/finance/bank-feeds/{feed_id}/import",
        headers={**auth, "Idempotency-Key": f"feed-{marker}"},
        files={"file": ("statement.csv", content, "text/csv")},
    )
    assert first.status_code == 200, first.text
    assert first.json()["imported_count"] == 2

    replay = await client.post(
        f"/api/v1/finance/bank-feeds/{feed_id}/import",
        headers={**auth, "Idempotency-Key": f"feed-{marker}"},
        files={"file": ("statement.csv", content, "text/csv")},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["status"] == "duplicate"

    async with AsyncSessionLocal() as db:
        count = int(
            (
                await db.scalar(
                    select(func.count())
                    .select_from(BankTransaction)
                    .where(BankTransaction.bank_account_id == UUID(bank_account_id))
                )
            )
            or 0
        )
        assert count == 2
        await db.execute(
            delete(BankTransaction).where(BankTransaction.bank_account_id == UUID(bank_account_id))
        )
        await db.execute(delete(BankAccount).where(BankAccount.id == UUID(bank_account_id)))
        await db.commit()


@pytest.mark.asyncio
async def test_dimensions_intercompany_and_budget_flows(client, auth):
    marker = uuid4().hex[:8].upper()
    entities = []
    for side in ("FROM", "TO"):
        response = await client.post(
            "/api/v1/finance/legal-entities",
            headers=auth,
            json={"code": f"LE-{marker}-{side}", "name": f"Legal entity {side} {marker}"},
        )
        assert response.status_code == 201, response.text
        entities.append(response.json()["id"])

    for path, suffix in (
        ("/finance/branches", "BR"),
        ("/finance/cost-centers", "CC"),
        ("/finance/departments", "DEP"),
    ):
        response = await client.post(
            f"/api/v1{path}",
            headers=auth,
            json={"code": f"{suffix}-{marker}", "name": f"{suffix} {marker}"},
        )
        assert response.status_code == 201, response.text

    intercompany = await client.post(
        "/api/v1/finance/intercompany",
        headers=auth,
        json={
            "from_entity_id": entities[0],
            "to_entity_id": entities[1],
            "transaction_date": date.today().isoformat(),
            "amount": "250.00",
            "description": f"Intercompany test {marker}",
        },
    )
    assert intercompany.status_code == 201, intercompany.text
    transaction_id = intercompany.json()["id"]
    assert intercompany.json()["number"].startswith("IC/")

    posted = await client.post(
        f"/api/v1/finance/intercompany/{transaction_id}/post", headers=auth
    )
    assert posted.status_code == 200, posted.text
    assert posted.json()["status"] == "posted"

    eliminated = await client.post(
        f"/api/v1/finance/intercompany/{transaction_id}/eliminate", headers=auth
    )
    assert eliminated.status_code == 200, eliminated.text
    assert eliminated.json()["status"] == "eliminated"

    budget = await client.post(
        "/api/v1/finance/budgets",
        headers=auth,
        json={
            "name": f"Budget {marker}",
            "start_date": date.today().replace(day=1).isoformat(),
            "end_date": (date.today().replace(day=28) + timedelta(days=4)).isoformat(),
        },
    )
    assert budget.status_code == 201, budget.text
    budget_id = budget.json()["id"]
    accounts = await client.get("/api/v1/finance/accounts", headers=auth)
    revenue_id = next(row["id"] for row in accounts.json()["items"] if row["code"] == "4000")
    line = await client.post(
        f"/api/v1/finance/budgets/{budget_id}/lines",
        headers=auth,
        json={
            "account_id": revenue_id,
            "period": date.today().strftime("%Y-%m"),
            "amount": "1000.00",
        },
    )
    assert line.status_code == 201, line.text
    activated = await client.post(
        f"/api/v1/finance/budgets/{budget_id}/activate", headers=auth
    )
    assert activated.status_code == 200, activated.text
    variance = await client.get(
        f"/api/v1/finance/budgets/{budget_id}/vs-actual", headers=auth
    )
    assert variance.status_code == 200, variance.text
    assert variance.json()[0]["budget"] == "1000.00"

    async with AsyncSessionLocal() as db:
        transaction = await db.scalar(
            select(IntercompanyTransaction).where(
                IntercompanyTransaction.id == UUID(transaction_id)
            )
        )
        journal_ids = [
            item
            for item in (transaction.journal_entry_id, transaction.elimination_journal_entry_id)
            if item
        ]
        if journal_ids:
            await db.execute(
                delete(JournalLine).where(JournalLine.journal_entry_id.in_(journal_ids))
            )
            await db.execute(delete(JournalEntry).where(JournalEntry.id.in_(journal_ids)))
        await db.execute(
            delete(IntercompanyTransaction).where(
                IntercompanyTransaction.id == UUID(transaction_id)
            )
        )
        await db.execute(delete(BudgetLine).where(BudgetLine.budget_id == UUID(budget_id)))
        await db.execute(delete(Budget).where(Budget.id == UUID(budget_id)))
        await db.commit()


@pytest.mark.asyncio
async def test_fixed_asset_impairment_and_write_off_post_balanced_journals(client, auth):
    marker = uuid4().hex[:8].upper()
    asset_account = await _account(client, auth, marker, "ASSET", "asset")
    accumulated_account = await _account(client, auth, marker, "ACCDEP", "asset")
    expense_account = await _account(client, auth, marker, "EXPAIR", "expense")
    accounts = await client.get("/api/v1/finance/accounts", headers=auth)
    credit_account = next(row["id"] for row in accounts.json()["items"] if row["code"] == "1010")

    asset = await client.post(
        "/api/v1/finance/assets",
        headers=auth,
        json={
            "asset_tag": f"ASSET-{marker}",
            "name": f"Compliance asset {marker}",
            "acquisition_date": date.today().isoformat(),
            "in_service_date": date.today().isoformat(),
            "cost": "1000.00",
            "useful_life_months": 60,
            "asset_account_id": asset_account,
            "accumulated_depreciation_account_id": accumulated_account,
            "depreciation_expense_account_id": expense_account,
        },
    )
    assert asset.status_code == 201, asset.text
    asset_id = asset.json()["id"]

    capitalized = await client.post(
        f"/api/v1/finance/assets/{asset_id}/capitalize",
        headers=auth,
        json={"credit_account_id": credit_account},
    )
    assert capitalized.status_code == 200, capitalized.text

    impaired = await client.post(
        f"/api/v1/finance/assets/{asset_id}/impair",
        headers=auth,
        json={
            "impairment_date": date.today().isoformat(),
            "impairment_loss": "100.00",
            "expense_account_id": expense_account,
            "reason": "Temporary decline in value",
        },
    )
    assert impaired.status_code == 200, impaired.text
    assert impaired.json()["status"] == "impaired"
    assert impaired.json()["impairment_loss"] == "100.00"

    written_off = await client.post(
        f"/api/v1/finance/assets/{asset_id}/write-off",
        headers=auth,
        json={"write_off_date": date.today().isoformat(), "reason": "Asset no longer in use"},
    )
    assert written_off.status_code == 200, written_off.text
    assert written_off.json()["status"] == "written_off"

    async with AsyncSessionLocal() as db:
        references = [
            f"IMP:ASSET-{marker}",
            f"WO:ASSET-{marker}",
            capitalized.json()["reference"],
        ]
        journals = list(
            (
                await db.scalars(
                    select(JournalEntry).where(JournalEntry.reference.in_(references))
                )
            ).all()
        )
        assert len(journals) == 3
        for journal in journals:
            lines = list(
                (
                    await db.scalars(
                        select(JournalLine).where(JournalLine.journal_entry_id == journal.id)
                    )
                ).all()
            )
            debit = sum((line.debit for line in lines), start=0)
            credit = sum((line.credit for line in lines), start=0)
            assert debit == credit
            await db.execute(
                delete(JournalLine).where(JournalLine.journal_entry_id == journal.id)
            )
        await db.execute(delete(JournalEntry).where(JournalEntry.id.in_([item.id for item in journals])))
        await db.execute(delete(FixedAsset).where(FixedAsset.id == UUID(asset_id)))
        await db.execute(
            delete(Account).where(
                Account.id.in_([UUID(asset_account), UUID(accumulated_account), UUID(expense_account)])
            )
        )
        await db.commit()
