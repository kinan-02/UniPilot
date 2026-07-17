"""Unit tests for the expression-tree vocabulary
(docs/agent/CALCULATION_VALIDATION_REASONING_BLOCK_PLAN.md Part 1) --
one operator at a time, `validate_expression_tree`'s own structural checks,
and a multi-level tree exercising the full validate+evaluate path together.
"""

from __future__ import annotations

import pytest

from app.agent_core.tools.primitives.expression_tree import (
    FACTS_DEFECT_PREFIX,
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


def test_validate_rejects_aggregate_over_a_non_list_ref():
    """Regression (live, 2026-07-15): the calc-validation model summed over
    `creditBreakdown` -- the credit-BUCKETS dict -- instead of the
    `completedCourses` list sitting in the same facts. Validation passed (the
    ref exists), so it only blew up at EVALUATION time inside the tool call as
    `of_not_a_list`, which is unrepairable: the block never retries a validated
    tree. The step failed, and a retrieval block then did the arithmetic
    in-model and asserted a wrong total (63.0 vs 62.5).

    Catching it at validation time hands the bounded repair loop a fixable
    error instead."""
    node = ExpressionNode(op="sum", of=ExpressionNode(ref="creditBreakdown"), field="creditsEarned")
    facts = {
        "creditBreakdown": {"required": 107.5, "electives": 35.5},
        "completedCourses": [{"creditsEarned": 4.0}],
    }

    errors = validate_expression_tree(node, facts=facts)

    assert any("creditBreakdown" in error and "not a list" in error for error in errors), errors
    # The message must point at the list-valued facts, so repair can succeed.
    assert any("completedCourses" in error for error in errors), errors


def test_validate_rejects_sum_over_a_field_absent_from_the_records():
    """Regression (live, ISE credits_remaining): the calc-validation model
    summed `field: "deficit"` over the `completedCourses` list -- a field the
    course records don't carry -- so every `record.get("deficit")` was None and
    the tool died at EVALUATION time as `non_numeric_field_value`, which is
    unrepairable (the block never retries a validated tree). The step failed and
    the composition then reported a hallucinated earned-credits total.

    Catching it at validation time, and naming the numeric fields that DO exist,
    hands the bounded repair loop a fixable error."""
    node = ExpressionNode(op="sum", of=ExpressionNode(ref="completedCourses"), field="deficit")
    facts = {
        "completedCourses": [
            {"courseNumber": "00940345", "creditsEarned": 4.0, "grade": 88.0},
            {"courseNumber": "00940704", "creditsEarned": 1.5, "grade": 95.0},
        ]
    }

    errors = validate_expression_tree(node, facts=facts)

    assert any("deficit" in error and "numeric" in error for error in errors), errors
    # The message must name the numeric fields available, so repair can switch.
    assert any("creditsEarned" in error for error in errors), errors


def test_records_with_no_numeric_field_at_all_is_a_facts_defect_not_an_expression_error():
    """When the records carry no numbers whatsoever, the expression is not the
    thing that's wrong -- the data is.

    Live (2026-07-16, ise_correctness `credits_remaining`): `requiredCourses`
    came back as 29 records keyed on exactly `(id, nodeType)`. No credits. The
    expression that tried to sum credits over them was semantically CORRECT, and
    the bounded repair loop spent its attempts rewriting it anyway, because a
    missing field and a misnamed one arrived as the same error. Repair was told
    to switch to one of `numeric fields available: []`.

    No edit to the expression can fix this, so it must be reported as what it is
    and never sent to repair -- distinct from
    `test_sum_non_numeric_field_value_fails_closed`, where real numeric fields
    exist and switching to one IS the fix.
    """
    node = ExpressionNode(op="sum", of=ExpressionNode(ref="requiredCourses"), field="credits")
    facts = {
        "requiredCourses": [
            {"id": "00940345", "nodeType": "course"},
            {"id": "00940704", "nodeType": "course"},
        ]
    }

    errors = validate_expression_tree(node, facts=facts)

    assert any(error.startswith(FACTS_DEFECT_PREFIX) for error in errors), errors
    # It names what the records DO carry, so the caller can see what retrieval
    # actually fetched -- and that `credits` was never among it.
    assert any("id" in error and "nodeType" in error for error in errors), errors


def test_validate_allows_aggregate_over_a_list_ref():
    node = ExpressionNode(op="sum", of=ExpressionNode(ref="completedCourses"), field="creditsEarned")
    facts = {"completedCourses": [{"creditsEarned": 4.0}]}

    assert validate_expression_tree(node, facts=facts) == []


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


# --- Groundedness: an expression must read the facts it was handed ----------
# Regression for the 2026-07-16 ise_correctness laundering chain: a fabricated
# in-model total (63.5; the real total is 62.5) was fed back as a literal, so
# the engine computed a flawless 155 - 63.5 = 91.5 and the wrong number reached
# the student wearing the calculator's authority.


def test_all_const_expression_is_rejected_when_facts_were_supplied():
    # The exact tree from the live run.
    node = ExpressionNode(op="subtract", left=ExpressionNode(const=155), right=ExpressionNode(const=63.5))
    facts = {"totalCreditsRequired": 155.0, "completedCourses": [{"creditsEarned": 4.0}]}

    errors = validate_expression_tree(node, facts=facts)

    assert errors, "an expression that reads none of its facts must not validate"
    assert "reads none of the supplied facts" in errors[0]
    # The repair pass needs somewhere concrete to go.
    assert "completedCourses" in errors[0]


def test_all_const_expression_is_allowed_when_no_facts_were_supplied():
    # Nothing to ignore, so there is nothing to catch -- the rule must not fire.
    node = ExpressionNode(op="subtract", left=ExpressionNode(const=155), right=ExpressionNode(const=63.5))

    assert validate_expression_tree(node, facts={}) == []


def test_a_single_ref_anywhere_grounds_the_tree():
    # const operands stay legal next to a ref -- only a tree with NO ref at all
    # is ungrounded.
    node = ExpressionNode(
        op="compare",
        left=ExpressionNode(ref="totalCreditsRequired"),
        comparator=">=",
        right=ExpressionNode(const=100),
    )

    assert validate_expression_tree(node, facts={"totalCreditsRequired": 155.0}) == []


def test_groundedness_is_not_reported_on_a_structurally_invalid_tree():
    # A bad ref is the actionable error; adding "no refs" on top would be noise.
    node = ExpressionNode(op="subtract", left=ExpressionNode(ref="nope"), right=ExpressionNode(const=1))

    errors = validate_expression_tree(node, facts={"real": 1})

    assert len(errors) == 1
    assert "not found in facts" in errors[0]


# --- Arithmetic operand coercion -------------------------------------------
#
# CAUGHT LIVE (2026-07-16, `credits_remaining`). The degree's total credits
# reached the calculator as the STRING "155": an interpretation step read it off
# the ISE track wiki page, and an interpretation's `answer` is a string by
# schema. Every number ever read out of prose arrives this way.


def test_subtract_accepts_a_number_that_arrived_as_a_string_from_prose():
    facts = {"total": "155", "earned": 62.5}
    node = ExpressionNode(op="subtract", left=ExpressionNode(ref="total"), right=ExpressionNode(ref="earned"))

    result, _trace, errors = evaluate_expression(node, facts)

    assert errors == []
    assert result == 92.5


def test_compare_does_not_coerce_so_a_course_number_keeps_its_leading_zeros():
    """A course number IS a numeric string. Coercing `"00940224"` to 940224.0
    would silently destroy the leading zeros that every prerequisite and
    requirement match keys on -- which is why coercion lives in arithmetic
    operand position only, where intent is unambiguous, and never here.
    """
    facts = {"course": "00940224"}
    node = ExpressionNode(
        op="compare",
        comparator="==",
        left=ExpressionNode(ref="course"),
        right=ExpressionNode(const="00940224"),
    )

    result, _trace, errors = evaluate_expression(node, facts)

    assert errors == []
    assert result is True


def test_a_non_numeric_operand_error_names_the_operand_and_what_it_resolved_to():
    """An error a model cannot act on is retried verbatim.

    Live, `non_numeric_operand: subtract` named neither operand; the model
    re-emitted the identical expression, and the Planner then replanned it into
    a third identical failure.
    """
    facts = {"1d": {"answer": "155"}, "1e": 62.5}
    node = ExpressionNode(op="subtract", left=ExpressionNode(ref="1d"), right=ExpressionNode(ref="1e"))

    _result, _trace, errors = evaluate_expression(node, facts)

    assert len(errors) == 1
    error = errors[0]
    assert "non_numeric_operand: subtract" in error
    assert "ref '1d'" in error, "the failing operand must be named"
    assert "dict" in error, "and what it actually resolved to"
    assert "1e" in error, "available facts guide the repair"


def test_a_genuinely_non_numeric_string_still_fails():
    facts = {"semester": "2025-1", "n": 1}
    node = ExpressionNode(op="add", left=ExpressionNode(ref="semester"), right=ExpressionNode(ref="n"))

    _result, _trace, errors = evaluate_expression(node, facts)

    assert any("non_numeric_operand" in e for e in errors)
