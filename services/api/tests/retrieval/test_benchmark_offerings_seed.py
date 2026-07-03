"""Tests for benchmark offering seed helper."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.retrieval.evaluation.benchmark_offerings_seed import seed_benchmark_offerings
from app.retrieval.offerings_retriever import retrieve_offerings_context


@pytest.mark.asyncio
async def test_seed_benchmark_offerings_enables_eval_lookup(mongo_database):
    settings = get_settings()
    seeded = await seed_benchmark_offerings(mongo_database)
    assert seeded >= 1

    _academic, records = await retrieve_offerings_context(
        mongo_database,
        queries=[{"courseNumber": "00940101", "targetSemesterCode": "2025-1"}],
        entities={"courseNumber": "00940101", "targetSemesterCode": "2025-1"},
    )
    source_ids = [record.source_id for record in records]
    assert "offering:2025-1:00940101" in source_ids

    stored = await mongo_database[settings.course_offerings_collection].find_one(
        {"productionKey": "technion:course-offering:00940101:2025:200"}
    )
    assert stored is not None
    assert stored.get("source") == "rag_benchmark_seed"
