from datetime import date

import pytest

from app.modules.settings import patterns


def test_pattern_render_and_worst_case_length():
    context = patterns.RenderContext(seq=42, padding=5, prefix="INV", on_date=date(2025, 4, 1), fiscal_year="25-26")
    assert patterns.render("INV/{fy}/{seq:05}", context) == "INV/25-26/00042"
    assert patterns.validate("INV/{fy}/{seq:05}", doc_type="gst_invoice", padding=5, prefix="INV") == []


def test_gst_17_character_invoice_pattern_is_rejected():
    problems = patterns.validate("GSTINV/{fy}/{seq:05}", doc_type="gst_invoice", padding=5, prefix="GSTINV")
    assert problems


@pytest.mark.parametrize("pattern", ["{uuid}", "{now}", "{random}", "INV/{unknown}/{seq}", "INV/{seq"])
def test_forbidden_unknown_and_malformed_patterns(pattern):
    problems = patterns.validate(pattern, doc_type="internal", padding=5, prefix="INV")
    assert problems


def test_profile_compliance_for_gst_documents():
    for doc_type in ("gst_invoice", "gst_credit_note", "gst_debit_note", "gst_bill_of_supply"):
        profile = patterns.profile_for(doc_type)
        assert profile.max_length == 16
        assert profile.irp_safe is True
