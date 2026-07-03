import pytest

from app.config import MAX_RESULTS_CAP
from app.tools.validation import (
    validate_body_format,
    validate_iso_date,
    validate_max_results,
    validate_message_id,
    validate_user_id,
)
from app.graph.errors import OutlookValidationError


def test_validate_max_results_defaults_and_caps():
    assert validate_max_results(None) == 10
    assert validate_max_results(100) == MAX_RESULTS_CAP


def test_validate_max_results_rejects_zero():
    with pytest.raises(OutlookValidationError):
        validate_max_results(0)


def test_validate_user_id_requires_object_id():
    with pytest.raises(OutlookValidationError):
        validate_user_id("not-an-object-id")
    assert validate_user_id("507f1f77bcf86cd799439011") == "507f1f77bcf86cd799439011"


def test_validate_message_id_required():
    with pytest.raises(OutlookValidationError):
        validate_message_id("")


def test_validate_iso_date_accepts_date_and_datetime():
    assert validate_iso_date("2026-01-15", field_name="since") == "2026-01-15"
    assert validate_iso_date("2026-01-15T10:00:00Z", field_name="since") == "2026-01-15T10:00:00Z"


def test_validate_iso_date_rejects_invalid():
    with pytest.raises(OutlookValidationError):
        validate_iso_date("not-a-date", field_name="since")


def test_validate_body_format():
    assert validate_body_format("text") == "text"
    with pytest.raises(OutlookValidationError):
        validate_body_format("xml")
