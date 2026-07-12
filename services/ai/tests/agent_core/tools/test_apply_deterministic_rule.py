"""Unit tests for `apply_deterministic_rule` (docs/agent/AGENT_VISION.md §5, primitive 6).

`rule` shape and `rule["type"]` vocabulary are defined in
docs/agent/DETERMINISTIC_RULE_CONTRACT.md -- these tests exercise all three
rule types, every fail-closed error path, and the "missing facts key" vs
"present but empty" distinction the contract doc requires.
"""

from __future__ import annotations

import pytest

from app.agent_core.tools.primitives.apply_deterministic_rule import (
    ApplyDeterministicRuleInput,
    run_apply_deterministic_rule,
)


async def test_missing_rule_type_fails_closed():
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule={}, facts={}))
    assert result.ok is False
    assert "rule_type_required" in result.error


async def test_unknown_rule_type_fails_closed():
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule={"type": "guess_the_answer"}, facts={})
    )
    assert result.ok is False
    assert "unknown_rule_type: guess_the_answer" in result.error


async def test_rule_type_key_accepted_as_an_alias_for_type():
    """A live-eval run found the model reliably using `rule_type` instead of
    `type` -- `rule` is a loosely-typed dict, so this key name is invisible
    in the JSON schema the model sees. Accepted as an alias rather than
    relying solely on prompt wording."""
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(
            rule={"rule_type": "count_threshold", "source": "items", "comparator": ">=", "threshold": 0},
            facts={"items": []},
        )
    )
    assert result.ok is True
    assert result.data["type"] == "count_threshold"


async def test_type_key_takes_precedence_over_rule_type_alias():
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(
            rule={
                "type": "count_threshold",
                "rule_type": "guess_the_answer",
                "source": "items",
                "comparator": ">=",
                "threshold": 0,
            },
            facts={"items": []},
        )
    )
    assert result.ok is True
    assert result.data["type"] == "count_threshold"


# -- sum_threshold ------------------------------------------------------


async def test_sum_threshold_computes_correctly_with_filter():
    rule = {
        "type": "sum_threshold",
        "source": "completedCourses",
        "field": "credits",
        "filter": {"status": "completed"},
        "comparator": ">=",
        "threshold": 5,
    }
    facts = {
        "completedCourses": [
            {"credits": 3.5, "status": "completed"},
            {"credits": 2.0, "status": "completed"},
            {"credits": 4.0, "status": "failed"},  # excluded by filter
        ]
    }
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts=facts))
    assert result.ok is True
    assert result.data == {
        "type": "sum_threshold",
        "sum": 5.5,
        "comparator": ">=",
        "threshold": 5,
        "satisfied": True,
        "matchedCount": 2,
    }
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_sum_threshold_without_filter_includes_all_records():
    rule = {
        "type": "sum_threshold",
        "source": "completedCourses",
        "field": "credits",
        "comparator": ">=",
        "threshold": 100,
    }
    facts = {"completedCourses": [{"credits": 3.5}, {"credits": 2.0}]}
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts=facts))
    assert result.ok is True
    assert result.data["sum"] == 5.5
    assert result.data["matchedCount"] == 2
    assert result.data["satisfied"] is False


async def test_sum_threshold_missing_required_field_fails_closed():
    rule = {"type": "sum_threshold", "field": "credits", "comparator": ">=", "threshold": 5}
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts={}))
    assert result.ok is False
    assert "source_required" in result.error


async def test_sum_threshold_unknown_comparator_fails_closed():
    rule = {
        "type": "sum_threshold",
        "source": "completedCourses",
        "field": "credits",
        "comparator": "~=",
        "threshold": 5,
    }
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completedCourses": []})
    )
    assert result.ok is False
    assert "unknown_comparator: ~=" in result.error


async def test_sum_threshold_missing_facts_source_fails_closed():
    """`facts` has no "completedCourses" key at all -- "we don't have this
    data" -- distinct from the key being present with an empty list."""
    rule = {
        "type": "sum_threshold",
        "source": "completedCourses",
        "field": "credits",
        "comparator": ">=",
        "threshold": 5,
    }
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts={}))
    assert result.ok is False
    assert "facts_source_missing: completedCourses" in result.error


async def test_sum_threshold_empty_facts_source_is_a_real_zero_not_a_failure():
    """`facts["completedCourses"]` present as `[]` -- a real, computable
    answer (sum is legitimately 0), not "cannot determine"."""
    rule = {
        "type": "sum_threshold",
        "source": "completedCourses",
        "field": "credits",
        "comparator": ">=",
        "threshold": 5,
    }
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completedCourses": []})
    )
    assert result.ok is True
    assert result.data["sum"] == 0
    assert result.data["satisfied"] is False


