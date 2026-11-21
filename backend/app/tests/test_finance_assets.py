import calendar
from datetime import date
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_fixed_asset_capitalization_depreciation_and_disposal(client, auth):
    marker = uuid4().hex[:8].upper()
    accounts_response = await client.get(
        "/api/v1/finance/accounts", headers=auth, params={"size": 200}
    )
    assert accounts_response.status_code == 200, accounts_response.text
    accounts = {row["code"]: row for row in accounts_response.json()["items"]}

    month = date.today().replace(day=1)
    if month.month == 1:
        prior_month = date(month.year - 1, 12, 1)
    else:
        prior_month = date(month.year, month.month - 1, 1)
    in_service = prior_month.replace(day=15)
    period_end = date(
        month.year,
        month.month,
        calendar.monthrange(month.year, month.month)[1],
    )
    asset = await client.post(
        "/api/v1/finance/assets",
        headers=auth,
        json={
            "asset_tag": f"FA-{marker}",
            "name": f"Test asset {marker}",
            "acquisition_date": in_service.isoformat(),
            "in_service_date": in_service.isoformat(),
            "cost": "1200.00",
            "residual_value": "0.00",
            "useful_life_months": 12,
            "asset_account_id": accounts["1200"]["id"],
            "accumulated_depreciation_account_id": accounts["1200"]["id"],
            "depreciation_expense_account_id": accounts["5000"]["id"],
        },
    )
    assert asset.status_code == 201, asset.text
    asset_id = asset.json()["id"]

    capitalization = await client.post(
        f"/api/v1/finance/assets/{asset_id}/capitalize",
        headers=auth,
        json={"credit_account_id": accounts["2000"]["id"]},
    )
    assert capitalization.status_code == 200, capitalization.text
    assert capitalization.json()["status"] == "posted"
    assert capitalization.json()["source_document_type"] == "fixed_asset"

    depreciation = await client.post(
        "/api/v1/finance/assets/depreciation/run",
        headers=auth,
        json={"period_end": period_end.isoformat()},
    )
    assert depreciation.status_code == 200, depreciation.text
    assert depreciation.json()["created_count"] == 1
    assert str(depreciation.json()["depreciations"][0]["amount"]) == "100.00"

    replay = await client.post(
        "/api/v1/finance/assets/depreciation/run",
        headers=auth,
        json={"period_end": period_end.isoformat()},
    )
    assert replay.status_code == 200, replay.text
    assert replay.json()["created_count"] == 0
    assert replay.json()["skipped_count"] == 1

    disposal = await client.post(
        f"/api/v1/finance/assets/{asset_id}/dispose",
        headers=auth,
        json={
            "disposed_on": period_end.isoformat(),
            "proceeds": "1050.00",
            "proceeds_account_id": accounts["1010"]["id"],
            "gain_loss_account_id": accounts["5000"]["id"],
        },
    )
    assert disposal.status_code == 200, disposal.text
    lines = disposal.json()["lines"]
    assert sum(float(line["debit"]) for line in lines) == pytest.approx(
        sum(float(line["credit"]) for line in lines)
    )
    current_asset = await client.get(f"/api/v1/finance/assets/{asset_id}", headers=auth)
    assert current_asset.status_code == 200, current_asset.text
    assert current_asset.json()["status"] == "disposed"
    assert current_asset.json()["accumulated_depreciation"] == "100.00"
