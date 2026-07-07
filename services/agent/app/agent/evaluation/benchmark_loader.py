"""Load and optionally expand agent benchmark cases."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_AGENT_BENCHMARK_PATH = Path(__file__).resolve().parent / "agent_benchmark_cases.jsonl"
_RAG_BENCHMARK_PATH = (
    Path(__file__).resolve().parents[2] / "retrieval" / "evaluation" / "benchmark_cases.jsonl"
)

_COURSE_QUESTION_EXPECT = {
    "noRunFailed": True,
    "minTextLength": 20,
    "textNotContains": ["I could not produce a response"],
}


def load_jsonl_cases(path: Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        cases.append(json.loads(stripped))
    return cases


def load_agent_benchmark_cases(path: Path | None = None) -> list[dict[str, Any]]:
    return load_jsonl_cases(path or _AGENT_BENCHMARK_PATH)


def _rag_case_to_agent_case(rag_case: dict[str, Any]) -> dict[str, Any]:
    intent = str(rag_case.get("intent") or "course_question")
    course_number = (rag_case.get("entities") or {}).get("courseNumber")
    setup: dict[str, Any] = {"profileTemplate": "dds_track"}
    if course_number:
        setup["completedCourseNumbers"] = []

    expect: dict[str, Any] = dict(_COURSE_QUESTION_EXPECT)
    expect["intent"] = intent

    if intent == "course_question":
        expect["textContainsAny"] = ["course", "prerequisite", "offered", "credit", "009"]
        expect["blockTypesAny"] = [
            "CourseCardBlock",
            "PrerequisiteStatusBlock",
            "OfferingSummaryBlock",
            "WarningBlock",
            "SourceSummaryBlock",
        ]
    elif intent == "requirement_explanation":
        expect["textContainsAny"] = ["requirement", "elective", "credit", "bucket", "דריש"]
        expect["blockTypesAny"] = ["RequirementBucketBlock", "SourceSummaryBlock", "WarningBlock"]
    elif intent == "graduation_progress_check":
        expect["textContainsAny"] = ["credit", "graduation", "missing", "requirement"]
        expect["blockTypesAny"] = ["RequirementSummaryBlock", "RequirementBucketBlock", "WarningBlock"]

    return {
        "id": f"agent_rag_{rag_case.get('id')}",
        "category": f"from_rag_{intent}",
        "message": str(rag_case.get("query") or ""),
        "setup": setup,
        "expect": expect,
        "notes": f"Derived from RAG case {rag_case.get('id')}",
    }


def sample_rag_agent_cases(
    *,
    limit: int,
    intents: set[str] | None = None,
    rag_path: Path | None = None,
) -> list[dict[str, Any]]:
    rag_cases = load_jsonl_cases(rag_path or _RAG_BENCHMARK_PATH)
    selected: list[dict[str, Any]] = []
    seen_messages: set[str] = set()

    for rag_case in rag_cases:
        intent = str(rag_case.get("intent") or "")
        if intents and intent not in intents:
            continue
        if rag_case.get("evalType") == "offering":
            continue
        message = str(rag_case.get("query") or "").strip()
        if not message or message in seen_messages:
            continue
        seen_messages.add(message)
        selected.append(_rag_case_to_agent_case(rag_case))
        if len(selected) >= limit:
            break

    return selected


def merge_cases(
    base_cases: list[dict[str, Any]],
    extra_cases: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_id = {str(case["id"]): case for case in base_cases}
    for case in extra_cases:
        by_id[str(case["id"])] = case
    return list(by_id.values())
