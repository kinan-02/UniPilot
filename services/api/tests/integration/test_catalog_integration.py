"""Integration tests for Phase 13 read-only catalog API."""

import pytest

from tests.fixtures.catalog_production_fixtures import (
    ADVISORY_RULE_ID,
    EXCLUDED_COURSE,
    HARD_REQUIREMENT_ID,
    KNOWN_COURSE,
    KNOWN_PROGRAM,
    seed_catalog_production_fixtures,
)

VALID_PASSWORD = "StrongPass123!"


async def register_access_token(client, email: str) -> str:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": VALID_PASSWORD},
    )
    assert response.status_code == 201
    return response.json()["data"]["accessToken"]


@pytest.mark.asyncio
async def test_catalog_requires_auth(auth_client):
    response = await auth_client.get("/catalog/courses")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_courses_pagination(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-list@example.com")

    response = await auth_client.get(
        "/catalog/courses?limit=1&offset=0",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 2
    assert len(body["data"]["items"]) == 1
    assert body["data"]["limit"] == 1


@pytest.mark.asyncio
async def test_search_by_course_number(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-search-number@example.com")

    response = await auth_client.get(
        f"/catalog/courses?courseNumber={KNOWN_COURSE}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["courseNumber"] == KNOWN_COURSE


@pytest.mark.asyncio
async def test_search_by_hebrew_title(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-search-title@example.com")

    response = await auth_client.get(
        "/catalog/courses?q=דיסקרטית",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(item["courseNumber"] == KNOWN_COURSE for item in items)


@pytest.mark.asyncio
async def test_get_course_detail(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-detail@example.com")

    response = await auth_client.get(
        f"/catalog/courses/{KNOWN_COURSE}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    course = response.json()["data"]["course"]
    assert course["courseNumber"] == KNOWN_COURSE
    assert course["metadata"]["degreeRequirementsInferred"] is False
    assert "productionKey" not in course


@pytest.mark.asyncio
async def test_get_missing_course_returns_404(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-missing@example.com")

    response = await auth_client.get(
        "/catalog/courses/00999999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_invalid_course_number_returns_400(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-invalid@example.com")

    response = await auth_client.get(
        "/catalog/courses/123",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_include_offerings_on_course_detail(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-offerings@example.com")

    response = await auth_client.get(
        f"/catalog/courses/{KNOWN_COURSE}?includeOfferings=true",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    offerings = response.json()["data"]["course"]["offerings"]
    assert len(offerings) == 1
    assert offerings[0]["semesterCode"] == 201


@pytest.mark.asyncio
async def test_offerings_filter_by_semester_code(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-offering-filter@example.com")

    response = await auth_client.get(
        f"/catalog/courses/{KNOWN_COURSE}/offerings?semesterCode=201",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 1


@pytest.mark.asyncio
async def test_list_degree_programs(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-programs@example.com")

    response = await auth_client.get(
        "/catalog/degree-programs",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 1


@pytest.mark.asyncio
async def test_get_degree_program(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-program@example.com")

    response = await auth_client.get(
        f"/catalog/degree-programs/{KNOWN_PROGRAM}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    program = response.json()["data"]["program"]
    assert program["programCode"] == KNOWN_PROGRAM
    assert program["totalCredits"] == 155.0


@pytest.mark.asyncio
async def test_missing_degree_program_returns_404(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-program-missing@example.com")

    response = await auth_client.get(
        "/catalog/degree-programs/009999-1-000",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_hard_requirements_exclude_advisory_rules(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-hard-reqs@example.com")

    response = await auth_client.get(
        f"/catalog/degree-programs/{KNOWN_PROGRAM}/requirements",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    requirements = response.json()["data"]["requirements"]
    assert len(requirements) == 1
    assert requirements[0]["requirementGroupId"] == HARD_REQUIREMENT_ID
    assert requirements[0]["requirementEnforcement"] == "hard"
    assert all(item["requirementGroupId"] != ADVISORY_RULE_ID for item in requirements)


@pytest.mark.asyncio
async def test_advisory_rules_are_non_enforced(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-advisory@example.com")

    response = await auth_client.get(
        f"/catalog/degree-programs/{KNOWN_PROGRAM}/advisory-rules",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    rules = response.json()["data"]["advisoryRules"]
    assert len(rules) == 1
    assert rules[0]["requirementGroupId"] == ADVISORY_RULE_ID
    assert rules[0]["advisoryOnly"] is True
    assert rules[0]["enforceInGraduationProgress"] is False
    assert rules[0]["notHardRequirement"] is True


@pytest.mark.asyncio
async def test_catalog_summary_separates_hard_and_advisory(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-summary@example.com")

    response = await auth_client.get(
        f"/catalog/degree-programs/{KNOWN_PROGRAM}/catalog-summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    summary = response.json()["data"]["catalogSummary"]
    assert summary["counts"]["hardRequirements"] == 1
    assert summary["counts"]["advisoryRules"] == 1
    assert summary["hardRequirements"][0]["requirementEnforcement"] == "hard"
    assert summary["advisoryRules"][0]["notHardRequirement"] is True


@pytest.mark.asyncio
async def test_excluded_course_not_in_fixture(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-excluded@example.com")

    response = await auth_client.get(
        f"/catalog/courses/{EXCLUDED_COURSE}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_limit_max_enforced(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-limit@example.com")

    response = await auth_client.get(
        "/catalog/courses?limit=500",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_list_courses_filtered_by_semester_offerings(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-semester-filter@example.com")

    response = await auth_client.get(
        "/catalog/courses?academicYear=2025&semesterCode=201&limit=50",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert len(items) >= 1
    assert all(item.get("semesterOfferingSummary") for item in items)
    assert items[0]["semesterOfferingSummary"]["semesterCode"] == 201


@pytest.mark.asyncio
async def test_semester_filter_requires_both_params(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-semester-pair@example.com")

    response = await auth_client.get(
        "/catalog/courses?academicYear=2025",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
