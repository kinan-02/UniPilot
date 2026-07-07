"""Unit tests for real-world anonymizer scanner (Phase 26)."""

from __future__ import annotations

from app.agent.evaluation.real_world_anonymizer import detect_possible_private_identifiers


def test_detects_email() -> None:
    findings = detect_possible_private_identifiers({"anonymized_user_message": "reach me at a@b.com"})
    assert any("email_pattern" in item for item in findings)


def test_detects_phone() -> None:
    findings = detect_possible_private_identifiers({"anonymized_user_message": "call +972-50-123-4567"})
    assert any("phone_pattern" in item for item in findings)


def test_detects_israeli_id_like_number() -> None:
    findings = detect_possible_private_identifiers({"anonymized_user_message": "id 123456789"})
    assert any("israeli_id_pattern" in item for item in findings)


def test_detects_long_student_id_like_number() -> None:
    findings = detect_possible_private_identifiers({"anonymized_user_message": "student number 12345678901"})
    assert any("long_numeric_id_pattern" in item for item in findings)


def test_detects_explicit_name_keys() -> None:
    findings = detect_possible_private_identifiers({"full_name": "Not Allowed"})
    assert any("explicit_name_key" in item for item in findings)


def test_detects_raw_pdf_file_path_markers() -> None:
    findings = detect_possible_private_identifiers({"anonymized_user_message": "uploaded /tmp/transcript.pdf"})
    assert any("raw_pdf_marker" in item or "file_path_marker" in item for item in findings)


def test_detects_transcript_row_markers() -> None:
    findings = detect_possible_private_identifiers({"anonymized_user_message": "transcript_rows export"})
    assert any("transcript_marker" in item for item in findings)


def test_nested_unsafe_fields_detected() -> None:
    findings = detect_possible_private_identifiers(
        {"anonymized_context": {"contact": {"email": "secret@example.com"}}}
    )
    assert findings


def test_safe_anonymized_payload_passes() -> None:
    findings = detect_possible_private_identifiers(
        {
            "anonymized_user_message": "What electives do I still need for CS track?",
            "anonymized_context": {"track": "cs", "year": 2},
        }
    )
    assert findings == []
