"""Unit tests for transcript import normalization."""

from types import SimpleNamespace

from app.services.transcript_import_normalization import (
    resolve_import_credits,
    resolve_import_grade_points,
)


def test_resolve_import_credits_prefers_parsed_pdf_value():
    row = SimpleNamespace(courseNumber="00940202", grade=79, creditsEarned=3.5)
    assert resolve_import_credits(row, {"credits": 4}) == 3.5


def test_resolve_import_credits_keeps_zero_for_exemption_without_points():
    row = SimpleNamespace(courseNumber="01030015", grade=0, creditsEarned=0)
    assert resolve_import_credits(row, {"credits": 3}) == 0.0


def test_resolve_import_credits_uses_catalog_for_graded_row_missing_credits():
    row = SimpleNamespace(courseNumber="00940411", grade=80, creditsEarned=0)
    assert resolve_import_credits(row, {"credits": 4}) == 4.0


def test_resolve_import_grade_points_marks_exemption_without_points():
    row = SimpleNamespace(grade=0)
    assert resolve_import_grade_points(row) == 0.0

    row = SimpleNamespace(grade=80)
    assert resolve_import_grade_points(row) is None
