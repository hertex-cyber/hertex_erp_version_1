"""Tally XML chart-of-accounts importer.

Supports the ``<LEDGER>`` records exported by Tally ERP 9 / Tally Prime
(``PARENT`` group and ``OPENINGBALANCE``).  Importing is idempotent: ledgers are
matched by name and only missing fields are updated.
"""

import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationError
from app.core.numbering import next_number
from app.modules.finance.models import Account, JournalEntry, JournalLine
from app.modules.finance.schemas import TallyImportResult
from app.modules.finance.service import ensure_period_open
from app.modules.identity.models import User

_TYPE_RANGES = {
    "asset": 1000,
    "liability": 2000,
    "equity": 3000,
    "income": 4000,
    "expense": 5000,
}

_PARENT_TYPES = (
    ("loans (liability)", "liability"),
    ("loans & advances (asset)", "asset"),
    ("sundry creditors", "liability"),
    ("sundry debtors", "asset"),
    ("cash-in-hand", "asset"),
    ("bank accounts", "asset"),
    ("bank od", "liability"),
    ("fixed assets", "asset"),
    ("current assets", "asset"),
    ("current liabilities", "liability"),
    ("duties & taxes", "liability"),
    ("provisions", "liability"),
    ("reserves & surplus", "equity"),
    ("capital account", "equity"),
    ("sales accounts", "income"),
    ("direct incomes", "income"),
    ("indirect incomes", "income"),
    ("purchase accounts", "expense"),
    ("direct expenses", "expense"),
    ("indirect expenses", "expense"),
    ("stock-in-hand", "asset"),
    ("deposits", "asset"),
    ("secured loans", "liability"),
    ("unsecured loans", "liability"),
    ("suspense", "liability"),
)


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1].upper()


def _text(element: ET.Element, name: str) -> str:
    for child in element:
        if _tag(child) == name:
            return (child.text or "").strip()
    return ""


def _classify(parent: str) -> str:
    key = " ".join(parent.lower().split())
    for prefix, account_type in _PARENT_TYPES:
        if key.startswith(prefix):
            return account_type
    return "asset"


def _parse_amount(raw: str) -> Optional[Decimal]:
    value = raw.strip().replace(",", "").replace("₹", "").replace("Rs.", "").strip()
    if not value:
        return None
    sign = Decimal("1")
    if value.lower().endswith("cr"):
        value, sign = value[:-2].strip(), Decimal("-1")
    elif value.lower().endswith("dr"):
        value = value[:-2].strip()
    try:
        return Decimal(value) * sign
    except InvalidOperation as exc:
        raise ValidationError(f"Invalid Tally amount: {raw!r}") from exc


def _next_code(used: set[str], account_type: str) -> str:
    candidate = _TYPE_RANGES.get(account_type, 1000)
    while str(candidate) in used:
        candidate += 1
    code = str(candidate)
    used.add(code)
    return code


def _parse_ledgers(content: bytes) -> list[dict]:
    upper = content.upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise ValidationError("Tally file must not contain a DTD or entity declarations")
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValidationError(f"Malformed Tally XML: {exc}") from exc

    ledgers: list[dict] = []
    seen: set[str] = set()
    for element in root.iter():
        if _tag(element) != "LEDGER":
            continue
        name = (element.get("NAME") or _text(element, "NAME")).strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        parent = _text(element, "PARENT")
        ledgers.append(
            {
                "name": name,
                "parent": parent,
                "account_type": _classify(parent),
                "opening_balance": _parse_amount(_text(element, "OPENINGBALANCE")),
            }
        )
    return ledgers


async def import_tally(
    db: AsyncSession,
    user: User,
    content: bytes,
    *,
    opening_date: date,
    post_opening_balance: bool = True,
) -> TallyImportResult:
    if not content.strip():
        raise ValidationError("Empty Tally file")
    ledgers = _parse_ledgers(content)
    if not ledgers:
        raise ValidationError("No <LEDGER> records found in the Tally file")

    stmt = select(Account)
    if not user.is_superuser and user.tenant_id:
        stmt = stmt.where(Account.tenant_id == user.tenant_id)
    existing = {account.name.lower(): account for account in (await db.scalars(stmt)).all()}
    used_codes = {account.code for account in existing.values()}

    created = 0
    updated = 0
    imported: list[tuple[Account, Decimal]] = []
    warnings: list[str] = []
    for ledger in ledgers:
        key = ledger["name"].lower()
        opening = ledger["opening_balance"] or Decimal("0")
        account = existing.get(key)
        if account is None:
            account = Account(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                code=_next_code(used_codes, ledger["account_type"]),
                name=ledger["name"],
                account_type=ledger["account_type"],
                description=f"Imported from Tally (group: {ledger['parent'] or 'unmapped'})",
            )
            db.add(account)
            await db.flush()
            existing[key] = account
            created += 1
        else:
            changed = False
            if account.account_type != ledger["account_type"] and not account.is_system:
                account.account_type = ledger["account_type"]
                changed = True
            if not account.description:
                account.description = f"Imported from Tally (group: {ledger['parent'] or 'unmapped'})"
                changed = True
            if changed:
                updated += 1
        if opening:
            imported.append((account, opening))

    result = TallyImportResult(
        accounts_seen=len(ledgers),
        accounts_created=created,
        accounts_updated=updated,
        opening_balance_posted=False,
        warnings=warnings,
    )
    if not post_opening_balance or not imported:
        return result

    total_debit = sum((amount for _, amount in imported if amount > 0), Decimal("0"))
    total_credit = sum((-amount for _, amount in imported if amount < 0), Decimal("0"))
    if total_debit != total_credit:
        result.warnings.append(
            f"Opening balances are unbalanced (debit {total_debit} / credit {total_credit}); "
            "journal entry was not posted"
        )
        return result
    if total_debit <= 0:
        return result

    await ensure_period_open(db, user.tenant_id, opening_date)

    reference = "TALLY:OPENING"
    existing_entry = await db.scalar(
        select(JournalEntry.id).where(
            JournalEntry.reference == reference, JournalEntry.status == "posted"
        )
    )
    if existing_entry:
        result.warnings.append(
            "A Tally opening-balance journal already exists; skipped posting"
        )
        return result

    entry = JournalEntry(
        tenant_id=user.tenant_id,
        created_by_id=user.id,
        entry_number=await next_number(db, JournalEntry, "entry_number", "JE", user.tenant_id),
        entry_date=opening_date,
        reference=reference,
        memo="Tally opening balances",
        status="posted",
        posted_by_id=user.id,
        posted_at=datetime.now(timezone.utc),
    )
    db.add(entry)
    await db.flush()
    for account, amount in imported:
        db.add(
            JournalLine(
                tenant_id=user.tenant_id,
                created_by_id=user.id,
                journal_entry_id=entry.id,
                account_id=account.id,
                description="Tally opening balance",
                debit=amount if amount > 0 else Decimal("0"),
                credit=-amount if amount < 0 else Decimal("0"),
            )
        )
    await db.flush()
    result.opening_balance_posted = True
    result.journal_entry_id = entry.id
    return result
