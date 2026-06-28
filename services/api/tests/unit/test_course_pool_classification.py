"""Tests for course-to-pool classification."""

from __future__ import annotations

from app.services.course_pool_classification import (
    build_mandatory_course_number_keys,
    is_mandatory_curriculum_course,
    resolve_claiming_pool,
)


PROGRAM = "009118-1-000"


def _pool(group_suffix: str, **kwargs):
    doc = {
        "requirementGroupId": f"{PROGRAM}:{group_suffix}",
        "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
        "courseReferences": [],
    }
    doc.update(kwargs)
    return doc


def test_resolve_claiming_pool_prefers_focus_chain_over_additional_prefix():
    focus_pool = _pool(
        "is-focus-chain-performance",
        ruleExpression={"type": "course_pool", "operator": "choose_chain", "chooseCount": 3},
        courseReferences=[{"courseNumber": "00960327"}, {"courseNumber": "00960324"}],
    )
    additional_pool = _pool(
        "is-additional-faculty-electives",
        ruleExpression={"type": "course_pool", "operator": "min_credits", "allowedPrefixes": ["094", "0096"]},
    )
    pools = [additional_pool, focus_pool]

    claimed = resolve_claiming_pool("00960327", pools, program_code=PROGRAM)
    assert claimed is not None
    assert claimed["requirementGroupId"] == f"{PROGRAM}:is-focus-chain-performance"


def test_resolve_claiming_pool_additional_claims_prefix_only_courses():
    focus_pool = _pool(
        "is-focus-chain-performance",
        ruleExpression={"type": "course_pool", "operator": "choose_chain", "chooseCount": 3},
        courseReferences=[{"courseNumber": "00960327"}],
    )
    additional_pool = _pool(
        "is-additional-faculty-electives",
        ruleExpression={"type": "course_pool", "operator": "min_credits", "allowedPrefixes": ["094"]},
    )
    pools = [focus_pool, additional_pool]

    claimed = resolve_claiming_pool("09400101", pools, program_code=PROGRAM)
    assert claimed is not None
    assert claimed["requirementGroupId"] == f"{PROGRAM}:is-additional-faculty-electives"


def test_mandatory_matrix_course_numbers():
    keys = build_mandatory_course_number_keys(
        [
            {
                "courseReferences": [
                    {"courseNumber": "01040031"},
                    {"courseNumber": "104031"},
                    {"courseNumber": "1040065", "alternatives": ["1040016"]},
                ]
            }
        ]
    )
    assert is_mandatory_curriculum_course("01040031", keys)
    assert is_mandatory_curriculum_course("104031", keys)
    assert is_mandatory_curriculum_course("1040016", keys)
    assert not is_mandatory_curriculum_course("00940411", keys)
