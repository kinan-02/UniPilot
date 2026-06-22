"""Unit tests for elective pool prefix enrichment."""

from __future__ import annotations

from app.curriculum.pool_course_enrichment import (
    enrich_pool_documents_for_explorer,
    map_prefix_catalog_courses_to_pools,
    pools_needing_prefix_enrichment,
    resolve_pool_allowed_prefixes,
)
from app.curriculum.rule_dsl import summarize_elective_bucket


def test_resolve_pool_allowed_prefixes_from_known_suffix():
    pool = {
        "requirementGroupId": "009216-1-000:elective-faculty-pool",
        "ruleExpression": {"type": "course_pool", "operator": "min_credits"},
    }
    assert resolve_pool_allowed_prefixes(pool, program_code="009216-1-000") == [
        "0094",
        "0095",
        "0096",
        "0097",
    ]


def test_resolve_pool_allowed_prefixes_from_notes():
    pool = {
        "requirementGroupId": "009216-1-000:custom-pool",
        "notes": ["Courses with prefix 094/095 only."],
        "ruleExpression": {"type": "course_pool"},
    }
    assert resolve_pool_allowed_prefixes(pool, program_code="009216-1-000") == ["0094", "0095"]


def test_enrich_behavior_chain_fallback_when_export_empty():
    behavior_pool = {
        "requirementGroupId": "009118-1-000:is-behavior-science-chain",
        "courseReferences": [],
        "ruleExpression": {
            "type": "course_pool",
            "operator": "choose_n",
            "chooseCount": 1,
            "chain": "behavior_science",
        },
    }
    enriched = enrich_pool_documents_for_explorer(
        [behavior_pool],
        program_code="009118-1-000",
        prefix_courses_by_pool={},
        courses_truncated=False,
    )
    numbers = {ref["courseNumber"] for ref in enriched[0]["courseReferences"]}
    assert numbers == {"0960600", "0960620"}


def test_enrich_focus_chain_fallback_when_export_empty():
    focus_pool = {
        "requirementGroupId": "009118-1-000:is-focus-chain-ml",
        "courseReferences": [],
        "ruleExpression": {"type": "course_pool", "operator": "choose_chain", "chooseCount": 3},
    }
    enriched = enrich_pool_documents_for_explorer(
        [focus_pool],
        program_code="009118-1-000",
        prefix_courses_by_pool={},
        courses_truncated=False,
    )
    numbers = {ref["courseNumber"] for ref in enriched[0]["courseReferences"]}
    assert "0970209" in numbers
    assert len(numbers) >= 3


def test_enrich_faculty_pool_unions_ds_pool_and_prefix_catalog():
    ds_pool = {
        "requirementGroupId": "009216-1-000:elective-ds-pool",
        "courseReferences": [
            {"courseNumber": "00940345", "titleHint": "DS elective"},
        ],
        "ruleExpression": {"type": "course_pool", "operator": "min_credits"},
    }
    faculty_pool = {
        "requirementGroupId": "009216-1-000:elective-faculty-pool",
        "ruleExpression": {
            "type": "course_pool",
            "operator": "min_credits",
            "allowedPrefixes": ["0094", "0095", "0096", "0097"],
            "includesPoolSuffix": "elective-ds-pool",
        },
    }
    prefix_courses = [
        {"courseNumber": "00950101", "title": "Faculty A", "credits": 3.0},
    ]
    needed = pools_needing_prefix_enrichment([ds_pool, faculty_pool], program_code="009216-1-000")
    mapped = map_prefix_catalog_courses_to_pools(
        pool_prefixes=needed,
        catalog_courses=prefix_courses,
    )
    enriched = enrich_pool_documents_for_explorer(
        [ds_pool, faculty_pool],
        program_code="009216-1-000",
        prefix_courses_by_pool=mapped,
        courses_truncated=False,
    )
    faculty = next(
        document
        for document in enriched
        if document["requirementGroupId"].endswith("elective-faculty-pool")
    )
    numbers = {ref["courseNumber"] for ref in faculty["courseReferences"]}
    assert numbers == {"00940345", "00950101"}
    assert faculty["explorerCourseListSource"] == "vault_union"


def test_enrich_pool_documents_adds_synthetic_refs():
    pool = {
        "requirementGroupId": "009216-1-000:elective-faculty-pool",
        "ruleExpression": {"type": "course_pool", "operator": "min_credits"},
    }
    prefix_courses = [
        {"courseNumber": "00950101", "title": "Faculty A", "credits": 3.0},
        {"courseNumber": "12345678", "title": "Unrelated", "credits": 3.5},
    ]
    needed = pools_needing_prefix_enrichment([pool], program_code="009216-1-000")
    mapped = map_prefix_catalog_courses_to_pools(
        pool_prefixes=needed,
        catalog_courses=prefix_courses,
    )
    enriched = enrich_pool_documents_for_explorer(
        [pool],
        program_code="009216-1-000",
        prefix_courses_by_pool=mapped,
        courses_truncated=False,
    )

    assert len(enriched[0]["courseReferences"]) == 1
    assert enriched[0]["courseReferences"][0]["courseNumber"] == "00950101"

    summary = summarize_elective_bucket(
        enriched[0],
        program_code="009216-1-000",
        courses_by_number={"00950101": prefix_courses[0]},
    )
    assert summary["courseListSource"] == "prefix_catalog"
    assert summary["courseCount"] == 1
    assert summary["allowedPrefixes"] == ["0094", "0095", "0096", "0097"]
