"""Regression tests: API must keep every track's chain pools explorer-ready."""

from __future__ import annotations

from app.curriculum.pool_course_enrichment import (
    FOCUS_CHAIN_FALLBACK_NUMBERS,
    CHOOSE_N_CHAIN_FALLBACK_NUMBERS,
    enrich_pool_documents_for_explorer,
)
from app.curriculum.rule_dsl import resolve_progress_display, summarize_elective_bucket
from app.services.graduation_requirement_links import credit_bucket_id_for_pool
from tests.helpers.elective_chain_contract import faculty_contract, iter_contract_pools


def _refs(numbers: tuple[str, ...]) -> list[dict[str, str]]:
    return [{"courseNumber": number} for number in numbers]


def test_contract_pools_have_enrichment_fallbacks():
    fallbacks = {**CHOOSE_N_CHAIN_FALLBACK_NUMBERS, **FOCUS_CHAIN_FALLBACK_NUMBERS}
    missing = [
        entry["suffix"]
        for entry in iter_contract_pools(faculty_id="dds")
        if entry["suffix"] not in fallbacks
    ]
    assert missing == []


def test_empty_exported_pools_still_populate_via_fallbacks():
    for entry in iter_contract_pools(faculty_id="dds"):
        program_code = entry["programCode"]
        suffix = entry["suffix"]
        operator = entry["operator"]
        pool = {
            "requirementGroupId": f"{program_code}:{suffix}",
            "title": suffix,
            "ruleExpression": {
                "type": "course_pool",
                "operator": operator,
                "chooseCount": 1 if operator == "choose_n" else 3,
            },
            "courseReferences": [],
        }
        enriched = enrich_pool_documents_for_explorer(
            [pool],
            program_code=program_code,
            prefix_courses_by_pool={},
            courses_truncated=False,
        )[0]
        ref_count = len(enriched["courseReferences"])
        assert ref_count >= entry["minCourseRefs"], (
            f"{program_code}:{suffix} fallback produced {ref_count} refs"
        )
        assert ref_count <= entry["maxCourseRefs"], (
            f"{program_code}:{suffix} fallback produced {ref_count} refs (max {entry['maxCourseRefs']})"
        )


def test_summarized_buckets_expose_chain_metadata_for_all_contract_pools():
    fallbacks = {**CHOOSE_N_CHAIN_FALLBACK_NUMBERS, **FOCUS_CHAIN_FALLBACK_NUMBERS}

    for entry in iter_contract_pools(faculty_id="dds"):
        program_code = entry["programCode"]
        suffix = entry["suffix"]
        numbers = fallbacks[suffix]
        pool = {
            "requirementGroupId": f"{program_code}:{suffix}",
            "title": suffix,
            "catalogDescription": f"Catalog text for {suffix}",
            "ruleExpression": {
                "type": "course_pool",
                "operator": entry["operator"],
                "chooseCount": 1 if entry["operator"] == "choose_n" else 3,
            },
            "courseReferences": _refs(numbers),
        }
        courses_by_number = {
            number.zfill(8): {
                "courseNumber": number.zfill(8),
                "title": f"Course {number}",
                "credits": 3.0,
            }
            for number in numbers
        }
        summary = summarize_elective_bucket(
            pool,
            program_code=program_code,
            courses_by_number=courses_by_number,
            linked_credit_bucket_id=credit_bucket_id_for_pool(
                program_code=program_code,
                pool_document=pool,
            ),
        )
        assert summary["progressDisplay"] == "chain_steps"
        assert summary["catalogDescription"] == pool["catalogDescription"]
        assert summary["courseCount"] >= entry["minCourseRefs"]
        assert summary["explorerReady"] is True
        assert credit_bucket_id_for_pool(program_code=program_code, pool_document=pool)


def test_deprecated_ie_focus_pool_not_linked():
    from app.services.graduation_requirement_links import EXPLORER_POOL_CREDIT_BUCKET_SUFFIX

    dds = faculty_contract("dds") or {}
    for suffix in dds.get("deprecatedPoolSuffixes") or []:
        assert suffix not in EXPLORER_POOL_CREDIT_BUCKET_SUFFIX


def test_resolve_progress_display_chain_steps_for_all_contract_operators():
    for entry in iter_contract_pools(faculty_id="dds"):
        pool = {
            "requirementGroupId": f"{entry['programCode']}:{entry['suffix']}",
            "ruleExpression": {
                "type": "course_pool",
                "operator": entry["operator"],
            },
        }
        assert (
            resolve_progress_display(pool, program_code=entry["programCode"]) == "chain_steps"
        )
