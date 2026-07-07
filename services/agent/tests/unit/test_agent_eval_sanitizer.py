"""Unit tests for offline eval sanitizer (Phase 23)."""

from __future__ import annotations

import pytest

from app.agent.evaluation.sanitizer import (
    assert_no_forbidden_eval_payload,
    sanitize_eval_payload,
)


def test_valid_payload_passes() -> None:
    payload = {"id": "c1", "user_message": "hello"}
    assert sanitize_eval_payload(payload, strict=True) == payload


def test_raw_context_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        sanitize_eval_payload({"raw_context": "x"}, strict=True)


def test_raw_prompt_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        sanitize_eval_payload({"raw_prompt": "x"}, strict=True)


def test_raw_blocks_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        sanitize_eval_payload({"raw_blocks": []}, strict=True)


def test_transcript_rows_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        sanitize_eval_payload({"transcript_rows": []}, strict=True)


def test_catalog_dump_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        sanitize_eval_payload({"catalog_dump": {}}, strict=True)


def test_proposed_action_payload_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        sanitize_eval_payload({"proposed_action_payload": {}}, strict=True)


def test_chain_of_thought_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        sanitize_eval_payload({"chain_of_thought": "x"}, strict=True)


def test_strict_false_strips_forbidden_keys() -> None:
    cleaned = sanitize_eval_payload({"raw_context": "x", "id": "c1"}, strict=False)
    assert "raw_context" not in cleaned
    assert cleaned["id"] == "c1"


def test_nested_forbidden_keys_rejected() -> None:
    with pytest.raises(ValueError, match="forbidden_eval_payload"):
        sanitize_eval_payload({"meta": {"raw_response": "x"}}, strict=True)


def test_assert_no_forbidden_eval_payload_passes() -> None:
    assert_no_forbidden_eval_payload({"safe": True})
