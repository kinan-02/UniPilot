"""Unit tests for the expression-tree vocabulary
(docs/agent/CALCULATION_VALIDATION_REASONING_BLOCK_PLAN.md Part 1) --
one operator at a time, `validate_expression_tree`'s own structural checks,
and a multi-level tree exercising the full validate+evaluate path together.
"""

from __future__ import annotations

import pytest

from app.agent_core.tools.primitives.expression_tree import (
    ExpressionNode,
    evaluate_expression,
    validate_expression_tree,
)

# -- one test per operator: happy path + its own failure mode ---------------


def test_sum_happy_path():
    node = ExpressionNode(op="sum", of=ExpressionNode(ref="completed_courses"), field="credits_earned")
    facts = {"completed_courses": [{"credits_earned": 3.5}, {"credits_earned": 2.0}]}
    assert validate_expression_tree(node, facts=facts) == []
    value, trace, errors = evaluate_expression(node, facts)
    assert errors == []
    assert value == 5.5
    assert trace == ["sum(ref:completed_courses.credits_earned) = 5.5"]


def test_sum_non_numeric_field_value_fails_closed():
    node = ExpressionNode(op="sum", of=ExpressionNode(ref="completed_courses"), field="credits_earned")
    facts = {"completed_courses": [{"credits_earned": "three"}]}
    value, trace, errors = evaluate_expression(node, facts)
    assert value is None
    assert any("non_numeric_field_value" in error for error in errors)


def test_count_happy_path():
    node = ExpressionNode(op="count", of=ExpressionNode(ref="completed_courses"), filter={"status": "completed"})
    facts = {
        "completed_courses": [
            {"status": "completed"},
            {"status": "completed"},
            {"status": "in_progress"},
        ]
    }
    assert validate_expression_tree(node, facts=facts) == []
    value, trace, errors = evaluate_expression(node, facts)
    assert errors == []
    assert value == 2
    assert trace == ["count(ref:completed_courses) = 2"]


def test_count_missing_ref_fails_closed():
    node = ExpressionNode(op="count", of=ExpressionNode(ref="nonexistent"))
    value, trace, errors = evaluate_expression(node, {})
    assert value is None
    assert errors == ["ref_not_found: nonexistent"]


def test_average_happy_path():
    node = ExpressionNode(op="average", of=ExpressionNode(ref="grades"), field="score")
    facts = {"grades": [{"score": 80}, {"score": 90}]}
    assert validate_expression_tree(node, facts=facts) == []
    value, trace, errors = evaluate_expression(node, facts)
    assert errors == []
    assert value == 85.0


def test_average_of_empty_set_fails_closed_not_zero():
    """Distinct from `sum`'s empty-set-is-zero: an average of zero items is
    undefined, not zero."""
    node = ExpressionNode(op="average", of=ExpressionNode(ref="grades"), field="score")
    value, trace, errors = evaluate_expression(node, {"grades": []})
    assert value is None
    assert errors == ["average_of_empty_set"]


def test_add_happy_path():
    node = ExpressionNode(op="add", left=ExpressionNode(const=2), right=ExpressionNode(const=3))
    value, trace, errors = evaluate_expression(node, {})
    assert errors == []
    assert value == 5
    assert trace == ["2 + 3 = 5"]


def test_subtract_happy_path():
    node = ExpressionNode(op="subtract", left=ExpressionNode(const=160), right=ExpressionNode(const=3.5))
    value, trace, errors = evaluate_expression(node, {})
    assert errors == []
    assert value == 156.5


def test_multiply_happy_path():
    node = ExpressionNode(op="multiply", left=ExpressionNode(const=4), right=ExpressionNode(const=2.5))
    value, trace, errors = evaluate_expression(node, {})
    assert errors == []
    assert value == 10.0


def test_divide_happy_path():
    node = ExpressionNode(op="divide", left=ExpressionNode(const=10), right=ExpressionNode(const=4))
    value, trace, errors = evaluate_expression(node, {})
    assert errors == []
    assert value == 2.5


def test_divide_by_zero_fails_closed_never_inf_or_nan():
    node = ExpressionNode(op="divide", left=ExpressionNode(const=10), right=ExpressionNode(const=0))
    value, trace, errors = evaluate_expression(node, {})
    assert value is None
    assert errors == ["division_by_zero"]


