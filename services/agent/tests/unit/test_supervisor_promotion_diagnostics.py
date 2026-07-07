"""Unit tests for `supervisor/promotion_diagnostics.build_supervisor_promotion_metadata`."""

from __future__ import annotations

from app.agent.supervisor.promotion_diagnostics import build_supervisor_promotion_metadata
from app.agent.supervisor.promotion_schemas import PromotionBlockReason, PromotionDecision


def test_metadata_shape_matches_spec() -> None:
    decision = PromotionDecision(
        status="blocked",
        promoted=False,
        workflow_name="graduation_progress_workflow",
        mode="promote_validated",
        reasons=[PromotionBlockReason(code="validation_not_passed", severity="warning", message="...")],
    )

    metadata = build_supervisor_promotion_metadata(decision)

    assert metadata == {
        "status": "blocked",
        "promoted": False,
        "workflowName": "graduation_progress_workflow",
        "mode": "promote_validated",
        "reasons": [{"code": "validation_not_passed", "severity": "warning"}],
    }


def test_metadata_for_promoted_decision() -> None:
    decision = PromotionDecision(
        status="promoted", promoted=True, workflow_name="graduation_progress_workflow", mode="promote_validated"
    )

    metadata = build_supervisor_promotion_metadata(decision)

    assert metadata["status"] == "promoted"
    assert metadata["promoted"] is True
    assert metadata["reasons"] == []


def test_metadata_for_skipped_decision() -> None:
    decision = PromotionDecision(status="skipped", promoted=False, workflow_name=None, mode="off")

    metadata = build_supervisor_promotion_metadata(decision)

    assert metadata["status"] == "skipped"
    assert metadata["workflowName"] is None
    assert metadata["mode"] == "off"


def test_metadata_caps_reasons_list() -> None:
    reasons = [PromotionBlockReason(code=f"code-{i}", severity="error", message="m") for i in range(30)]
    decision = PromotionDecision(status="blocked", promoted=False, workflow_name="graduation_progress_workflow", reasons=reasons)

    metadata = build_supervisor_promotion_metadata(decision)

    assert len(metadata["reasons"]) == 20


def test_metadata_never_includes_raw_details_or_forbidden_payload() -> None:
    decision = PromotionDecision(
        status="blocked",
        promoted=False,
        workflow_name="graduation_progress_workflow",
        reasons=[
            PromotionBlockReason(
                code="block_types_mismatch",
                severity="error",
                message="mismatch",
                details={"liveBlockTypes": ["A"], "candidateBlockTypes": ["B"], "raw_context": {"x": 1}},
            )
        ],
    )

    metadata = build_supervisor_promotion_metadata(decision)

    metadata_text = str(metadata)
    # Only code/severity are ever surfaced per reason -- `details` (which
    # could theoretically carry something larger) is intentionally dropped.
    assert "liveBlockTypes" not in metadata_text
    assert "raw_context" not in metadata_text
