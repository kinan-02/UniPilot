"""Unit tests for synthesis candidate safety (Phase 22)."""

from __future__ import annotations

from app.agent.synthesis.candidate_safety import check_synthesis_candidate_safety


def test_normal_academic_answer_passes() -> None:
    assert check_synthesis_candidate_safety("You still need 40 credits to graduate.") == []


def test_empty_candidate_fails() -> None:
    reasons = check_synthesis_candidate_safety("")
    assert any(r.code == "candidate_empty" for r in reasons)


def test_too_long_candidate_fails() -> None:
    reasons = check_synthesis_candidate_safety("x" * 100, max_chars=50)
    assert any(r.code == "candidate_too_long" for r in reasons)


def test_raw_payload_marker_fails() -> None:
    reasons = check_synthesis_candidate_safety("Here is ```json payload")
    assert any(r.code == "candidate_raw_payload_marker" for r in reasons)


def test_chain_of_thought_marker_fails() -> None:
    reasons = check_synthesis_candidate_safety("chain_of_thought: hidden")
    assert any(r.code == "candidate_chain_of_thought_marker" for r in reasons)


def test_write_claim_fails() -> None:
    reasons = check_synthesis_candidate_safety("I saved your plan to your profile.")
    assert any(r.code == "candidate_write_claim" for r in reasons)


def test_action_proposal_claim_fails() -> None:
    reasons = check_synthesis_candidate_safety("I created an action proposal for import.")
    assert any(r.code == "candidate_action_proposal_claim" for r in reasons)


def test_unsupported_certainty_with_uncertainty_notes_fails() -> None:
    reasons = check_synthesis_candidate_safety(
        "You will definitely graduate next semester.",
        uncertainty_notes=["Track choice is assumed"],
    )
    assert any(r.code == "candidate_unsupported_certainty" for r in reasons)


def test_internal_id_leak_fails() -> None:
    reasons = check_synthesis_candidate_safety("See ObjectId 507f1f77bcf86cd799439011 for details.")
    assert any(r.code == "candidate_internal_id_leak" for r in reasons)


def test_hebrew_normal_text_passes() -> None:
    assert check_synthesis_candidate_safety("חסרים לך 40 נקודות זכות לסיום התואר.") == []


def test_arabic_normal_text_passes() -> None:
    assert check_synthesis_candidate_safety("تحتاج إلى 40 نقطة إضافية للتخرج.") == []


def test_english_normal_text_passes() -> None:
    assert check_synthesis_candidate_safety("Focus on your remaining core courses this semester.") == []
