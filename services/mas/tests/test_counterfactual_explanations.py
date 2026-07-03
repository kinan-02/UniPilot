"""Tests for counterfactual explanations."""

from __future__ import annotations

from app.services.counterfactual_explanations import build_counterfactual_explanations


def test_build_counterfactual_explanations_for_rejected_variants() -> None:
    explanations = build_counterfactual_explanations(
        chosen_variant="balanced",
        chosen_utility=0.81,
        arbitration={
            "chosen_variant": "balanced",
            "rejected_alternatives": [
                {
                    "variant": "fast",
                    "course_ids": ["00140008", "00140102"],
                    "utility": 0.72,
                }
            ],
        },
        variant_evaluations=[
            {
                "variant": "fast",
                "course_ids": ["00140008", "00140102"],
                "hard_ok": True,
            }
        ],
    )
    assert len(explanations) == 1
    assert explanations[0]["variant"] == "fast"
    assert "0.72" in explanations[0]["reason"]


def test_build_counterfactual_explanations_for_hard_failed_variant() -> None:
    explanations = build_counterfactual_explanations(
        chosen_variant="balanced",
        chosen_utility=0.81,
        arbitration={"chosen_variant": "balanced", "rejected_alternatives": []},
        variant_evaluations=[
            {
                "variant": "aggressive",
                "course_ids": ["00140008", "00140102", "00140101"],
                "hard_ok": False,
                "progress_report": {"critiques": [{"message": "Credit overload"}]},
            }
        ],
    )
    assert explanations[0]["hardOk"] is False
    assert "Credit overload" in explanations[0]["reason"]


def test_build_counterfactual_explanations_skips_invalid_entries() -> None:
    explanations = build_counterfactual_explanations(
        chosen_variant="balanced",
        chosen_utility=0.81,
        arbitration={
            "chosen_variant": "balanced",
            "rejected_alternatives": ["not-a-dict", {"variant": "balanced"}],
        },
        variant_evaluations=["not-a-dict"],
    )
    assert explanations == []


def test_build_counterfactual_explanations_uses_default_hard_failure_reason() -> None:
    explanations = build_counterfactual_explanations(
        chosen_variant="balanced",
        chosen_utility=0.81,
        arbitration={"chosen_variant": "balanced", "rejected_alternatives": []},
        variant_evaluations=[
            {
                "variant": "aggressive",
                "course_ids": ["00140008"],
                "hard_ok": False,
            }
        ],
    )
    assert explanations[0]["reason"] == "Failed hard feasibility or workload constraints."