async def test_sum_threshold_wrong_shape_facts_source_fails_closed():
    rule = {
        "type": "sum_threshold",
        "source": "completedCourses",
        "field": "credits",
        "comparator": ">=",
        "threshold": 5,
    }
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completedCourses": {"not": "a list"}})
    )
    assert result.ok is False
    assert "facts_source_wrong_shape: completedCourses" in result.error


async def test_sum_threshold_non_numeric_field_value_fails_closed():
    rule = {
        "type": "sum_threshold",
        "source": "completedCourses",
        "field": "credits",
        "comparator": ">=",
        "threshold": 5,
    }
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completedCourses": [{"credits": "three"}]})
    )
    assert result.ok is False
    assert "non_numeric_field_value: completedCourses.credits" in result.error


async def test_sum_threshold_boolean_field_value_treated_as_non_numeric():
    """`isinstance(True, numbers.Number)` is `True` in Python -- must be
    rejected explicitly, never silently summed as 1."""
    rule = {
        "type": "sum_threshold",
        "source": "completedCourses",
        "field": "passed",
        "comparator": ">=",
        "threshold": 1,
    }
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completedCourses": [{"passed": True}]})
    )
    assert result.ok is False
    assert "non_numeric_field_value" in result.error


# -- count_threshold ------------------------------------------------------


async def test_count_threshold_computes_correctly_with_filter():
    rule = {
        "type": "count_threshold",
        "source": "completedCourses",
        "filter": {"requirementBucket": "math"},
        "comparator": ">=",
        "threshold": 2,
    }
    facts = {
        "completedCourses": [
            {"requirementBucket": "math"},
            {"requirementBucket": "math"},
            {"requirementBucket": "physics"},
        ]
    }
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts=facts))
    assert result.ok is True
    assert result.data == {
        "type": "count_threshold",
        "count": 2,
        "comparator": ">=",
        "threshold": 2,
        "satisfied": True,
    }


async def test_count_threshold_missing_required_field_fails_closed():
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule={"type": "count_threshold", "comparator": ">=", "threshold": 2}, facts={})
    )
    assert result.ok is False
    assert "source_required" in result.error


async def test_count_threshold_unknown_comparator_fails_closed():
    rule = {"type": "count_threshold", "source": "completedCourses", "comparator": "?", "threshold": 2}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completedCourses": []})
    )
    assert result.ok is False
    assert "unknown_comparator: ?" in result.error


async def test_count_threshold_missing_facts_source_fails_closed():
    rule = {"type": "count_threshold", "source": "completedCourses", "comparator": ">=", "threshold": 2}
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts={}))
    assert result.ok is False
    assert "facts_source_missing: completedCourses" in result.error


async def test_count_threshold_wrong_shape_facts_source_fails_closed():
    rule = {"type": "count_threshold", "source": "completedCourses", "comparator": ">=", "threshold": 2}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completedCourses": "not a list"})
    )
    assert result.ok is False
    assert "facts_source_wrong_shape: completedCourses" in result.error


async def test_count_threshold_without_filter_counts_all():
    rule = {"type": "count_threshold", "source": "completedCourses", "comparator": "==", "threshold": 3}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completedCourses": [{}, {}, {}]})
    )
    assert result.ok is True
    assert result.data["count"] == 3
    assert result.data["satisfied"] is True


# -- field_comparison ------------------------------------------------------


async def test_field_comparison_computes_correctly():
    rule = {"type": "field_comparison", "source": "profile", "field": "gpa", "comparator": ">=", "threshold": 80}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"profile": {"gpa": 85.5}})
    )
    assert result.ok is True
    assert result.data == {
        "type": "field_comparison",
        "value": 85.5,
        "comparator": ">=",
        "threshold": 80,
        "satisfied": True,
    }


async def test_field_comparison_missing_required_field_fails_closed():
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(
            rule={"type": "field_comparison", "source": "profile", "comparator": ">=", "threshold": 80}, facts={}
        )
    )
    assert result.ok is False
    assert "field_required" in result.error


async def test_field_comparison_unknown_comparator_fails_closed():
    rule = {"type": "field_comparison", "source": "profile", "field": "gpa", "comparator": "<>", "threshold": 80}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"profile": {"gpa": 85}})
    )
    assert result.ok is False
    assert "unknown_comparator: <>" in result.error


async def test_field_comparison_missing_facts_source_fails_closed():
    rule = {"type": "field_comparison", "source": "profile", "field": "gpa", "comparator": ">=", "threshold": 80}
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts={}))
    assert result.ok is False
    assert "facts_source_missing: profile" in result.error


