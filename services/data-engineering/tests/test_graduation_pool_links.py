"""Tests for Phase 15.1 graduation pool link promotion metadata."""

from __future__ import annotations

from app.promotion.dds_production_promoter import map_staging_catalog_rule_to_production
from app.promotion.graduation_pool_links import GRADUATION_LINKED_POOL_TO_CREDIT_BUCKET


def test_map_staging_catalog_rule_adds_linked_credit_bucket_for_ds_pools() -> None:
    for pool_id, bucket_id in GRADUATION_LINKED_POOL_TO_CREDIT_BUCKET.items():
        document = map_staging_catalog_rule_to_production(
            {
                "requirementGroupId": pool_id,
                "programCode": pool_id.split(":")[0],
                "ruleExpression": {"type": "course_pool", "operator": "choose_credits"},
                "stagingKey": f"rule:{pool_id}",
            },
            promotion_run_id="run-1",
            promoted_at="2026-06-20T00:00:00+00:00",
            catalog_version="2025-2026",
        )
        assert document["linkedCreditBucketId"] == bucket_id
        assert document["enforceInGraduationProgress"] is False
        assert document["advisoryOnly"] is True
        assert document["sourceMetadata"]["graduationPoolLinkPhase"] == "15.1"


def test_map_staging_catalog_rule_omits_link_for_semester_matrix() -> None:
    document = map_staging_catalog_rule_to_production(
        {
            "requirementGroupId": "009216-1-000:semester-1-matrix",
            "programCode": "009216-1-000",
            "ruleExpression": {"type": "semester_matrix", "operator": "all_of"},
            "stagingKey": "rule:semester-1",
        },
        promotion_run_id="run-1",
        promoted_at="2026-06-20T00:00:00+00:00",
        catalog_version="2025-2026",
    )
    assert "linkedCreditBucketId" not in document
