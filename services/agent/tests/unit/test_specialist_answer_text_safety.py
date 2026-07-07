"""Unit tests for `app.agent.specialists.answer_text_safety.check_answer_text_safety` (Phase 14)."""

from __future__ import annotations

from app.agent.specialists.answer_text_safety import check_answer_text_safety

_NORMAL_TEXT = (
    "You still need 40 more credits to graduate. Focus on completing your remaining "
    "core courses in the data engineering track next semester."
)


# ---------------------------------------------------------------------------
# 1. Normal answer text passes.
# ---------------------------------------------------------------------------


def test_normal_answer_text_passes() -> None:
    assert check_answer_text_safety(_NORMAL_TEXT) == []


# ---------------------------------------------------------------------------
# 2. Empty text fails.
# ---------------------------------------------------------------------------


def test_empty_text_fails() -> None:
    reasons = check_answer_text_safety("")
    assert any(r.code == "specialist_answer_text_empty" for r in reasons)


def test_whitespace_only_text_fails() -> None:
    reasons = check_answer_text_safety("   \n\t  ")
    assert any(r.code == "specialist_answer_text_empty" for r in reasons)


def test_none_text_fails() -> None:
    reasons = check_answer_text_safety(None)
    assert any(r.code == "specialist_answer_text_empty" for r in reasons)


# ---------------------------------------------------------------------------
# 3. Too-long text fails.
# ---------------------------------------------------------------------------


def test_too_long_text_fails() -> None:
    reasons = check_answer_text_safety("x" * 4001, max_chars=4000)
    assert any(r.code == "specialist_answer_text_too_long" for r in reasons)


def test_text_at_exact_limit_passes_length_check() -> None:
    reasons = check_answer_text_safety("a" * 4000, max_chars=4000)
    assert not any(r.code == "specialist_answer_text_too_long" for r in reasons)


# ---------------------------------------------------------------------------
# 4. Chain-of-thought marker fails.
# ---------------------------------------------------------------------------


def test_chain_of_thought_marker_fails() -> None:
    reasons = check_answer_text_safety(f"{_NORMAL_TEXT} chain_of_thought: secret reasoning here")
    assert any(r.code == "specialist_answer_text_forbidden_payload" for r in reasons)


# ---------------------------------------------------------------------------
# 5. Scratchpad marker fails.
# ---------------------------------------------------------------------------


def test_scratchpad_marker_fails() -> None:
    reasons = check_answer_text_safety(f"{_NORMAL_TEXT} scratchpad notes: draft reasoning")
    assert any(r.code == "specialist_answer_text_forbidden_payload" for r in reasons)


# ---------------------------------------------------------------------------
# 6. Raw blocks marker fails.
# ---------------------------------------------------------------------------


def test_raw_blocks_marker_fails() -> None:
    reasons = check_answer_text_safety('Here is the answer. "blocks": [{"type": "GraduationStatusBlock"}]')
    assert any(r.code == "specialist_answer_text_forbidden_payload" for r in reasons)


# ---------------------------------------------------------------------------
# 7. Proposed action payload marker fails.
# ---------------------------------------------------------------------------


def test_proposed_action_payload_marker_fails() -> None:
    reasons = check_answer_text_safety('Done. "proposedActions": [{"actionType": "save_semester_plan"}]')
    assert any(r.code == "specialist_answer_text_forbidden_payload" for r in reasons)


# ---------------------------------------------------------------------------
# 8. Write/save/import claim fails.
# ---------------------------------------------------------------------------


def test_write_claim_i_updated_fails() -> None:
    reasons = check_answer_text_safety("I updated your profile with the latest credits.")
    assert any(r.code == "specialist_answer_text_write_claim" for r in reasons)


def test_write_claim_i_saved_fails() -> None:
    reasons = check_answer_text_safety("I saved your new semester plan.")
    assert any(r.code == "specialist_answer_text_write_claim" for r in reasons)


def test_write_claim_i_imported_fails() -> None:
    reasons = check_answer_text_safety("I imported your transcript successfully.")
    assert any(r.code == "specialist_answer_text_write_claim" for r in reasons)


def test_write_claim_changed_profile_fails() -> None:
    reasons = check_answer_text_safety("I changed your profile to reflect the new track.")
    assert any(r.code == "specialist_answer_text_write_claim" for r in reasons)


# ---------------------------------------------------------------------------
# 9. Raw transcript marker fails.
# ---------------------------------------------------------------------------


def test_raw_transcript_marker_fails() -> None:
    reasons = check_answer_text_safety(f"{_NORMAL_TEXT} transcript_rows: [row1, row2]")
    assert any(r.code == "specialist_answer_text_forbidden_payload" for r in reasons)


# ---------------------------------------------------------------------------
# 10. Raw catalog dump marker fails.
# ---------------------------------------------------------------------------


def test_raw_catalog_dump_marker_fails() -> None:
    reasons = check_answer_text_safety(f"{_NORMAL_TEXT} full_catalog: [...]")
    assert any(r.code == "specialist_answer_text_forbidden_payload" for r in reasons)


# ---------------------------------------------------------------------------
# 11. Hebrew/Arabic/English normal academic explanation passes.
# ---------------------------------------------------------------------------


def test_hebrew_normal_academic_explanation_passes() -> None:
    hebrew_text = "נותרו לך 40 נקודות זכות להשלמת התואר. מומלץ להתמקד בקורסי הליבה הנותרים."
    assert check_answer_text_safety(hebrew_text) == []


def test_arabic_normal_academic_explanation_passes() -> None:
    arabic_text = "لا يزال يتعين عليك إكمال 40 ساعة معتمدة للتخرج. ركز على المقررات الأساسية المتبقية."
    assert check_answer_text_safety(arabic_text) == []


def test_english_normal_academic_explanation_passes() -> None:
    assert check_answer_text_safety(_NORMAL_TEXT) == []


# ---------------------------------------------------------------------------
# Additional: never raises, and returns compact reasons only.
# ---------------------------------------------------------------------------


def test_never_raises_on_non_string_input() -> None:
    reasons = check_answer_text_safety(12345)  # type: ignore[arg-type]
    assert isinstance(reasons, list)


def test_never_raises_on_bad_max_chars() -> None:
    reasons = check_answer_text_safety(_NORMAL_TEXT, max_chars=None)  # type: ignore[arg-type]
    assert isinstance(reasons, list)


def test_reasons_are_compact_reason_objects() -> None:
    reasons = check_answer_text_safety("")
    for reason in reasons:
        assert reason.code
        assert reason.severity in ("info", "warning", "error")
