"""Document-number pattern grammar (module 15A, §5.4).

A pattern is an allow-listed token template such as ``INV/{fy}/{seq:05}``.
Rendering is plain token substitution — never ``str.format`` on user input — so a
stored pattern can never execute anything, and every token is predictable which
keeps ``peek``/preview and the gap report exact.

Rule 46 / IRP constraints are applied per document channel through
:class:`DocProfile` and enforced at *config* time (worst-case render) as well as
at *render* time.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Optional

TOKEN_PATTERN = re.compile(r"\{([a-z_]+)(?::0?(\d{1,3})d?)?\}")

ALLOWED_TOKENS = frozenset(
    {"seq", "prefix", "suffix", "fy", "yy", "yyyy", "mm", "dd", "branch", "state", "tenant_code", "doc"}
)

# Tokens that would make numbering unpredictable or injectable. They are rejected
# with a dedicated message so an admin understands *why*.
FORBIDDEN_TOKENS = frozenset(
    {"random", "uuid", "user", "now", "env", "date", "time", "guid", "nanoid"}
)

MAX_PADDING = 12


class PatternError(ValueError):
    """Raised for an unparseable or unsafe pattern."""

    def __init__(self, message: str, *, code: str = "numbering.pattern_invalid"):
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class DocProfile:
    """Rendering constraints for one document channel."""

    name: str
    max_length: int
    allowed_regex: str
    uppercase: bool
    irp_safe: bool
    default_reset: str = "fiscal_year"


PROFILES: dict[str, DocProfile] = {
    "gst_invoice": DocProfile("gst_invoice", 16, r"^[A-Z0-9\-/]+$", True, True),
    "gst_credit_note": DocProfile("gst_credit_note", 16, r"^[A-Z0-9\-/]+$", True, True),
    "gst_debit_note": DocProfile("gst_debit_note", 16, r"^[A-Z0-9\-/]+$", True, True),
    "gst_bill_of_supply": DocProfile("gst_bill_of_supply", 16, r"^[A-Z0-9\-/]+$", True, True),
    "pos_sale": DocProfile("pos_sale", 24, r"^[A-Z0-9\-/]+$", True, False),
    "internal": DocProfile("internal", 32, r"^[A-Za-z0-9\-/_ ]+$", False, False, "never"),
    "journal_entry": DocProfile("journal_entry", 32, r"^[A-Z0-9\-/]+$", False, False),
}

DEFAULT_PROFILE = PROFILES["internal"]


def profile_for(doc_type: str | None) -> DocProfile:
    return PROFILES.get(doc_type or "internal", DEFAULT_PROFILE)


def fiscal_year_label(on_date: date, start_month: int = 4) -> str:
    """Short Indian-style fiscal-year label: 2025-04-01..2026-03-31 -> ``25-26``."""
    year = on_date.year if on_date.month >= start_month else on_date.year - 1
    return f"{str(year % 100).zfill(2)}-{str((year + 1) % 100).zfill(2)}"


def period_bounds(on_date: date, reset_policy: str, start_month: int = 4) -> tuple[date, date, str]:
    """Return ``(period_start, period_end, fiscal_year_key)`` for a document date."""
    if reset_policy == "never":
        return date(1970, 1, 1), date(2999, 12, 31), ""
    if reset_policy == "monthly":
        start = on_date.replace(day=1)
        end = _add_months(start, 1)
        return start, end, f"{on_date.year}-{str(on_date.month).zfill(2)}"
    if reset_policy == "calendar_year":
        return date(on_date.year, 1, 1), date(on_date.year, 12, 31), str(on_date.year)
    # fiscal_year (default, Indian April-March)
    label = fiscal_year_label(on_date, start_month)
    start_year = on_date.year if on_date.month >= start_month else on_date.year - 1
    start = date(start_year, start_month, 1)
    return start, _add_months(start, 12), label


def _add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    # Day overflow is irrelevant for period ends (we always start from day 1).
    day = min(value.day, 28)
    return date(year, month, day)


def parse(pattern: str) -> list[str | tuple[str, Optional[int]]]:
    """Split a pattern into literal chunks and ``(token, width)`` tuples."""
    if not pattern:
        raise PatternError("Pattern is empty")
    if pattern.count("{") != pattern.count("}"):
        raise PatternError("Pattern has unbalanced braces")
    tokens: list[str | tuple[str, Optional[int]]] = []
    cursor = 0
    for match in TOKEN_PATTERN.finditer(pattern):
        literal = pattern[cursor : match.start()]
        if literal:
            tokens.append(literal)
        name, width = match.group(1), match.group(2)
        if name in FORBIDDEN_TOKENS:
            raise PatternError(
                f"Token '{{{name}}}' is not allowed: document numbers must be predictable",
                code="numbering.pattern_token_forbidden",
            )
        if name not in ALLOWED_TOKENS:
            raise PatternError(f"Unknown pattern token '{{{name}}}'")
        if width is not None and not 1 <= int(width) <= MAX_PADDING:
            raise PatternError(f"Width for '{{{name}}}' must be 1..{MAX_PADDING}")
        tokens.append((name, int(width) if width else None))
        cursor = match.end()
    tail = pattern[cursor:]
    if tail:
        tokens.append(tail)
    leftover = [chunk for chunk in tokens if isinstance(chunk, str) and ("{" in chunk or "}" in chunk)]
    if leftover:
        raise PatternError(f"Malformed pattern near {leftover[0]!r}")
    return tokens


@dataclass(frozen=True)
class RenderContext:
    seq: int
    padding: int = 5
    prefix: str = ""
    suffix: str = ""
    on_date: Optional[date] = None
    fiscal_year: str = ""
    branch_code: str = ""
    state_code: str = ""
    tenant_code: str = ""
    doc_code: str = ""


def render(pattern: str, context: RenderContext) -> str:
    if not pattern:
        # Legacy rows with no pattern keep the classic PREFIX-00001 shape.
        return f"{context.prefix}-{context.seq:0{context.padding}d}"
    on_date = context.on_date or date.today()
    pieces: list[str] = []
    for token in parse(pattern):
        if isinstance(token, str):
            pieces.append(token)
            continue
        name, width = token
        if name == "seq":
            pieces.append(str(context.seq).zfill(width or context.padding))
        elif name == "prefix":
            pieces.append(context.prefix)
        elif name == "suffix":
            pieces.append(context.suffix)
        elif name == "fy":
            pieces.append(context.fiscal_year)
        elif name == "yy":
            pieces.append(str(on_date.year)[-2:])
        elif name == "yyyy":
            pieces.append(str(on_date.year))
        elif name == "mm":
            pieces.append(f"{on_date.month:02d}")
        elif name == "dd":
            pieces.append(f"{on_date.day:02d}")
        elif name == "branch":
            pieces.append(context.branch_code)
        elif name == "state":
            pieces.append(context.state_code)
        elif name == "tenant_code":
            pieces.append(context.tenant_code)
        elif name == "doc":
            pieces.append(context.doc_code or context.prefix)
    return "".join(pieces)


def worst_case(
    pattern: str,
    *,
    padding: int,
    prefix: str = "",
    suffix: str = "",
    branch_code: str = "",
    state_code: str = "",
    tenant_code: str = "",
    doc_code: str = "",
    on_date: Optional[date] = None,
    fiscal_year: str = "",
) -> str:
    """Render the longest possible value the pattern can ever produce.

    This is the anti-timebomb check: a series that renders ``INV/25-26/00001`` is
    fine, but if document 100000 would overflow the 16-character GST limit the
    pattern must be rejected *now*, not in production two years from now.
    """
    probe = on_date or date.today()
    return render(
        pattern,
        RenderContext(
            seq=10**min(padding, MAX_PADDING) - 1,
            padding=padding,
            prefix=prefix,
            suffix=suffix,
            on_date=probe,
            fiscal_year=fiscal_year or fiscal_year_label(probe),
            branch_code=branch_code or "XXXXXXXX",
            state_code=state_code or "99",
            tenant_code=tenant_code or "XXXXXXXX",
            doc_code=doc_code,
        ),
    )


def validate(
    pattern: str | None,
    *,
    doc_type: str = "internal",
    padding: int = 5,
    prefix: str = "",
    suffix: str = "",
    irp_safe: bool = False,
    max_length: int | None = None,
    allowed_chars_regex: str | None = None,
    branch_code: str = "",
    state_code: str = "",
    tenant_code: str = "",
    doc_code: str = "",
    sample_date: Optional[date] = None,
) -> list[str]:
    """Validate a series configuration; returns human-readable problems (empty = OK)."""
    profile = profile_for(doc_type)
    problems: list[str] = []
    if padding < 1 or padding > MAX_PADDING:
        problems.append(f"padding must be between 1 and {MAX_PADDING}")
    if pattern is None:
        # Legacy prefix/padding configuration: validate the classic shape.
        sample = f"{prefix}-{(10**min(padding, MAX_PADDING)) - 1:0{padding}d}"
        pattern_ok = True
    else:
        try:
            parse(pattern)
        except PatternError as exc:
            return [str(exc)]
        sample = worst_case(
            pattern,
            padding=padding,
            prefix=prefix,
            suffix=suffix,
            branch_code=branch_code,
            state_code=state_code,
            tenant_code=tenant_code,
            doc_code=doc_code,
            on_date=sample_date,
        )
        pattern_ok = True

    if not pattern_ok:
        return problems

    limit = max_length or profile.max_length
    if len(sample) > limit:
        problems.append(
            f"Rendered number '{sample}' is {len(sample)} characters; the {doc_type} "
            f"channel allows at most {limit}"
        )
    regex = allowed_chars_regex or profile.allowed_regex
    try:
        compiled = re.compile(regex)
    except re.error:
        problems.append(f"allowed_chars_regex {regex!r} is not a valid regular expression")
        compiled = None
    if compiled is not None and not compiled.match(sample):
        problems.append(f"Rendered number '{sample}' does not match allowed characters {regex}")
    if (irp_safe or profile.irp_safe) and sample:
        if sample[0] in {"0", "-", "/"}:
            problems.append("IRP validation rejects numbers starting with '0', '-' or '/'")
        if sample != sample.upper():
            problems.append("IRP validation rejects lowercase characters in document numbers")
    return problems


def sanitize(value: str, doc_type: str = "internal") -> str:
    """Uppercase when the channel requires it (IRP rejects lowercase)."""
    profile = profile_for(doc_type)
    return value.upper() if profile.uppercase else value