def test_compare_happy_path():
    node = ExpressionNode(op="compare", left=ExpressionNode(const=130), comparator=">=", right=ExpressionNode(const=120))
    value, trace, errors = evaluate_expression(node, {})
    assert errors == []
    assert value is True
    assert trace == ["130 >= 120 = True"]


def test_compare_unknown_comparator_fails_closed():
    node = ExpressionNode(op="compare", left=ExpressionNode(const=1), comparator="~=", right=ExpressionNode(const=1))
    value, trace, errors = evaluate_expression(node, {})
    assert value is None
    assert errors == ["unknown_comparator: ~="]


# -- validate_expression_tree's own structural checks ------------------------


def test_validate_depth_exceeded():
    node = ExpressionNode(const=1)
    for _ in range(10):
        node = ExpressionNode(op="add", left=node, right=ExpressionNode(const=1))
    errors = validate_expression_tree(node, facts={}, max_depth=3)
    assert any("max_depth" in error for error in errors)


def test_validate_node_count_exceeded():
    node = ExpressionNode(const=1)
    for _ in range(10):
        node = ExpressionNode(op="add", left=node, right=ExpressionNode(const=1))
    errors = validate_expression_tree(node, facts={}, max_nodes=5)
    assert any("max_nodes" in error for error in errors)


def test_validate_unknown_ref():
    node = ExpressionNode(op="sum", of=ExpressionNode(ref="completedCourses"), field="credits")
    errors = validate_expression_tree(node, facts={"completed_courses": []})
    assert len(errors) == 1
    assert "ref 'completedCourses' not found in facts" in errors[0]


def test_validate_missing_required_sibling_field_for_sum():
    node = ExpressionNode(op="sum", of=ExpressionNode(ref="completed_courses"))  # no `field`
    errors = validate_expression_tree(node, facts={"completed_courses": []})
    assert any("'field' is required" in error for error in errors)


def test_validate_missing_of_for_count():
    node = ExpressionNode(op="count")
    errors = validate_expression_tree(node, facts={})
    assert any("'of' is required" in error for error in errors)


def test_validate_missing_left_and_right_for_binary_op():
    node = ExpressionNode(op="subtract")
    errors = validate_expression_tree(node, facts={})
    assert any("left and right required" in error for error in errors)


def test_validate_missing_comparator_for_compare():
    node = ExpressionNode(op="compare", left=ExpressionNode(const=1), right=ExpressionNode(const=2))
    errors = validate_expression_tree(node, facts={})
    assert any("unknown comparator" in error for error in errors)


def test_validate_ambiguous_node_more_than_one_of_const_ref_op_set():
    """The pydantic model_validator normally blocks this at construction
    time -- `model_construct` bypasses it to exercise
    `validate_expression_tree`'s own defense-in-depth check directly, as if
    a node were mutated or built without going through `model_validate`."""
    node = ExpressionNode.model_construct(const=1, ref="x", op=None)
    errors = validate_expression_tree(node, facts={"x": 1})
    assert any("exactly one of const/ref/op" in error for error in errors)


def test_validate_no_shape_set_at_all():
    node = ExpressionNode.model_construct(const=None, ref=None, op=None)
    errors = validate_expression_tree(node, facts={})
    assert any("exactly one of const/ref/op" in error for error in errors)


def test_pydantic_model_validator_rejects_ambiguous_node_at_construction_time():
    with pytest.raises(Exception):
        ExpressionNode(const=1, ref="x")


# -- multi-level tree: the credits-remaining example -------------------------


def test_credits_remaining_multi_level_tree_validate_and_evaluate():
    """160 minus the sum of completed credits -- exercises validate and
    evaluate together, asserting the full trace content, not just the final
    number."""
    node = ExpressionNode(
        op="subtract",
        left=ExpressionNode(const=160),
        right=ExpressionNode(op="sum", of=ExpressionNode(ref="completed_courses"), field="credits_earned"),
    )
    facts = {"completed_courses": [{"credits_earned": 3.5}, {"credits_earned": 2.0}]}

    assert validate_expression_tree(node, facts=facts) == []

    value, trace, errors = evaluate_expression(node, facts)
    assert errors == []
    assert value == 154.5
    assert trace == [
        "sum(ref:completed_courses.credits_earned) = 5.5",
        "160 - 5.5 = 154.5",
    ]
