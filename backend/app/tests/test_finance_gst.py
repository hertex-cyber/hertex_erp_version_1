from datetime import date
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, update

from app.db.session import AsyncSessionLocal
from app.modules.finance.models import (
    Account,
    GRNAccrual,
    Invoice,
    InvoiceTaxLine,
    JournalEntry,
    JournalLine,
    TaxCode,
    TaxRegistration,
)
from app.modules.inventory.models import Product, StockMove
from app.modules.pos.models import PosSale, PosSaleLine
from app.modules.procurement.models import (
    GoodsReceipt,
    PurchaseOrder,
    Vendor,
    VendorInvoice,
    VendorInvoiceTaxLine,
)
from app.modules.sales.models import DeliveryChallan, SalesOrder, SalesOrderLine


async def _create_account(client, auth, marker, code, account_type):
    response = await client.post(
        "/api/v1/finance/accounts",
        headers=auth,
        json={
            "code": f"GST-{marker}-{code}",
            "name": f"GST {code} {marker}",
            "account_type": account_type,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


@pytest.mark.asyncio
async def test_gst_line_snapshots_post_sales_and_vendor_tax(client, auth):
    marker = uuid4().hex[:8].upper()
    numeric_marker = str(uuid4().int % 10000).zfill(4)
    gstin = f"29ABCDE{numeric_marker}F1Z5"
    invoice_number = f"GST-AR-{marker}"
    invoice_numbers = []
    vendor_invoice_number = f"GST-AP-{marker}"
    account_ids = []
    tax_registration_id = None
    purchase_order_id = None
    vendor_id = None
    receipt_id = None
    grn_number = None
    product_ids = []
    sales_order_ids = []
    pos_sale_ids = []

    try:
        accounts = {}
        for component, account_type in (
            ("OUT-CGST", "liability"),
            ("OUT-SGST", "liability"),
            ("OUT-IGST", "liability"),
            ("IN-CGST", "asset"),
            ("IN-SGST", "asset"),
            ("IN-IGST", "asset"),
        ):
            accounts[component] = await _create_account(
                client, auth, marker, component, account_type
            )
            account_ids.append(accounts[component])

        registration = await client.post(
            "/api/v1/finance/tax/registrations",
            headers=auth,
            json={
                "legal_name": f"GST Test {marker}",
                "gstin": gstin,
                "state_code": "29",
                "is_default": False,
            },
        )
        assert registration.status_code == 201, registration.text
        tax_registration_id = registration.json()["id"]
        assert registration.json()["is_default"] is True

        mismatch = await client.post(
            "/api/v1/finance/tax/registrations",
            headers=auth,
            json={
                "legal_name": f"Invalid GST Test {marker}",
                "gstin": f"27ABCDE{numeric_marker}F1Z5",
                "state_code": "29",
            },
        )
        assert mismatch.status_code == 422, mismatch.text
        invalid_state = await client.post(
            "/api/v1/finance/tax/registrations",
            headers=auth,
            json={
                "legal_name": f"Invalid State GST Test {marker}",
                "gstin": f"00ABCDE{numeric_marker}F1Z5",
                "state_code": "00",
            },
        )
        assert invalid_state.status_code == 422, invalid_state.text

        code = await client.post(
            "/api/v1/finance/tax/codes",
            headers=auth,
            json={
                "code": f"GST18-{marker}",
                "description": "18% GST",
                "cgst_rate": "9",
                "sgst_rate": "9",
                "igst_rate": "18",
                "can_claim_itc": True,
                "output_cgst_account_id": accounts["OUT-CGST"],
                "output_sgst_account_id": accounts["OUT-SGST"],
                "output_igst_account_id": accounts["OUT-IGST"],
                "input_cgst_account_id": accounts["IN-CGST"],
                "input_sgst_account_id": accounts["IN-SGST"],
                "input_igst_account_id": accounts["IN-IGST"],
            },
        )
        assert code.status_code == 201, code.text
        tax_code_id = code.json()["id"]

        product = await client.post(
            "/api/v1/inventory/products",
            headers=auth,
            json={
                "sku": f"GST-{marker}",
                "name": f"GST Test Product {marker}",
                "sale_price": "100.00",
                "purchase_price": "50.00",
                "tax_code_id": tax_code_id,
            },
        )
        assert product.status_code == 201, product.text
        product_id = product.json()["id"]
        product_ids.append(product_id)

        unclassified_product = await client.post(
            "/api/v1/inventory/products",
            headers=auth,
            json={
                "sku": f"GST-NO-TAX-{marker}",
                "name": f"Unclassified GST Product {marker}",
                "sale_price": "100.00",
            },
        )
        assert unclassified_product.status_code == 201, unclassified_product.text
        unclassified_product_id = unclassified_product.json()["id"]
        product_ids.append(unclassified_product_id)

        sales_order = await client.post(
            "/api/v1/sales/orders",
            headers=auth,
            json={
                "order_date": date.today().isoformat(),
                "lines": [
                    {
                        "product_id": product_id,
                        "quantity": "1",
                        "unit_price": "100.00",
                    }
                ],
            },
        )
        assert sales_order.status_code == 201, sales_order.text
        sales_order_id = sales_order.json()["id"]
        sales_order_ids.append(sales_order_id)
        assert sales_order.json()["tax_registration_id"] == tax_registration_id
        assert sales_order.json()["place_of_supply_state_code"] == "29"
        assert sales_order.json()["tax"] == "18.00"

        fulfilled_order = await client.post(
            f"/api/v1/sales/orders/{sales_order_id}/fulfill",
            headers=auth,
        )
        assert fulfilled_order.status_code == 200, fulfilled_order.text
        assert fulfilled_order.json()["status"] == "fulfilled"

        missing_pos_classification = await client.post(
            "/api/v1/pos/checkout",
            headers=auth,
            json={
                "place_of_supply_state_code": "29",
                "lines": [{"product_id": unclassified_product_id, "quantity": "1"}],
            },
        )
        assert missing_pos_classification.status_code == 422, missing_pos_classification.text

        pos_sale = await client.post(
            "/api/v1/pos/checkout",
            headers=auth,
            json={
                "place_of_supply_state_code": "27",
                "lines": [{"product_id": product_id, "quantity": "1"}],
            },
        )
        assert pos_sale.status_code == 201, pos_sale.text
        pos_sale_ids.append(pos_sale.json()["id"])
        pos_order_id = pos_sale.json()["sales_order_id"]
        sales_order_ids.append(pos_order_id)
        assert pos_sale.json()["tax"] == "18.00"
        assert pos_sale.json()["total"] == "118.00"
        async with AsyncSessionLocal() as db:
            pos_invoice = await db.scalar(
                select(Invoice).where(Invoice.source_order_id == UUID(pos_order_id))
            )
            assert pos_invoice is not None
            invoice_numbers.append(pos_invoice.invoice_number)
            pos_invoice_line = await db.scalar(
                select(InvoiceTaxLine).where(InvoiceTaxLine.invoice_id == pos_invoice.id)
            )
            assert pos_invoice_line is not None
            assert pos_invoice_line.tax_type_snapshot == "taxable"
            assert pos_invoice_line.can_claim_itc_snapshot is True
            assert pos_invoice_line.igst_amount == 18

        invalid_rate = await client.post(
            "/api/v1/finance/tax/codes",
            headers=auth,
            json={
                "code": f"BAD-{marker}",
                "description": "Inconsistent rate",
                "cgst_rate": "9",
                "sgst_rate": "9",
                "igst_rate": "17",
                "can_claim_itc": False,
                "output_cgst_account_id": accounts["OUT-CGST"],
                "output_sgst_account_id": accounts["OUT-SGST"],
                "output_igst_account_id": accounts["OUT-IGST"],
            },
        )
        assert invalid_rate.status_code == 422, invalid_rate.text

        exempt = await client.post(
            "/api/v1/finance/tax/codes",
            headers=auth,
            json={
                "code": f"EXEMPT-{marker}",
                "description": "Exempt supply",
                "tax_type": "exempt",
                "can_claim_itc": False,
            },
        )
        assert exempt.status_code == 201, exempt.text
        exempt_code_id = exempt.json()["id"]

        invoice = await client.post(
            "/api/v1/finance/invoices",
            headers=auth,
            json={
                "issue_date": date.today().isoformat(),
                "subtotal": "250.00",
                "tax": "0.00",
                "total": "250.00",
            },
        )
        assert invoice.status_code == 201, invoice.text
        invoice_id = invoice.json()["id"]
        invoice_number = invoice.json()["invoice_number"]
        invoice_numbers.append(invoice_number)
        saved_lines = await client.put(
            f"/api/v1/finance/invoices/{invoice_id}/tax-lines",
            headers=auth,
            json={
                "lines": [
                    {
                        "tax_code_id": tax_code_id,
                        "registration_id": tax_registration_id,
                        "place_of_supply_state_code": "29",
                        "taxable_amount": "100.00",
                        "description": "Intra-state taxable line",
                    },
                    {
                        "tax_code_id": exempt_code_id,
                        "registration_id": tax_registration_id,
                        "place_of_supply_state_code": "29",
                        "taxable_amount": "50.00",
                        "description": "Exempt line",
                    },
                    {
                        "tax_code_id": tax_code_id,
                        "registration_id": tax_registration_id,
                        "place_of_supply_state_code": "27",
                        "taxable_amount": "100.00",
                        "description": "Inter-state taxable line",
                    },
                ]
            },
        )
        assert saved_lines.status_code == 200, saved_lines.text
        sales_components = {
            line["place_of_supply_state_code"]: line
            for line in saved_lines.json()
            if line["taxable_amount"] == "100.00"
        }
        intra = sales_components["29"]
        inter = sales_components["27"]
        assert (intra["tax_type_snapshot"], intra["can_claim_itc_snapshot"]) == (
            "taxable",
            True,
        )
        assert (intra["cgst_amount"], intra["sgst_amount"], intra["igst_amount"]) == (
            "9.00",
            "9.00",
            "0.00",
        )
        assert (inter["cgst_amount"], inter["sgst_amount"], inter["igst_amount"]) == (
            "0.00",
            "0.00",
            "18.00",
        )
        exempt_line = next(
            line for line in saved_lines.json()
            if line["tax_code_id"] == exempt_code_id
        )
        assert (exempt_line["tax_type_snapshot"], exempt_line["can_claim_itc_snapshot"]) == (
            "exempt",
            False,
        )

        missing_classification = await client.post(
            "/api/v1/finance/invoices",
            headers=auth,
            json={
                "issue_date": date.today().isoformat(),
                "subtotal": "10.00",
                "tax": "0.00",
                "total": "10.00",
            },
        )
        assert missing_classification.status_code == 201, missing_classification.text
        unclassified_id = missing_classification.json()["id"]
        invoice_numbers.append(missing_classification.json()["invoice_number"])
        unclassified_post = await client.post(
            f"/api/v1/finance/invoices/{unclassified_id}/post", headers=auth
        )
        assert unclassified_post.status_code == 422, unclassified_post.text

        posted = await client.post(
            f"/api/v1/finance/invoices/{invoice_id}/post", headers=auth
        )
        assert posted.status_code == 200, posted.text
        entry_response = await client.get(
            "/api/v1/finance/journal-entries",
            headers=auth,
            params={"q": invoice_number, "size": 200},
        )
        assert entry_response.status_code == 200, entry_response.text
        sales_entry = next(
            row for row in entry_response.json()["items"]
            if row["reference"] == f"INV:{invoice_number}"
        )
        sales_accounts = {
            line["account"]["code"]: (line["debit"], line["credit"])
            for line in sales_entry["lines"]
        }
        assert sales_accounts[f"GST-{marker}-OUT-CGST"] == ("0.00", "9.00")
        assert sales_accounts[f"GST-{marker}-OUT-SGST"] == ("0.00", "9.00")
        assert sales_accounts[f"GST-{marker}-OUT-IGST"] == ("0.00", "18.00")
        assert sales_accounts["1100"] == ("286.00", "0.00")
        assert sales_accounts["4000"] == ("0.00", "250.00")

        products = await client.get(
            "/api/v1/inventory/products", headers=auth, params={"size": 1}
        )
        product = products.json()["items"][0]
        vendor_response = await client.post(
            "/api/v1/procurement/vendors",
            headers=auth,
            json={"code": f"GST-V-{marker}", "name": f"GST vendor {marker}"},
        )
        assert vendor_response.status_code == 201, vendor_response.text
        vendor_id = UUID(vendor_response.json()["id"])
        po_response = await client.post(
            "/api/v1/procurement/purchase-orders",
            headers=auth,
            json={
                "vendor_id": str(vendor_id),
                "order_date": date.today().isoformat(),
                "lines": [
                    {"product_id": product["id"], "quantity": "2", "unit_price": "100.00"}
                ],
            },
        )
        assert po_response.status_code == 201, po_response.text
        purchase_order_id = UUID(po_response.json()["id"])
        approved_po = await client.post(
            f"/api/v1/procurement/purchase-orders/{purchase_order_id}/approve",
            headers=auth,
        )
        assert approved_po.status_code == 200, approved_po.text
        receipt_response = await client.post(
            f"/api/v1/procurement/purchase-orders/{purchase_order_id}/receive",
            headers=auth,
            json={
                "purchase_order_id": str(purchase_order_id),
                "received_date": date.today().isoformat(),
            },
        )
        assert receipt_response.status_code == 200, receipt_response.text
        receipt_id = UUID(receipt_response.json()["id"])
        grn_number = receipt_response.json()["grn_number"]

        vendor_invoice = await client.post(
            "/api/v1/procurement/vendor-invoices",
            headers=auth,
            json={
                "vendor_id": str(vendor_id),
                "purchase_order_id": str(purchase_order_id),
                "invoice_number": vendor_invoice_number,
                "issue_date": date.today().isoformat(),
                "amount": "200.00",
                "tax_amount": "0.00",
            },
        )
        assert vendor_invoice.status_code == 201, vendor_invoice.text
        vendor_invoice_id = vendor_invoice.json()["id"]
        vendor_tax_lines = await client.put(
            f"/api/v1/procurement/vendor-invoices/{vendor_invoice_id}/tax-lines",
            headers=auth,
            json={
                "lines": [
                    {
                        "tax_code_id": tax_code_id,
                        "registration_id": tax_registration_id,
                        "place_of_supply_state_code": "29",
                        "taxable_amount": "100.00",
                        "description": "Taxable purchase",
                    },
                    {
                        "tax_code_id": exempt_code_id,
                        "registration_id": tax_registration_id,
                        "place_of_supply_state_code": "29",
                        "taxable_amount": "100.00",
                        "description": "Exempt purchase",
                    },
                ]
            },
        )
        assert vendor_tax_lines.status_code == 200, vendor_tax_lines.text
        assert vendor_tax_lines.json()[0]["cgst_amount"] == "9.00"
        assert (
            vendor_tax_lines.json()[0]["tax_type_snapshot"],
            vendor_tax_lines.json()[0]["can_claim_itc_snapshot"],
        ) == ("taxable", True)
        approved_bill = await client.post(
            f"/api/v1/procurement/vendor-invoices/{vendor_invoice_id}/approve",
            headers=auth,
        )
        assert approved_bill.status_code == 200, approved_bill.text
        assert approved_bill.json()["tax_amount"] == "18.00"

        vendor_entries = await client.get(
            "/api/v1/finance/journal-entries",
            headers=auth,
            params={"q": vendor_invoice_number, "size": 200},
        )
        assert vendor_entries.status_code == 200, vendor_entries.text
        vendor_entry = next(
            row for row in vendor_entries.json()["items"]
            if row["reference"] == f"VINV:{vendor_invoice_number}"
        )
        vendor_accounts = {
            line["account"]["code"]: (line["debit"], line["credit"])
            for line in vendor_entry["lines"]
        }
        assert vendor_accounts[f"GST-{marker}-IN-CGST"] == ("9.00", "0.00")
        assert vendor_accounts[f"GST-{marker}-IN-SGST"] == ("9.00", "0.00")
        assert vendor_accounts["2000"] == ("0.00", "218.00")
        assert vendor_accounts["2100"] == ("200.00", "0.00")
    finally:
        async with AsyncSessionLocal() as db:
            if pos_sale_ids:
                await db.execute(delete(PosSaleLine).where(PosSaleLine.sale_id.in_(
                    [UUID(item) for item in pos_sale_ids]
                )))
                await db.execute(
                    delete(PosSale).where(PosSale.id.in_([UUID(item) for item in pos_sale_ids]))
                )
            if sales_order_ids:
                order_ids = [UUID(item) for item in sales_order_ids]
                await db.execute(
                    delete(DeliveryChallan).where(DeliveryChallan.order_id.in_(order_ids))
                )
                await db.execute(
                    delete(StockMove).where(StockMove.product_id.in_(
                        [UUID(item) for item in product_ids]
                    ))
                )
                await db.execute(
                    delete(SalesOrderLine).where(SalesOrderLine.order_id.in_(order_ids))
                )
            registration = await db.scalar(
                select(TaxRegistration).where(TaxRegistration.gstin == gstin)
            )
            tax_codes = list(
                (
                    await db.scalars(
                        select(TaxCode).where(TaxCode.code.in_([f"GST18-{marker}", f"EXEMPT-{marker}"]))
                    )
                ).all()
            )
            invoice_rows = list(
                (
                    await db.scalars(
                        select(Invoice).where(
                            Invoice.invoice_number.in_(invoice_numbers)
                            | Invoice.source_order_id.in_(
                                [UUID(item) for item in sales_order_ids]
                            )
                        )
                    )
                ).all()
            ) if invoice_numbers or sales_order_ids else []
            invoice_numbers.extend(item.invoice_number for item in invoice_rows)
            if invoice_rows:
                await db.execute(
                    delete(InvoiceTaxLine).where(
                        InvoiceTaxLine.invoice_id.in_([item.id for item in invoice_rows])
                    )
                )
                await db.execute(delete(Invoice).where(Invoice.id.in_([item.id for item in invoice_rows])))

            vendor_invoice = await db.scalar(
                select(VendorInvoice).where(
                    VendorInvoice.invoice_number == vendor_invoice_number
                )
            )
            if vendor_invoice:
                await db.execute(
                    delete(VendorInvoiceTaxLine).where(
                        VendorInvoiceTaxLine.invoice_id == vendor_invoice.id
                    )
                )
                await db.execute(
                    delete(GRNAccrual).where(
                        GRNAccrual.cleared_by_invoice_id == vendor_invoice.id
                    )
                )
                await db.execute(
                    delete(VendorInvoice).where(VendorInvoice.id == vendor_invoice.id)
                )
            if receipt_id:
                await db.execute(
                    delete(GRNAccrual).where(GRNAccrual.goods_receipt_id == receipt_id)
                )
                await db.execute(
                    update(GoodsReceipt)
                    .where(GoodsReceipt.id == receipt_id)
                    .values(journal_entry_id=None)
                )
                await db.execute(delete(GoodsReceipt).where(GoodsReceipt.id == receipt_id))
            if purchase_order_id:
                await db.execute(
                    delete(PurchaseOrder).where(PurchaseOrder.id == purchase_order_id)
                )
            if vendor_id:
                await db.execute(delete(Vendor).where(Vendor.id == vendor_id))

            if sales_order_ids:
                await db.execute(
                    delete(SalesOrder).where(
                        SalesOrder.id.in_([UUID(item) for item in sales_order_ids])
                    )
                )
            if product_ids:
                await db.execute(
                    delete(Product).where(Product.id.in_([UUID(item) for item in product_ids]))
                )

            journal_references = [
                *(f"INV:{number}" for number in invoice_numbers),
                f"VINV:{vendor_invoice_number}",
            ]
            if grn_number:
                journal_references.append(f"GRN:{grn_number}")
            journal_ids = list(
                (
                    await db.scalars(
                        select(JournalEntry.id).where(
                            JournalEntry.reference.in_(journal_references)
                        )
                    )
                ).all()
            )
            if journal_ids:
                await db.execute(
                    delete(JournalLine).where(JournalLine.journal_entry_id.in_(journal_ids))
                )
                await db.execute(
                    delete(JournalEntry).where(JournalEntry.id.in_(journal_ids))
                )
            if tax_codes:
                for tax_code in tax_codes:
                    await db.delete(tax_code)
            if registration:
                await db.delete(registration)
            if account_ids:
                await db.execute(
                    delete(Account).where(
                        Account.id.in_([UUID(account_id) for account_id in account_ids])
                    )
                )
            await db.commit()