async def test_field_comparison_wrong_shape_facts_source_fails_closed():
    rule = {"type": "field_comparison", "source": "profile", "field": "gpa", "comparator": ">=", "threshold": 80}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"profile": [1, 2, 3]})
    )
    assert result.ok is False
    assert "facts_source_wrong_shape: profile" in result.error


async def test_field_comparison_non_numeric_value_fails_closed():
    rule = {"type": "field_comparison", "source": "profile", "field": "gpa", "comparator": ">=", "threshold": 80}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"profile": {"gpa": "excellent"}})
    )
    assert result.ok is False
    assert "non_numeric_field_value: profile.gpa" in result.error


async def test_field_comparison_not_satisfied():
    rule = {"type": "field_comparison", "source": "profile", "field": "gpa", "comparator": ">=", "threshold": 80}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"profile": {"gpa": 60}})
    )
    assert result.ok is True
    assert result.data["satisfied"] is False


# -- comparator correctness (all six, not just coverage) --------------------


@pytest.mark.parametrize(
    ("comparator", "value", "threshold", "expected"),
    [
        (">=", 5, 5, True),
        (">=", 4, 5, False),
        (">", 6, 5, True),
        (">", 5, 5, False),
        ("<=", 5, 5, True),
        ("<=", 6, 5, False),
        ("<", 4, 5, True),
        ("<", 5, 5, False),
        ("==", 5, 5, True),
        ("==", 4, 5, False),
        ("!=", 4, 5, True),
        ("!=", 5, 5, False),
    ],
)
async def test_every_comparator(comparator, value, threshold, expected):
    rule = {"type": "field_comparison", "source": "x", "field": "v", "comparator": comparator, "threshold": threshold}
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"x": {"v": value}})
    )
    assert result.ok is True
    assert result.data["satisfied"] is expected


# -- expression (docs/agent/CALCULATION_VALIDATION_REASONING_BLOCK_PLAN.md Part 1) --


async def test_expression_happy_path_end_to_end():
    """160 minus the sum of completed credits -- the credits-remaining case
    this rule type was added to cover."""
    rule = {
        "type": "expression",
        "expression": {
            "op": "subtract",
            "left": {"const": 160},
            "right": {"op": "sum", "of": {"ref": "completed_courses"}, "field": "credits_earned"},
        },
    }
    facts = {"completed_courses": [{"credits_earned": 3.5}, {"credits_earned": 2.0}]}
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts=facts))
    assert result.ok is True
    assert result.data["type"] == "expression"
    assert result.data["result"] == 154.5
    assert result.data["trace"] == [
        "sum(ref:completed_courses.credits_earned) = 5.5",
        "160 - 5.5 = 154.5",
    ]
    assert result.certainty.basis == "official_record"
    assert result.certainty.confidence == 1.0


async def test_expression_missing_expression_key_fails_closed():
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule={"type": "expression"}, facts={}))
    assert result.ok is False
    assert "expression_required" in result.error


async def test_expression_malformed_shape_fails_closed():
    """Doesn't even parse as an `ExpressionNode` -- more than one of
    const/ref/op set."""
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(
            rule={"type": "expression", "expression": {"const": 1, "ref": "x"}}, facts={"x": 1}
        )
    )
    assert result.ok is False
    assert "invalid_expression_shape" in result.error


async def test_expression_validation_failure_path():
    """Parses fine, but references a `ref` that isn't in `facts` --
    `validate_expression_tree` catches this before evaluation ever runs."""
    rule = {
        "type": "expression",
        "expression": {"op": "sum", "of": {"ref": "nonexistent"}, "field": "credits"},
    }
    result = await run_apply_deterministic_rule(ApplyDeterministicRuleInput(rule=rule, facts={}))
    assert result.ok is False
    assert "expression_validation_failed" in result.error
    assert "nonexistent" in result.error


async def test_expression_evaluation_failure_path():
    """Structurally valid, but a runtime surprise (non-numeric field value)
    only detectable at evaluation time."""
    rule = {
        "type": "expression",
        "expression": {"op": "sum", "of": {"ref": "completed_courses"}, "field": "credits_earned"},
    }
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(rule=rule, facts={"completed_courses": [{"credits_earned": "three"}]})
    )
    assert result.ok is False
    assert "expression_evaluation_failed" in result.error


async def test_expression_does_not_affect_existing_rule_types():
    """The 3 existing rule types stay exactly as they were -- adding
    `expression` to `_HANDLERS` doesn't change their dispatch."""
    result = await run_apply_deterministic_rule(
        ApplyDeterministicRuleInput(
            rule={"type": "sum_threshold", "source": "x", "field": "v", "comparator": ">=", "threshold": 1},
            facts={"x": [{"v": 2}]},
        )
    )
    assert result.ok is True
    assert result.data["type"] == "sum_threshold"
