"""Tests for Phase 15.1 graduation pool link promotion metadata."""

from __future__ import annotations

from app.promotion.dds_production_promoter import map_staging_advisory_requirement_to_production
from app.promotion.graduation_pool_links import GRADUATION_LINKED_POOL_TO_CREDIT_BUCKET


def test_map_staging_advisory_requirement_adds_linked_credit_bucket_for_ds_pools() -> None:
    for pool_id, bucket_id in GRADUATION_LINKED_POOL_TO_CREDIT_BUCKET.items():
        program_code = pool_id.split(":")[0]
        document = map_staging_advisory_requirement_to_production(
            {
                "programCode": program_code,
                "stagingKey": f"req:{pool_id}",
                "requirementGroup": {
                    "groupId": pool_id,
                    "title": "Pool",
                    "requirementType": "elective",
                    "courseReferences": [],
                    "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
                },
            },
            promotion_run_id="run-1",
            promoted_at="2026-06-20T00:00:00+00:00",
            catalog_version="2025-2026",
        )
        assert document["linkedCreditBucketId"] == bucket_id
        assert document["recordType"] == "advisory_requirement_group"
        assert document["enforceInGraduationProgress"] is False
        assert document["advisoryOnly"] is True
        assert document["sourceMetadata"]["graduationPoolLinkPhase"] == "15.1"


def test_map_staging_advisory_requirement_adds_general_technion_links() -> None:
    document = map_staging_advisory_requirement_to_production(
        {
            "programCode": "009216-1-000",
            "stagingKey": "req:enrichment-pool",
            "requirementGroup": {
                "groupId": "009216-1-000:enrichment-pool",
                "title": "Enrichment pool",
                "requirementType": "elective",
                "courseReferences": [],
                "ruleExpression": {"type": "course_pool", "operator": "min_credits"},
            },
        },
        promotion_run_id="run-1",
        promoted_at="2026-06-20T00:00:00+00:00",
        catalog_version="2025-2026",
    )
    assert document["linkedCreditBucketId"] == "009216-1-000:enrichment"


def test_map_staging_advisory_requirement_adds_general_technion_links_for_cs_program() -> None:
    document = map_staging_advisory_requirement_to_production(
        {
            "programCode": "023023-1-000",
            "stagingKey": "req:enrichment-pool",
            "requirementGroup": {
                "groupId": "023023-1-000:enrichment-pool",
                "title": "Enrichment pool",
                "requirementType": "elective",
                "courseReferences": [],
                "ruleExpression": {"type": "course_pool", "operator": "min_credits"},
            },
        },
        promotion_run_id="run-1",
        promoted_at="2026-06-20T00:00:00+00:00",
        catalog_version="2025-2026",
    )
    assert document["linkedCreditBucketId"] == "023023-1-000:enrichment"


def test_map_staging_advisory_requirement_omits_link_for_semester_matrix() -> None:
    document = map_staging_advisory_requirement_to_production(
        {
            "programCode": "009216-1-000",
            "stagingKey": "req:semester-1",
            "requirementGroup": {
                "groupId": "009216-1-000:semester-1-matrix",
                "title": "Semester 1",
                "requirementType": "core",
                "courseReferences": [],
                "ruleExpression": {"type": "semester_matrix", "operator": "all_of"},
            },
        },
        promotion_run_id="run-1",
        promoted_at="2026-06-20T00:00:00+00:00",
        catalog_version="2025-2026",
    )
    assert "linkedCreditBucketId" not in document
