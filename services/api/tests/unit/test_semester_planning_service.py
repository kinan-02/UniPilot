"""Unit tests for semester planning service helpers."""

from app.services.semester_planning_service import _build_credit_variants


def test_build_credit_variants_default():
    variants = _build_credit_variants(default_max=18.0, planning_objective="")
    labels = [label for label, _ in variants]
    credits = [value for _, value in variants]
    assert "Balanced" in labels
    assert 18.0 in credits
    assert len(variants) >= 2


def test_build_credit_variants_lighter_objective():
    variants = _build_credit_variants(default_max=18.0, planning_objective="lighter_workload")
    assert variants[0][0] == "Lighter workload"
    assert variants[0][1] == 14.0
