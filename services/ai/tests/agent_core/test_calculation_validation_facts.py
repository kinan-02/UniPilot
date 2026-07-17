"""Fact-binding regression tests for the calculation_validation subagent.

Covers the live-eval finding that a completed-courses list fetched by a
retrieval dependency arrived wrapped in its `{key, value, source, confidence}`
envelope, so the expression evaluator's single-hop `facts["completedCourses"]`
resolved to the wrapper dict instead of the list -- failing with
`of_not_a_list: ref:completedCourses`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent_core.planning.state import CertaintyTag, StateEntry
from app.agent_core.subagents.calculation_validation_block import (
    _flatten_dependency_facts,
    _unwrap_fact_envelope,
)


def _entry(step_id: str, data: dict) -> StateEntry:
    return StateEntry(
        entry_id=f"{step_id}-0",
        step_id=step_id,
        role="retrieval",
        status="succeeded",
        output_schema_name="retrieval_agent_output_v1",
        data=data,
        certainty=CertaintyTag(basis="official_record", confidence=1.0),
        produced_at=datetime.now(timezone.utc),
    )


def test_unwrap_fact_envelope_returns_inner_value() -> None:
    envelope = {
        "key": "completedCourses",
        "value": [{"courseNumber": "00440105"}],
        "source": "get_entity(...)",
        "confidence": 1.0,
    }

    assert _unwrap_fact_envelope(envelope) == [{"courseNumber": "00440105"}]


def test_unwrap_leaves_plain_dict_untouched() -> None:
    # A genuine dict fact that is not an envelope (no `key`) must pass through.
    plain = {"trackSlug": "track-electrical-engineering"}

    assert _unwrap_fact_envelope(plain) == plain


def test_flatten_promotes_and_unwraps_completed_courses_list() -> None:
    # Arrange -- the exact shape captured from the failing live run: an inner
    # `facts` map whose values are `{key, value, source, confidence}` envelopes.
    courses = [
        {"courseNumber": "00140003", "creditsEarned": 3.5},
        {"courseNumber": "00440105", "creditsEarned": 3.0},
    ]
    entry = _entry(
        "1b",
        {
            "facts": {
                "completedCourses": {
                    "key": "completedCourses",
                    "value": courses,
                    "source": "get_entity(entity_type='completed_courses')",
                    "confidence": 1.0,
                }
            },
            "confidence": 1.0,
        },
    )

    # Act
    facts = _flatten_dependency_facts([entry])

    # Assert -- the ref binds directly to the list, not the envelope.
    assert facts["completedCourses"] == courses
    assert isinstance(facts["completedCourses"], list)
    # The step_id key still carries the full entry data.
    assert facts["1b"]["facts"]["completedCourses"]["key"] == "completedCourses"


def test_flatten_promotes_facts_nested_under_pipeline_sub_results() -> None:
    # A routed multi-specialist pipeline aggregates its sub-steps one level
    # deeper, under data["sub_results"][<sub>]["facts"] -- there is no top-level
    # "facts" key. The flattener must descend so a downstream calc expression
    # can still bind {"ref": "completedCourses"} to the list. Regression for the
    # ISE `credits_remaining` live run: without this, `_flatten_dependency_facts`
    # left the list buried, the sum step reported `List-valued facts available:
    # []`, and the whole calculation died.
    courses = [
        {"courseNumber": "00940345", "creditsEarned": 4.0},
        {"courseNumber": "00940704", "creditsEarned": 1.5},
    ]
    entry = _entry(
        "1e",
        {
            "sub_results": {
                "1b": {
                    "facts": {
                        "completedCourses": {
                            "key": "completedCourses",
                            "value": courses,
                            "source": "get_entity(entity_type='completed_courses')",
                            "confidence": 1.0,
                        }
                    }
                }
            }
        },
    )

    facts = _flatten_dependency_facts([entry])

    assert facts["completedCourses"] == courses
    assert isinstance(facts["completedCourses"], list)
    # The step_id key still carries the full aggregate output.
    assert "sub_results" in facts["1e"]


def test_flatten_does_not_overwrite_existing_step_id_key() -> None:
    # An inner fact key that collides with a step_id must not clobber it
    # (promotion is additive, via setdefault).
    entry = _entry("credits", {"facts": {"credits": {"key": "credits", "value": 12}}})

    facts = _flatten_dependency_facts([entry])

    assert facts["credits"] == entry.data


# --- Cross-step refs -------------------------------------------------------
#
# CAUGHT LIVE (2026-07-16, `credits_remaining`). The turn computed both numbers
# it needed and could not subtract them: `ref` is a single-hop `facts[ref]`
# lookup, and a prior calculation's 62.5 sat one level down inside its entry
# dict. Retrieval was unaffected (its `facts` map gets promoted), so the system
# could compute from fetched data but never from a computation -- and any
# credits-remaining answer is inherently two-stage.


def _calc_entry(step_id: str, result) -> StateEntry:
    entry = _entry(step_id, {"type": "expression", "result": result, "trace": [f"... = {result}"]})
    return entry.model_copy(update={"role": "calculation_validation"})


def _interpretation_entry(step_id: str, answer: str) -> StateEntry:
    entry = _entry(
        step_id,
        {"certainty_basis": "wiki_derived", "confidence": 1.0, "assumptions": [], "answer": answer},
    )
    return entry.model_copy(update={"role": "interpretation"})


def test_a_prior_calculations_result_is_ref_able_by_step_id() -> None:
    facts = _flatten_dependency_facts([_calc_entry("1e", 62.5)])

    assert facts["1e"] == 62.5, "a ref must bind to the number, not the entry dict"


def test_an_interpretations_answer_is_ref_able_by_step_id() -> None:
    facts = _flatten_dependency_facts([_interpretation_entry("1d", "155")])

    assert facts["1d"] == "155"


def test_the_live_credits_remaining_expression_now_evaluates() -> None:
    """The exact expression the model wrote, which failed three times.

    `subtract(ref "1d", ref "1e")` -> `non_numeric_operand: subtract`, because
    both refs bound to entry dicts. There was no expression that could have
    worked; composition did the arithmetic in prose instead.
    """
    from app.agent_core.tools.primitives.expression_tree import (
        ExpressionNode,
        evaluate_expression,
        validate_expression_tree,
    )

    facts = _flatten_dependency_facts([_interpretation_entry("1d", "155"), _calc_entry("1e", 62.5)])
    node = ExpressionNode(op="subtract", left=ExpressionNode(ref="1d"), right=ExpressionNode(ref="1e"))

    assert validate_expression_tree(node, facts=facts) == []
    result, _trace, errors = evaluate_expression(node, facts)

    assert errors == []
    assert result == 92.5, "155 (read off the wiki as a string) minus 62.5 (a prior calculation)"


def test_a_retrieval_entry_still_binds_to_its_whole_data() -> None:
    """Only a step that answered with ONE value is scalarized. Retrieval answers
    with a `facts` map, whose members are promoted individually -- unchanged."""
    facts = _flatten_dependency_facts([
        _entry("1b", {"certainty_basis": "official_record", "confidence": 1.0, "facts": {"completedCourses": {"key": "completedCourses", "value": [{"creditsEarned": 4.0}]}}})
    ])

    assert isinstance(facts["1b"], dict)
    assert facts["completedCourses"] == [{"creditsEarned": 4.0}]
