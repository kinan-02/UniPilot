"""Unit tests for `find_course_numbers_by_ids` -- the courseId -> courseNumber
join that lets completed-course records (which store only a courseId reference)
expose their real course numbers to the agent's prerequisite reasoning."""

from __future__ import annotations

from typing import Any

import pytest
from bson import ObjectId

from app.repositories.course_repository import find_course_numbers_by_ids


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return list(self._docs)


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def find(self, query: dict[str, Any], projection: dict[str, Any] | None = None) -> _FakeCursor:
        wanted = set(query.get("_id", {}).get("$in", []))
        return _FakeCursor([doc for doc in self._docs if doc.get("_id") in wanted])


class _FakeDatabase:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._collection = _FakeCollection(docs)

    def __getitem__(self, _name: str) -> _FakeCollection:
        return self._collection


@pytest.mark.asyncio
async def test_maps_ids_to_course_numbers() -> None:
    a, b = ObjectId(), ObjectId()
    db = _FakeDatabase([{"_id": a, "courseNumber": "01040031"}, {"_id": b, "courseNumber": "02340114"}])
    mapping = await find_course_numbers_by_ids(db, [a, b])
    assert mapping == {str(a): "01040031", str(b): "02340114"}


@pytest.mark.asyncio
async def test_empty_ids_returns_empty_without_querying() -> None:
    db = _FakeDatabase([{"_id": ObjectId(), "courseNumber": "X"}])
    assert await find_course_numbers_by_ids(db, []) == {}


@pytest.mark.asyncio
async def test_courses_missing_a_number_are_skipped() -> None:
    a, b = ObjectId(), ObjectId()
    db = _FakeDatabase([{"_id": a, "courseNumber": "01040031"}, {"_id": b}])  # b has no number
    mapping = await find_course_numbers_by_ids(db, [a, b])
    assert mapping == {str(a): "01040031"}


@pytest.mark.asyncio
async def test_none_ids_are_filtered_out() -> None:
    a = ObjectId()
    db = _FakeDatabase([{"_id": a, "courseNumber": "01040031"}])
    mapping = await find_course_numbers_by_ids(db, [a, None])  # type: ignore[list-item]
    assert mapping == {str(a): "01040031"}
