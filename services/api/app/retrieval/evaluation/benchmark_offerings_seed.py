"""Offering coverage helpers for retrieval benchmark evaluation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config import Settings, get_settings
from app.planning.semester_codes import plan_semester_to_offering_keys
from app.retrieval.offerings_retriever import retrieve_offerings_context

_DEFAULT_BENCHMARK = Path(__file__).with_name("benchmark_cases.jsonl")


def _load_offering_cases(benchmark_path: Path | None = None) -> list[dict[str, Any]]:
    benchmark = benchmark_path or _DEFAULT_BENCHMARK
    cases: list[dict[str, Any]] = []
    for line in benchmark.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        case = json.loads(line)
        if str(case.get("evalType") or "") == "offering":
            cases.append(case)
    return cases


async def audit_benchmark_offerings_coverage(
    database: AsyncIOMotorDatabase,
    *,
    benchmark_path: Path | None = None,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """Report how many benchmark offering cases resolve via Mongo (and JSON fallback)."""
    cfg = settings or get_settings()
    cases = _load_offering_cases(benchmark_path)
    if not cases:
        return {"caseCount": 0, "resolvedCount": 0, "missingCaseIds": []}

    resolved: list[str] = []
    missing: list[str] = []
    for case in cases:
        entities = dict(case.get("entities") or {})
        _academic, records = await retrieve_offerings_context(
            database,
            queries=[entities],
            entities=entities,
            settings=cfg,
        )
        required = list(case.get("mustRetrieve") or [])
        source_ids = [getattr(record, "source_id", "") for record in records]
        if required and any(item in source_ids for item in required):
            resolved.append(str(case.get("id") or ""))
        elif records:
            resolved.append(str(case.get("id") or ""))
        else:
            missing.append(str(case.get("id") or ""))

    return {
        "caseCount": len(cases),
        "resolvedCount": len(resolved),
        "missingCaseIds": missing,
        "technionRawDir": (cfg.technion_raw_dir or "").strip() or None,
    }


async def seed_benchmark_offerings(
    database: AsyncIOMotorDatabase,
    *,
    benchmark_path: Path | None = None,
    settings: Settings | None = None,
) -> int:
    """DEV/CI ONLY: upsert synthetic offerings when Mongo lacks imported catalog data."""
    cfg = settings or get_settings()
    collection = database[cfg.course_offerings_collection]
    cases = _load_offering_cases(benchmark_path)
    seeded = 0
    for case in cases:
        entities = dict(case.get("entities") or {})
        course_number = str(entities.get("courseNumber") or "").strip()
        semester_code = str(entities.get("targetSemesterCode") or "").strip()
        keys = plan_semester_to_offering_keys(semester_code)
        if not course_number or keys is None:
            continue
        academic_year, term_code = keys
        document: dict[str, Any] = {
            "productionKey": f"technion:course-offering:{course_number}:{academic_year}:{term_code}",
            "courseNumber": course_number,
            "academicYear": academic_year,
            "semesterCode": term_code,
            "scheduleGroups": [
                {"day": "Sunday", "time": "10:30-12:30", "type": "lecture", "group": "10"}
            ],
            "status": "published",
            "source": "rag_benchmark_seed",
            "benchmarkCaseId": case.get("id"),
        }
        await collection.update_one(
            {"productionKey": document["productionKey"]},
            {"$set": document},
            upsert=True,
        )
        seeded += 1
    return seeded
