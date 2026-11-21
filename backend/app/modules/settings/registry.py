"""Settings registry — the allow-list that *is* the configuration schema.

Code declares what may be configured; the database only stores values. A write to
a key that is not declared here is rejected (S-REG-1), which removes the entire
class of "a typo silently changed tax behaviour" bugs.

Each descriptor carries: type, default, declared scope order, validation,
grouping for the UI, and the governance flags (``critical``, ``deploy_only``,
``immutable_after``, ``data_impact``).

Scope order is per-setting, not a global rank: a policy setting declares
``("tenant",)`` (a user cannot override tax policy), a preference declares
``("user", "tenant")`` (the user wins).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from app.core.exceptions import ValidationError

GST_STATE_CODES = tuple(
    [f"{code:02d}" for code in range(1, 39)] + ["96", "97", "99"]
)

GSTIN_REGEX = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"

DATA_IMPACTS = ("none", "dpdp", "retention", "residency", "statutory")


def normalize_data_impact(value: str | None) -> str:
    normalized = (value or "none").strip().lower() or "none"
    if normalized not in DATA_IMPACTS:
        raise ValueError(f"Unsupported data_impact '{value}'")
    return normalized


@dataclass(frozen=True)
class SettingDescriptor:
    key: str
    type: str
    default: Any
    module: str
    label: str
    help: str = ""
    scopes: tuple[str, ...] = ("tenant",)
    choices: tuple[str, ...] | None = None
    min: float | None = None
    max: float | None = None
    regex: str | None = None
    critical: bool = False
    deploy_only: bool = False
    immutable_after: str | None = None
    data_impact: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    is_secret: bool = False
    env_var: str | None = None
    json_schema: dict | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data_impact", normalize_data_impact(self.data_impact))


def _d(**kwargs) -> SettingDescriptor:
    return SettingDescriptor(**kwargs)


def _secret(key: str, label: str, *, aliases: tuple[str, ...] = ()) -> SettingDescriptor:
    return _d(
        key=key,
        type="secret",
        default="",
        module="integrations",
        label=label,
        help="Encrypted integration credential; writes are masked and audited.",
        scopes=("tenant",),
        critical=True,
        data_impact="dpdp",
        aliases=aliases,
        is_secret=True,
    )


DESCRIPTORS: tuple[SettingDescriptor, ...] = (
    # ------------------------------------------------------------- company
    _d(
        key="company.profile.name",
        type="string",
        default="",
        module="company",
        label="Trading name",
        help="Appears on invoices and PDF headers.",
        critical=True,
    ),
    _d(
        key="company.profile.legal_name",
        type="string",
        default="",
        module="company",
        label="Registered legal name",
        critical=True,
    ),
    _d(
        key="company.profile.address",
        type="string",
        default="",
        module="company",
        label="Registered address",
        help="Rule 46(a) requires the supplier address on every tax invoice.",
        critical=True,
    ),
    _d(key="company.profile.phone", type="string", default="", module="company", label="Phone"),
    _d(
        key="company.profile.email",
        type="string",
        default="",
        module="company",
        label="Billing email",
        critical=True,
    ),
    _d(
        key="company.profile.gstin",
        type="string",
        default="",
        module="company",
        label="GSTIN",
        regex=GSTIN_REGEX,
        critical=True,
        data_impact="statutory",
    ),
    _d(
        key="company.profile.pan",
        type="string",
        default="",
        module="company",
        label="PAN",
        regex=r"^[A-Z]{5}[0-9]{4}[A-Z]$",
        critical=True,
    ),
    _d(key="company.profile.cin", type="string", default="", module="company", label="CIN"),
    _d(
        key="company.profile.state_code",
        type="enum",
        default="29",
        module="company",
        label="GST state code",
        help="Drives intra-state (CGST+SGST) vs inter-state (IGST) splitting.",
        choices=GST_STATE_CODES,
        critical=True,
        immutable_after="finance_first_posting",
    ),
    # -------------------------------------------------------- localization
    _d(
        key="company.locale.currency",
        type="currency",
        default="INR",
        module="localization",
        label="Base currency",
        critical=True,
        immutable_after="finance_first_posting",
    ),
    _d(
        key="company.locale.timezone",
        type="string",
        default="Asia/Kolkata",
        module="localization",
        label="Timezone",
        scopes=("tenant", "user"),
    ),
    _d(
        key="company.locale.date_format",
        type="enum",
        default="DD-MM-YYYY",
        module="localization",
        label="Date format",
        choices=("DD-MM-YYYY", "DD/MM/YYYY", "YYYY-MM-DD", "MM/DD/YYYY"),
        scopes=("tenant", "user"),
    ),
    _d(
        key="company.locale.number_format",
        type="enum",
        default="indian",
        module="localization",
        label="Number grouping",
        choices=("indian", "western"),
        scopes=("tenant", "user"),
    ),
    _d(
        key="company.fiscal.start_month",
        type="int",
        default=4,
        module="localization",
        label="Fiscal year start month",
        help="Numbering series and financial periods reset at this month.",
        min=1,
        max=12,
        critical=True,
        immutable_after="fiscal_closed",
    ),
    # ------------------------------------------------------------- finance
    _d(
        key="finance.invoice.due_days",
        type="int",
        default=15,
        module="finance",
        label="Default invoice due days",
        min=0,
        max=365,
    ),
    _d(
        key="finance.invoice.rounding",
        type="enum",
        default="document",
        module="finance",
        label="GST rounding level",
        choices=("line", "document"),
        critical=True,
    ),
    _d(
        key="finance.tax.tracking_mode",
        type="enum",
        default="separate",
        module="finance",
        label="Tax tracking accounts",
        choices=("single", "separate"),
        help="Separate = output and input tax tracked in their own accounts.",
        critical=True,
        immutable_after="finance_first_posting",
    ),
    _d(
        key="finance.tax.override_allowed",
        type="bool",
        default=False,
        module="finance",
        label="Allow manual tax override",
        critical=True,
    ),
    _d(
        key="finance.journal.manual_allowed",
        type="bool",
        default=True,
        module="finance",
        label="Allow manual journal entries",
        critical=True,
    ),
    _d(
        key="finance.period.lock_policy",
        type="enum",
        default="hard",
        module="finance",
        label="Period lock policy",
        choices=("hard", "soft"),
        critical=True,
    ),
    _d(
        key="finance.default_currency_rate_source",
        type="enum",
        default="manual",
        module="finance",
        label="FX rate source",
        choices=("manual", "rbi", "provider"),
    ),
    _d(
        key="finance.bank.match.date_tolerance_days",
        type="int",
        default=14,
        module="finance",
        label="Bank match date tolerance (days)",
        help="Maximum distance between a bank transaction date and a posted journal date.",
        min=0,
        max=365,
        critical=True,
        scopes=("tenant",),
    ),
    _d(
        key="finance.bank.match.amount_mode",
        type="enum",
        default="signed",
        module="finance",
        label="Bank match amount mode",
        help="Signed requires identical signed amounts; absolute ignores sign.",
        choices=("signed", "absolute"),
        critical=True,
        scopes=("tenant",),
    ),
    _d(
        key="finance.bank.match.reference_required",
        type="bool",
        default=False,
        module="finance",
        label="Require matching bank reference",
        critical=True,
        scopes=("tenant",),
    ),
    _d(
        key="finance.bank.match.max_candidates",
        type="int",
        default=20,
        module="finance",
        label="Maximum bank match suggestions",
        min=1,
        max=100,
        scopes=("tenant",),
    ),
    # --------------------------------------------------------------- sales
    _d(
        key="sales.quote.validity_days",
        type="int",
        default=14,
        module="sales",
        label="Quotation validity (days)",
        min=1,
        max=365,
    ),
    _d(
        key="sales.price.tax_inclusive",
        type="bool",
        default=False,
        module="sales",
        label="Prices include tax",
        critical=True,
    ),
    _d(
        key="sales.discount.level",
        type="enum",
        default="line",
        module="sales",
        label="Discount application level",
        choices=("none", "line", "document", "both"),
        critical=True,
    ),
    _d(
        key="sales.credit_limit.enforced",
        type="bool",
        default=True,
        module="sales",
        label="Enforce customer credit limits",
        critical=True,
    ),
    # --------------------------------------------------------- procurement
    _d(
        key="procurement.approval.threshold",
        type="decimal",
        default=50000,
        module="procurement",
        label="PO approval threshold",
        help="Purchase orders above this value need an approver.",
        min=0,
        critical=True,
    ),
    _d(
        key="procurement.match.tolerance_pct",
        type="decimal",
        default=0,
        module="procurement",
        label="3-way match tolerance (%)",
        min=0,
        max=5,
        critical=True,
    ),
    # ----------------------------------------------------------- inventory
    _d(
        key="inventory.valuation_method",
        type="enum",
        default="weighted_avg",
        module="inventory",
        label="Valuation method",
        choices=("fifo", "weighted_avg"),
        critical=True,
        immutable_after="stock_exists",
    ),
    _d(
        key="inventory.negative_stock_allowed",
        type="bool",
        default=False,
        module="inventory",
        label="Allow negative stock",
        critical=True,
    ),
    # ---------------------------------------------------------------- hr
    _d(
        key="hr.payroll.cutoff_day",
        type="int",
        default=25,
        module="hr",
        label="Payroll cut-off day",
        min=1,
        max=31,
        critical=True,
    ),
    _d(
        key="hr.statutory.pf_rate",
        type="decimal",
        default=12,
        module="hr",
        label="PF rate (%)",
        min=0,
        max=25,
        critical=True,
        data_impact="statutory",
    ),
    _d(
        key="hr.statutory.esi_rate",
        type="decimal",
        default=0.75,
        module="hr",
        label="ESI rate (%)",
        min=0,
        max=10,
        critical=True,
        data_impact="statutory",
    ),
    _d(
        key="hr.statutory.pt_state",
        type="string",
        default="",
        module="hr",
        label="Professional tax state",
        critical=True,
    ),
    # --------------------------------------------------------------- pos
    _d(
        key="pos.offline.block_size",
        type="int",
        default=100,
        module="pos",
        label="Offline number block size",
        help="Numbers reserved per device so offline bills stay unique.",
        min=20,
        max=500,
    ),
    _d(key="pos.receipt.footer_text", type="string", default="", module="pos", label="Receipt footer"),
    # ----------------------------------------------------------- support
    _d(
        key="support.sla.first_response_hours",
        type="int",
        default=4,
        module="support",
        label="First response SLA (hours)",
        min=1,
        max=168,
    ),
    _d(
        key="support.sla.resolution_hours",
        type="int",
        default=48,
        module="support",
        label="Resolution SLA (hours)",
        min=1,
        max=720,
    ),
    _d(
        key="support.business_hours",
        type="json",
        default={"start": "09:00", "end": "18:00", "days": [1, 2, 3, 4, 5, 6]},
        module="support",
        label="Business hours",
        json_schema={
            "type": "object",
            "required": ["start", "end", "days"],
            "properties": {
                "start": {"type": "string", "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"},
                "end": {"type": "string", "pattern": r"^([01]\d|2[0-3]):[0-5]\d$"},
                "days": {
                    "type": "array",
                    "items": {"type": "integer", "minimum": 1, "maximum": 7},
                },
            },
        },
    ),
    # ---------------------------------------------------------- security
    _d(
        key="security.session.timeout_minutes",
        type="int",
        default=60,
        module="security",
        label="Session timeout (minutes)",
        min=5,
        max=1440,
        critical=True,
        deploy_only=True,
        env_var="HERTEX_SESSION_TIMEOUT_MINUTES",
    ),
    _d(
        key="security.mfa.required_for_admins",
        type="bool",
        default=False,
        module="security",
        label="Require MFA for administrators",
        critical=True,
        deploy_only=True,
        env_var="HERTEX_REQUIRE_MFA_FOR_ADMINS",
    ),
    _d(
        key="security.password.min_length",
        type="int",
        default=12,
        module="security",
        label="Minimum password length",
        min=8,
        max=72,
        critical=True,
        deploy_only=True,
        env_var="PASSWORD_MIN_LENGTH",
    ),
    # ------------------------------------------------------ notifications
    _d(
        key="notifications.email.from_address",
        type="string",
        default="",
        module="notifications",
        label="From address",
    ),
    _d(
        key="notifications.email.reply_to",
        type="string",
        default="",
        module="notifications",
        label="Reply-to address",
    ),
    # ---------------------------------------------------------- documents
    _d(
        key="documents.pdf.show_gstin",
        type="bool",
        default=True,
        module="documents",
        label="Show GSTIN on PDFs",
    ),
    _d(
        key="documents.pdf.terms_text",
        type="string",
        default="",
        module="documents",
        label="Terms & conditions",
    ),
    _d(
        key="documents.pdf.signature_required",
        type="bool",
        default=False,
        module="documents",
        label="Require signature block",
    ),
    # ----------------------------------------------------------- features
    _d(
        key="features.module.projects.enabled",
        type="bool",
        default=True,
        module="features",
        label="Projects module",
        help="Hides the module in navigation; the API stays available.",
        scopes=("tenant", "user"),
    ),
    _d(
        key="features.module.pos.enabled",
        type="bool",
        default=True,
        module="features",
        label="POS module",
        scopes=("tenant", "user"),
    ),
    _d(
        key="features.module.marketing.enabled",
        type="bool",
        default=True,
        module="features",
        label="Marketing module",
        scopes=("tenant", "user"),
    ),
    _d(
        key="features.module.support.enabled",
        type="bool",
        default=True,
        module="features",
        label="Support module",
        scopes=("tenant", "user"),
    ),
    _d(
        key="features.numbering.engine",
        type="bool",
        default=True,
        module="features",
        label="Numbering engine (v2)",
        help="Rollout switch for the atomic numbering engine.",
    ),
    _d(
        key="settings.sequence.branch_fallback",
        type="bool",
        default=False,
        module="features",
        label="Allow tenant-wide series fallback",
        help="When off, a branch without its own series blocks document creation.",
    ),
    _secret(
        "gst_portal.client_id",
        "GST portal client ID",
        aliases=("integrations.external.gst_portal.client_id",),
    ),
    _secret(
        "gst_portal.client_secret",
        "GST portal client secret",
        aliases=("integrations.external.gst_portal.client_secret",),
    ),
    _secret(
        "e_invoice_portal.auth_token",
        "E-invoice portal auth token",
        aliases=("integrations.external.e_invoice_portal.auth_token",),
    ),
    _secret(
        "e_invoice_portal.client_id",
        "E-invoice portal client ID",
        aliases=("integrations.external.e_invoice_portal.client_id",),
    ),
    _secret(
        "e_invoice_portal.client_secret",
        "E-invoice portal client secret",
        aliases=("integrations.external.e_invoice_portal.client_secret",),
    ),
    _secret(
        "bank_feed.api_key",
        "Bank feed API key",
        aliases=("integrations.external.bank_feed.api_key",),
    ),
    _secret(
        "bank_feed.api_secret",
        "Bank feed API secret",
        aliases=("integrations.external.bank_feed.api_secret",),
    ),
    _secret(
        "payment_gateway.api_key",
        "Payment gateway API key",
        aliases=("integrations.external.payment_gateway.api_key",),
    ),
    _secret(
        "payment_gateway.webhook_secret",
        "Payment gateway webhook secret",
        aliases=("integrations.external.payment_gateway.webhook_secret",),
    ),
    _secret(
        "ocr.api_key",
        "OCR API key",
        aliases=("integrations.external.ocr.api_key", "integrations.ocr.api_key"),
    ),
)

BY_KEY: dict[str, SettingDescriptor] = {descriptor.key: descriptor for descriptor in DESCRIPTORS}

# Legacy aggregate keys from the original seed, mapped onto the new catalogue.
ALIASES: dict[str, str] = {"company.profile": "company.profile.name"}
for _descriptor in DESCRIPTORS:
    for _alias in _descriptor.aliases:
        ALIASES.setdefault(_alias, _descriptor.key)


def get_descriptor(key: str) -> Optional[SettingDescriptor]:
    descriptor = BY_KEY.get(key)
    if descriptor is not None:
        return descriptor
    mapped = ALIASES.get(key)
    return BY_KEY.get(mapped) if mapped else None


def secret_descriptors() -> list[SettingDescriptor]:
    return [descriptor for descriptor in DESCRIPTORS if descriptor.is_secret]


def is_secret_key(key: str) -> bool:
    descriptor = get_descriptor(key)
    return bool(descriptor and descriptor.is_secret)


def validate_secret_key(key: str) -> SettingDescriptor:
    descriptor = get_descriptor(key)
    if descriptor is None or not descriptor.is_secret:
        raise ValidationError(
            f"Unknown secret key '{key}'", code="settings.unknown_secret_key"
        )
    return descriptor


def keys_for_module(module: str) -> list[str]:
    return [descriptor.key for descriptor in DESCRIPTORS if descriptor.module == module]


def modules() -> list[str]:
    seen: list[str] = []
    for descriptor in DESCRIPTORS:
        if descriptor.module not in seen:
            seen.append(descriptor.module)
    return seen


def sample_value(descriptor: SettingDescriptor) -> Any:
    """A representative value for previews and tests."""
    if descriptor.type in {"int", "duration"}:
        return descriptor.default if isinstance(descriptor.default, int) else 1
    if descriptor.type == "decimal":
        return descriptor.default
    if descriptor.type == "bool":
        return bool(descriptor.default)
    if descriptor.type == "enum" and descriptor.choices:
        return descriptor.choices[0]
    if descriptor.type == "date":
        return date.today().isoformat()
    if descriptor.type == "currency":
        return descriptor.default or "INR"
    return descriptor.default
