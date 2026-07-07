"""Unit tests for `app.agent.specialists.text_promotion_diagnostics.build_specialist_text_promotion_metadata` (Phase 14)."""

from __future__ import annotations

from app.agent.specialists.text_promotion_diagnostics import build_specialist_text_promotion_metadata
from app.agent.specialists.text_promotion_schemas import SpecialistTextPromotionDecision, SpecialistTextPromotionReason

_LONG_ANSWER_TEXT = "This is the full promoted answer text. " * 50
_RAW_RESULT_MARKER = "RAW_SPECIALIST_RESULT_PAYLOAD_MARKER"
_RAW_OBSERVATION_MARKER = "RAW_OBSERVATION_SUMMARY_MARKER"


def _decision(**overrides) -> SpecialistTextPromotionDecision:
    defaults = dict(
        status="blocked",
        promoted=False,
        mode="promote_validated",
        workflow_name="graduation_progress_workflow",
        specialist_agent_name="graduation_progress_agent",
        reasons=[SpecialistTextPromotionReason(code="specialist_confidence_too_low", severity="warning")],
    )
    defaults.update(overrides)
    return SpecialistTextPromotionDecision(**defaults)


# ---------------------------------------------------------------------------
# 1. Compact metadata shape.
# ---------------------------------------------------------------------------


def test_compact_metadata_shape() -> None:
    metadata = build_specialist_text_promotion_metadata(_decision())

    assert set(metadata) == {"status", "promoted", "mode", "workflowName", "specialistAgentName", "reasons"}
    assert metadata["status"] == "blocked"
    assert metadata["promoted"] is False
    assert metadata["mode"] == "promote_validated"
    assert metadata["workflowName"] == "graduation_progress_workflow"
    assert metadata["specialistAgentName"] == "graduation_progress_agent"
    assert metadata["reasons"] == [{"code": "specialist_confidence_too_low", "severity": "warning"}]


def test_promoted_decision_metadata_shape() -> None:
    metadata = build_specialist_text_promotion_metadata(
        _decision(status="promoted", promoted=True, reasons=[])
    )

    assert metadata["status"] == "promoted"
    assert metadata["promoted"] is True
    assert metadata["reasons"] == []


# ---------------------------------------------------------------------------
# 2. Reasons capped if many.
# ---------------------------------------------------------------------------


def test_reasons_capped_if_many() -> None:
    many_reasons = [
        SpecialistTextPromotionReason(code=f"reason_{i}", severity="error") for i in range(50)
    ]
    metadata = build_specialist_text_promotion_metadata(_decision(reasons=many_reasons))

    assert len(metadata["reasons"]) == 20


# ---------------------------------------------------------------------------
# 3. No answer text stored.
# ---------------------------------------------------------------------------


def test_no_answer_text_stored() -> None:
    decision = _decision(
        reasons=[
            SpecialistTextPromotionReason(
                code="specialist_answer_text_too_long", severity="error", details={"preview": _LONG_ANSWER_TEXT}
            )
        ]
    )
    metadata = build_specialist_text_promotion_metadata(decision)

    metadata_text = str(metadata)
    assert _LONG_ANSWER_TEXT not in metadata_text
    assert "This is the full promoted answer text." not in metadata_text


# ---------------------------------------------------------------------------
# 4. No raw specialist result stored.
# ---------------------------------------------------------------------------


def test_no_raw_specialist_result_stored() -> None:
    decision = _decision(
        diagnostics={"rawResult": {"answer_text": _RAW_RESULT_MARKER, "creditsRemaining": 40.0}}
    )
    metadata = build_specialist_text_promotion_metadata(decision)

    assert _RAW_RESULT_MARKER not in str(metadata)
    assert "diagnostics" not in metadata


# ---------------------------------------------------------------------------
# 5. No raw observations stored.
# ---------------------------------------------------------------------------


def test_no_raw_observations_stored() -> None:
    decision = _decision(
        reasons=[
            SpecialistTextPromotionReason(
                code="specialist_has_rejected_tool_requests",
                severity="warning",
                details={"observationSummary": _RAW_OBSERVATION_MARKER},
            )
        ]
    )
    metadata = build_specialist_text_promotion_metadata(decision)

    assert _RAW_OBSERVATION_MARKER not in str(metadata)


# ---------------------------------------------------------------------------
# 6. Forbidden keys are rejected or omitted.
# ---------------------------------------------------------------------------


def test_forbidden_keys_never_appear_in_metadata() -> None:
    decision = _decision(
        reasons=[
            SpecialistTextPromotionReason(
                code="forbidden_diagnostic_payload_detected",
                severity="error",
                details={"chain_of_thought": "secret", "raw_context": {"x": 1}},
            )
        ]
    )
    metadata = build_specialist_text_promotion_metadata(decision)

    metadata_text = str(metadata)
    for forbidden in ("chain_of_thought", "raw_context", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        assert forbidden not in metadata_text


def test_metadata_only_ever_has_code_and_severity_per_reason() -> None:
    decision = _decision(
        reasons=[
            SpecialistTextPromotionReason(code="x", severity="error", details={"anything": "should be dropped"})
        ]
    )
    metadata = build_specialist_text_promotion_metadata(decision)

    for reason in metadata["reasons"]:
        assert set(reason) == {"code", "severity"}
