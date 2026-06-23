"""Cross-system edge-case integration tests (empty DB, validation, dedupe, boundaries)."""

from __future__ import annotations

import pytest

from app.config import get_settings
from tests.fixtures.catalog_production_fixtures import (
    KNOWN_COURSE,
    KNOWN_PROGRAM,
    seed_catalog_production_fixtures,
)
from tests.integration.test_catalog_integration import register_access_token

VALID_PASSWORD = "StrongPass123!"


@pytest.mark.asyncio
async def test_empty_catalog_returns_empty_lists_not_errors(auth_client, mongo_database):
    token = await register_access_token(auth_client, "edge-empty-catalog@example.com")

    courses = await auth_client.get(
        "/catalog/courses?limit=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert courses.status_code == 200
    assert courses.json()["data"]["total"] == 0
    assert courses.json()["data"]["items"] == []

    programs = await auth_client.get(
        "/catalog/degree-programs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert programs.status_code == 200
    assert programs.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_pagination_offset_beyond_total_returns_empty_page(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-offset@example.com")

    response = await auth_client.get(
        "/catalog/courses?limit=10&offset=9999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["total"] == 3
    assert body["items"] == []


@pytest.mark.asyncio
async def test_invalid_program_code_format_returns_400(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-bad-program@example.com")

    for path in [
        "/catalog/degree-programs/not-a-code/requirements",
        "/catalog/degree-programs/123/requirements",
        "/catalog/degree-programs/009216-1-000/extra",
    ]:
        response = await auth_client.get(
            path,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code in {400, 404}, path


@pytest.mark.asyncio
async def test_batch_offerings_rejects_empty_course_list(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-empty-batch@example.com")

    response = await auth_client.get(
        "/catalog/offerings?courseNumbers=,,",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_batch_offerings_rejects_invalid_course_number(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-invalid-batch@example.com")

    response = await auth_client.get(
        f"/catalog/offerings?courseNumbers={KNOWN_COURSE},123",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_batch_offerings_rejects_too_many_courses(auth_client, mongo_database, monkeypatch):
    monkeypatch.setenv("CATALOG_OFFERINGS_BATCH_MAX", "2")
    from app.config import get_settings

    get_settings.cache_clear()
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-batch-max@example.com")

    response = await auth_client.get(
        "/catalog/offerings?courseNumbers=00940345,02340117,01040031",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400
    assert "at most 2" in response.json()["error"]


@pytest.mark.asyncio
async def test_batch_offerings_missing_course_returns_empty_slot(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-missing-offering@example.com")

    response = await auth_client.get(
        f"/catalog/offerings?courseNumbers={KNOWN_COURSE},00999999&academicYear=2025&semesterCode=201",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    by_number = response.json()["data"]["offeringsByCourseNumber"]
    assert len(by_number[KNOWN_COURSE]) == 1
    assert by_number["00999999"] == []


@pytest.mark.asyncio
async def test_invalid_semester_code_on_list_returns_400(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-bad-semester@example.com")

    response = await auth_client.get(
        "/catalog/courses?academicYear=2025&semesterCode=999",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_search_no_match_returns_empty_items(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-no-match@example.com")

    response = await auth_client.get(
        "/catalog/courses?q=zzzznonexistentcoursexyz",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["items"] == []


@pytest.mark.asyncio
async def test_duplicate_advisory_rules_deduped_at_api_layer(auth_client, mongo_database):
    settings = get_settings()
    group_id = "009216-1-000:semester-1-matrix"
    await seed_catalog_production_fixtures(mongo_database)
    await mongo_database[settings.catalog_rules_collection].insert_one(
        {
            "programCode": KNOWN_PROGRAM,
            "requirementGroupId": group_id,
            "recordType": "catalog_rule",
            "ruleExpression": {"type": "semester_matrix", "semester": 1},
            "advisoryOnly": True,
            "enforceInGraduationProgress": False,
            "courseReferences": [],
            "status": "published",
        }
    )
    token = await register_access_token(auth_client, "edge-dedupe-advisory@example.com")

    response = await auth_client.get(
        f"/catalog/degree-programs/{KNOWN_PROGRAM}/advisory-rules",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    rules = response.json()["data"]["advisoryRules"]
    semester_one = [r for r in rules if r["requirementGroupId"] == group_id]
    assert len(semester_one) == 1


@pytest.mark.asyncio
async def test_graduation_progress_without_profile_returns_404(auth_client):
    token = await register_access_token(auth_client, "edge-no-profile-grad@example.com")

    response = await auth_client.get(
        "/graduation-progress",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_semester_plan_generate_without_profile_returns_404(auth_client):
    token = await register_access_token(auth_client, "edge-no-profile-plan@example.com")

    response = await auth_client.post(
        "/semester-plans/generate",
        headers={"Authorization": f"Bearer {token}"},
        json={"semesterCode": "2025-1"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_register_rejects_weak_password(auth_client):
    response = await auth_client.post(
        "/auth/register",
        json={"email": "weak-pass@example.com", "password": "short"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_catalog_ignores_unknown_query_params(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "edge-unknown-param@example.com")

    response = await auth_client.get(
        "/catalog/courses?limit=5&unknownParam=1",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "expected_status"),
    [
        ("limit=0", 400),
        ("offset=-1", 400),
        ("limit=201", 400),
        ("limit=1&offset=0", 200),
    ],
)
async def test_catalog_pagination_rejects_out_of_bounds(
    auth_client,
    mongo_database,
    query: str,
    expected_status: int,
):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, f"edge-pagination-{query.replace('=', '-')}@example.com")

    response = await auth_client.get(
        f"/catalog/courses?{query}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == expected_status


@pytest.mark.asyncio
async def test_completed_courses_list_empty_page_with_high_offset(auth_client, mongo_database):
    from tests.fixtures.completed_course_fixtures import (
        build_completed_course_payload,
        seed_production_course_fixture,
    )

    catalog = await seed_production_course_fixture(mongo_database)
    token = await register_access_token(auth_client, "edge-cc-high-page@example.com")

    create_response = await auth_client.post(
        "/completed-courses",
        headers={"Authorization": f"Bearer {token}"},
        json=build_completed_course_payload(catalog["courseId"]),
    )
    assert create_response.status_code == 201

    response = await auth_client.get(
        "/completed-courses?page=999&limit=50",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()["data"]
    assert body["completedCourses"] == []
    assert body["pagination"]["total"] == 1


@pytest.mark.asyncio
async def test_register_rejects_extra_unknown_fields(auth_client):
    response = await auth_client.post(
        "/auth/register",
        json={
            "email": "extra-field@example.com",
            "password": VALID_PASSWORD,
            "isAdmin": True,
        },
    )
    assert response.status_code == 400
