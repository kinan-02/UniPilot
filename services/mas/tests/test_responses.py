"""Unit tests for shared API response helpers."""

from app.core.responses import error_response, success_response


def test_success_response_envelope() -> None:
    payload = success_response({"status": "ok"})
    assert payload == {"success": True, "data": {"status": "ok"}, "error": None}


def test_error_response_envelope() -> None:
    payload = error_response("something went wrong")
    assert payload == {"success": False, "data": None, "error": "something went wrong"}
