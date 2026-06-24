"""Integration tests for Phase 13 read-only catalog API."""

import pytest

from tests.fixtures.catalog_production_fixtures import (
    ADVISORY_COUNTS_BY_PROGRAM,
    ADVISORY_RULE_ID,
    ALL_PROGRAMS,
    EXCLUDED_COURSE,
    HARD_REQUIREMENT_ID,
    KNOWN_COURSE,
    KNOWN_PROGRAM,
    TOTAL_ADVISORY_RULES,
    TOTAL_HARD_REQUIREMENTS,
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
async def test_list_academic_faculties_filters_by_program_type(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-faculties-filter@example.com")

    response = await auth_client.get(
        "/catalog/academic-faculties?programType=MSc",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["facultyId"] == "faculty-dds"


@pytest.mark.asyncio
async def test_list_academic_faculties(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-academic-faculties@example.com")

    response = await auth_client.get(
        "/catalog/academic-faculties",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] >= 1
    assert body["data"]["items"][0]["facultyId"] == "faculty-dds"


@pytest.mark.asyncio
async def test_list_path_options_for_bsc_tracks(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-path-options@example.com")

    response = await auth_client.get(
        "/catalog/path-options?facultyId=faculty-dds&programType=BSc&primaryOnly=true",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] == 3
    assert all(item["kind"] == "bsc_track" for item in body["data"]["items"])
    assert all(item.get("linkedDegreeProgramId") for item in body["data"]["items"])


@pytest.mark.asyncio
async def test_list_faculties(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-faculties@example.com")

    response = await auth_client.get(
        "/catalog/faculties",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["total"] >= 1
    assert isinstance(body["data"]["items"], list)


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
    assert body["data"]["total"] == 3
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
    assert response.json()["data"]["total"] == len(ALL_PROGRAMS)


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
    assert len(requirements) == 6
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
    assert len(rules) == ADVISORY_COUNTS_BY_PROGRAM[KNOWN_PROGRAM]
    assert any(rule["requirementGroupId"] == ADVISORY_RULE_ID for rule in rules)
    assert all(rule["advisoryOnly"] is True for rule in rules)
    assert all(rule["enforceInGraduationProgress"] is False for rule in rules)
    assert all(rule["notHardRequirement"] is True for rule in rules)


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
    assert summary["counts"]["hardRequirements"] == 6
    assert summary["counts"]["advisoryRules"] == ADVISORY_COUNTS_BY_PROGRAM[KNOWN_PROGRAM]
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


@pytest.mark.asyncio
async def test_batch_catalog_offerings(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-batch-offerings@example.com")

    response = await auth_client.get(
        f"/catalog/offerings?courseNumbers={KNOWN_COURSE}&academicYear=2025&semesterCode=201",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()["data"]
    assert body["totalCourses"] == 1
    assert KNOWN_COURSE in body["offeringsByCourseNumber"]
    assert len(body["offeringsByCourseNumber"][KNOWN_COURSE]) == 1


@pytest.mark.asyncio
async def test_vault_like_advisory_rule_totals(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-advisory-totals@example.com")

    total_advisory = 0
    for program_code in ALL_PROGRAMS:
        response = await auth_client.get(
            f"/catalog/degree-programs/{program_code}/advisory-rules",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        count = response.json()["data"]["total"]
        assert count == ADVISORY_COUNTS_BY_PROGRAM[program_code]
        total_advisory += count

    assert total_advisory == TOTAL_ADVISORY_RULES


@pytest.mark.asyncio
async def test_vault_like_hard_requirement_totals(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-hard-totals@example.com")

    total_hard = 0
    for program_code in ALL_PROGRAMS:
        response = await auth_client.get(
            f"/catalog/degree-programs/{program_code}/requirements",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        total_hard += response.json()["data"]["total"]

    assert total_hard == TOTAL_HARD_REQUIREMENTS


@pytest.mark.asyncio
async def test_get_course_returns_400_for_invalid_course_number(auth_client):
    token = await register_access_token(auth_client, "catalog-bad-number@example.com")

    response = await auth_client.get(
        "/catalog/courses/NOTANUMBER",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "8-digit" in response.json()["error"]


@pytest.mark.asyncio
async def test_get_course_returns_404_when_course_not_found(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-404-course@example.com")

    response = await auth_client.get(
        "/catalog/courses/09999999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_get_course_offerings_returns_400_for_invalid_course_number(auth_client):
    token = await register_access_token(auth_client, "catalog-offerings-bad@example.com")

    response = await auth_client.get(
        "/catalog/courses/BADNUMBER/offerings",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_course_offerings_returns_400_for_invalid_semester_code(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-offerings-bad-sem@example.com")

    response = await auth_client.get(
        f"/catalog/courses/{KNOWN_COURSE}/offerings?semesterCode=999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "semesterCode" in response.json()["error"]


@pytest.mark.asyncio
async def test_get_course_offerings_returns_404_when_course_not_found(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-offerings-404@example.com")

    response = await auth_client.get(
        "/catalog/courses/09999998/offerings",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_batch_offerings_returns_400_for_empty_course_numbers(auth_client):
    token = await register_access_token(auth_client, "catalog-batch-empty@example.com")

    response = await auth_client.get(
        "/catalog/offerings?courseNumbers=,,,",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "at least one" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_batch_offerings_returns_400_for_invalid_semester_code(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-batch-bad-sem@example.com")

    response = await auth_client.get(
        f"/catalog/offerings?courseNumbers={KNOWN_COURSE}&semesterCode=999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400
    assert "semesterCode" in response.json()["error"]


@pytest.mark.asyncio
async def test_get_degree_program_returns_404_when_not_found(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-degree-404@example.com")

    response = await auth_client.get(
        "/catalog/degree-programs/999999-9-999",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404
    assert "not found" in response.json()["error"].lower()


@pytest.mark.asyncio
async def test_get_degree_program_returns_400_for_invalid_program_code(auth_client):
    token = await register_access_token(auth_client, "catalog-program-bad-code@example.com")

    response = await auth_client.get(
        "/catalog/degree-programs/BADCODE",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 400


@pytest.mark.asyncio
async def test_get_hard_requirements_returns_404_when_program_not_found(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-req-404@example.com")

    response = await auth_client.get(
        "/catalog/degree-programs/999999-9-999/requirements",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_advisory_rules_returns_404_when_program_not_found(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-advisory-404@example.com")

    response = await auth_client.get(
        "/catalog/degree-programs/999999-9-999/advisory-rules",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_courses_with_offerings_included(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-include-offerings@example.com")

    response = await auth_client.get(
        "/catalog/courses?includeOfferings=true&limit=2",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "items" in body["data"]


@pytest.mark.asyncio
async def test_get_catalog_summary_returns_404_when_program_not_found(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-summary-404@example.com")

    response = await auth_client.get(
        "/catalog/degree-programs/999999-9-999/catalog-summary",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_batch_offerings_with_year_and_semester_returns_best_offering(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-batch-year-sem@example.com")

    response = await auth_client.get(
        f"/catalog/offerings?courseNumbers={KNOWN_COURSE}&academicYear=2025&semesterCode=200",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "offeringsByCourseNumber" in body["data"]


@pytest.mark.asyncio
async def test_get_course_returns_cached_response_on_second_call(auth_client, mongo_database):
    """Cache hit path in get_catalog_course (line 153)."""
    from unittest.mock import AsyncMock, patch

    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-cache-course@example.com")

    cached_data = {
        "courseNumber": KNOWN_COURSE,
        "title": "Cached Course",
        "credits": 3.0,
    }

    with patch("app.routes.catalog.get_cached_json", new_callable=AsyncMock, return_value=cached_data):
        response = await auth_client.get(
            f"/catalog/courses/{KNOWN_COURSE}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["data"]["course"]["courseNumber"] == KNOWN_COURSE


@pytest.mark.asyncio
async def test_batch_offerings_returns_cached_response(auth_client, mongo_database):
    """Cache hit path in batch_catalog_offerings (line 233)."""
    from unittest.mock import AsyncMock, patch

    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-cache-batch@example.com")

    cached_data = {"offeringsByCourseNumber": {KNOWN_COURSE: []}, "totalCourses": 1}

    with patch("app.routes.catalog.get_cached_json", new_callable=AsyncMock, return_value=cached_data):
        response = await auth_client.get(
            f"/catalog/offerings?courseNumbers={KNOWN_COURSE}",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["totalCourses"] == 1


@pytest.mark.asyncio
async def test_batch_offerings_without_year_or_semester_uses_grouped(auth_client, mongo_database):
    """Else branch in batch_catalog_offerings (lines 248-254) — no academicYear/semesterCode."""
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-batch-no-year@example.com")

    response = await auth_client.get(
        f"/catalog/offerings?courseNumbers={KNOWN_COURSE}",  # no academicYear or semesterCode
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert "offeringsByCourseNumber" in body["data"]


@pytest.mark.asyncio
async def test_list_degree_programs_returns_cached(auth_client, mongo_database):
    """Cache hit path in list_catalog_degree_programs (line 276)."""
    from unittest.mock import AsyncMock, patch

    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-cache-programs@example.com")

    cached_data = {"items": [], "total": 0}

    with patch("app.routes.catalog.get_cached_json", new_callable=AsyncMock, return_value=cached_data):
        response = await auth_client.get(
            "/catalog/degree-programs",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_planner_semesters_returns_catalog_backed_codes(auth_client, mongo_database):
    await seed_catalog_production_fixtures(mongo_database)
    token = await register_access_token(auth_client, "catalog-planner-semesters@example.com")

    response = await auth_client.get(
        "/catalog/planner-semesters",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    codes = body["data"]["planSemesterCodes"]
    assert isinstance(codes, list)
    assert "2025-2" in codes
    assert all(isinstance(code, str) and code.count("-") == 1 for code in codes)
    assert body["data"]["total"] == len(codes)
