import pytest

from app.core.exceptions import ValidationError
from app.modules.settings.registry import BY_KEY, get_descriptor
from app.modules.settings.service import validate_value


def test_unknown_key_is_rejected():
    assert get_descriptor("not.a.real.setting") is None


def test_registered_key_type_and_validation():
    due_days = get_descriptor("finance.invoice.due_days")
    assert due_days is not None
    assert validate_value(due_days, "30") == 30
    with pytest.raises(ValidationError) as exc:
        validate_value(due_days, 999)
    assert exc.value.code == "settings.validation_failed"


def test_v1_registry_contains_governance_flags():
    currency = BY_KEY["company.locale.currency"]
    assert currency.critical is True
    assert currency.immutable_after == "finance_first_posting"
    branch_fallback = BY_KEY["settings.sequence.branch_fallback"]
    assert branch_fallback.type == "bool"
    assert branch_fallback.default is False


def test_bank_match_rules_are_registered_and_validated():
    tolerance = BY_KEY["finance.bank.match.date_tolerance_days"]
    assert tolerance.default == 14
    assert tolerance.min == 0
    assert tolerance.max == 365
    assert tolerance.critical is True
    assert validate_value(tolerance, "30") == 30
    amount_mode = BY_KEY["finance.bank.match.amount_mode"]
    assert amount_mode.choices == ("signed", "absolute")
    assert validate_value(amount_mode, "absolute") == "absolute"
    with pytest.raises(ValidationError):
        validate_value(amount_mode, "rounded")


def test_bool_coercion_and_invalid_values():
    descriptor = BY_KEY["sales.credit_limit.enforced"]
    assert validate_value(descriptor, "true") is True
    with pytest.raises(ValidationError) as exc:
        validate_value(descriptor, "maybe")
    assert exc.value.code == "settings.type_mismatch"
