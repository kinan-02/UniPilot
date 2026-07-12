"""Shared fixtures for `app.agent_core.tools.primitives` tests.

`FakeDatabase` is a minimal, in-memory double for the exact slice of the
Motor `AsyncIOMotorDatabase` API `app.repositories.*` actually uses
(`find_one`, `find().sort().skip().limit().to_list()`, `count_documents`,
and -- for the one write-capable repository, `agent_action_proposal_
repository.py` -- `insert_one`) -- no `mongomock` dependency needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from bson import ObjectId

from app.db.mongo import set_test_database
from app.retrieval.graph_engine.academic_graph_engine import AcademicGraphEngine
from app.retrieval.graph_engine.graph_registry import graph_registry

REPO_ROOT = Path(__file__).resolve().parents[5]
WIKI_DIR = REPO_ROOT / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
TECHNION_RAW_DIR = REPO_ROOT / "services/data-engineering/data/raw/technion"
CATALOG_JSON = TECHNION_RAW_DIR / "courses_2025_201.json"


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = list(docs)

    def sort(self, *_args: Any, **_kwargs: Any) -> "_FakeCursor":
        return self

    def skip(self, count: int) -> "_FakeCursor":
        self._docs = self._docs[count:]
        return self

    def limit(self, count: int) -> "_FakeCursor":
        self._docs = self._docs[:count]
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        return list(self._docs) if length is None else list(self._docs[:length])


class _FakeInsertOneResult:
    def __init__(self, inserted_id: ObjectId) -> None:
        self.inserted_id = inserted_id


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def _matches(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        if "_id" in query:
            return [doc for doc in self._docs if doc.get("_id") == query["_id"]]
        user_id = query.get("userId")
        return [doc for doc in self._docs if doc.get("userId") == user_id]

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        matches = self._matches(query)
        return matches[0] if matches else None

    def find(self, query: dict[str, Any]) -> _FakeCursor:
        return _FakeCursor(self._matches(query))

    async def count_documents(self, query: dict[str, Any]) -> int:
        return len(self._matches(query))

    async def insert_one(self, document: dict[str, Any]) -> _FakeInsertOneResult:
        inserted_id = document.setdefault("_id", ObjectId())
        self._docs.append(document)
        return _FakeInsertOneResult(inserted_id)


class FakeDatabase:
    def __init__(self, collections: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._collections = {name: _FakeCollection(docs) for name, docs in (collections or {}).items()}

    def __getitem__(self, name: str) -> _FakeCollection:
        if name not in self._collections:
            self._collections[name] = _FakeCollection([])
        return self._collections[name]


@pytest.fixture
def fake_database_factory():
    def _build(collections: dict[str, list[dict[str, Any]]] | None = None) -> FakeDatabase:
        return FakeDatabase(collections)

    return _build


@pytest.fixture(autouse=True)
def reset_test_database_override():
    yield
    set_test_database(None)


@pytest.fixture(scope="session")
def real_academic_engine() -> AcademicGraphEngine:
    """Real wiki + real semester-catalog engine, session-scoped so it's only
    built once across every test in this package. Skips when the real data
    isn't checked out locally.
    """
    if not WIKI_DIR.exists() or not CATALOG_JSON.exists():
        pytest.skip("Real wiki/catalog data not available locally")
    engine = AcademicGraphEngine()
    engine.load_from_paths(
        str(WIKI_DIR),
        str(TECHNION_RAW_DIR),
        semester_filename="courses_2025_201.json",
    )
    engine.build_graph()
    return engine


@pytest.fixture
def use_real_academic_engine(monkeypatch: pytest.MonkeyPatch, real_academic_engine: AcademicGraphEngine):
    """Point the shared `graph_registry` singleton at the real, already-built
    engine for the duration of one test -- decouples these tests from
    `Settings`/env vars entirely (no risk of polluting other tests' config).
    """
    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)
    monkeypatch.setattr(graph_registry, "get_engine", lambda *_a, **_k: real_academic_engine)
    return real_academic_engine


@pytest.fixture
def use_real_technion_raw_dir(monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point `extract_temporal_pattern`'s settings lookup at the real raw
    Technion offering directory (7 real semester files) without touching
    `Settings`/env vars globally -- same isolation goal as
    `use_real_academic_engine`, for the one primitive that reads raw
    semester files directly instead of going through the graph engine.
    """
    if not TECHNION_RAW_DIR.exists():
        pytest.skip("Real raw Technion data not available locally")
    monkeypatch.setattr(graph_registry, "is_configured", lambda *_a, **_k: True)

    import app.agent_core.tools.primitives.extract_temporal_pattern as extract_temporal_pattern_module

    class _FakeSettings:
        def resolved_technion_raw_dir(self) -> str:
            return str(TECHNION_RAW_DIR)

    monkeypatch.setattr(extract_temporal_pattern_module, "get_settings", lambda: _FakeSettings())
    return TECHNION_RAW_DIR


@pytest.fixture
def use_real_academic_data(use_real_academic_engine: AcademicGraphEngine, use_real_technion_raw_dir: Path):
    """`search_over_state` composes `get_entity`/`traverse_relationship`
    (need the real engine) *and* `extract_temporal_pattern` (needs the real
    raw dir) -- this just combines the two fixtures above so tests don't
    have to request both separately.
    """
    return use_real_academic_engine
