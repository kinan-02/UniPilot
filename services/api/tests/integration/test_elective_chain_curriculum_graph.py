"""Integration regression: curriculum graph chain pools for IE and IS tracks."""

from __future__ import annotations

import pytest

from tests.fixtures.elective_chain_fixtures import seed_track_chain_fixtures
from tests.helpers.elective_chain_contract import faculty_contract, iter_contract_pools
from tests.integration.test_semester_plans_integration import (
    create_profile,
    register_access_token,
)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("program_code", "email_prefix"),
    [
        ("009009-1-000", "ie-chain-regression"),
        ("009118-1-000", "is-chain-regression"),
    ],
)
async def test_curriculum_graph_chain_pools_are_populated_for_track(
    auth_client,
    mongo_database,
    program_code: str,
    email_prefix: str,
):
    fixtures = await seed_track_chain_fixtures(mongo_database, program_code=program_code)
    expected = {
        entry["suffix"]: entry
        for entry in iter_contract_pools(faculty_id="dds")
        if entry["programCode"] == program_code
    }

    token = await register_access_token(auth_client, f"{email_prefix}@example.com")
    await create_profile(
        auth_client,
        token,
        degree_id=fixtures["programId"],
        extra={"academicPath": {"trackSlug": fixtures["trackSlug"]}},
    )

    response = await auth_client.get(
        "/graduation-progress/curriculum-graph",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    graph = response.json()["data"]["curriculumGraph"]
    buckets_by_suffix = {
        bucket["groupId"].split(":")[-1]: bucket for bucket in graph["electiveBuckets"]
    }

    for suffix, entry in expected.items():
        bucket = buckets_by_suffix.get(suffix)
        assert bucket is not None, f"missing bucket {program_code}:{suffix}"
        assert bucket["progressDisplay"] == "chain_steps"
        assert bucket["catalogDescription"]
        assert bucket["courseCount"] >= entry["minCourseRefs"]
        assert bucket["courseCount"] <= entry["maxCourseRefs"]
        assert bucket["explorerReady"] is True
        assert len(bucket["courses"]) >= entry["minCourseRefs"]

    dds = faculty_contract("dds") or {}
    deprecated = set(dds.get("deprecatedPoolSuffixes") or [])
    for suffix in deprecated:
        assert suffix not in buckets_by_suffix
