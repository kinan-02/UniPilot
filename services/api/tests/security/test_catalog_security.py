"""Security tests for JWT-protected catalog endpoints."""

import pytest

from tests.fixtures.catalog_production_fixtures import KNOWN_COURSE, KNOWN_PROGRAM


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/catalog/courses?limit=1",
        "/catalog/faculties",
        "/catalog/degree-programs",
        f"/catalog/courses/{KNOWN_COURSE}",
        f"/catalog/degree-programs/{KNOWN_PROGRAM}/requirements",
        f"/catalog/degree-programs/{KNOWN_PROGRAM}/advisory-rules",
        f"/catalog/degree-programs/{KNOWN_PROGRAM}/catalog-summary",
        "/catalog/offerings?courseNumbers=00940345&academicYear=2025&semesterCode=201",
        "/catalog/planner-semesters",
    ],
)
async def test_catalog_routes_require_jwt(security_client, path: str) -> None:
    response = await security_client.get(path)
    assert response.status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/catalog/courses?limit=1",
        f"/catalog/degree-programs/{KNOWN_PROGRAM}/advisory-rules",
    ],
)
async def test_catalog_routes_reject_invalid_jwt(security_client, path: str) -> None:
    response = await security_client.get(
        path,
        headers={"Authorization": "Bearer not-a-valid-jwt"},
    )
    assert response.status_code == 401
