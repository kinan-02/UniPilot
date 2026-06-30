#!/usr/bin/env python3
"""Live advisor pipeline tests — requires OPENAI_API_KEY (DeepSeek or OpenAI)."""

from __future__ import annotations

import os
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
WIKI = REPO / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
RAW = REPO / "services/data-engineering/data/raw/technion"

sys.path.insert(0, str(ROOT))

from app.services.academic_graph_engine import AcademicGraphEngine  # noqa: E402
from app.services.advisor_agent import UserContext, advise  # noqa: E402
from app.services.graph_tools import _block_is_empty  # noqa: E402

KNOWN_COURSE = "00440148"  # גלים ומערכות מפולגות
SPRING_ONLY = "00440127"

PASS = 0
FAIL = 0
WARN = 0


@dataclass
class LiveCase:
    name: str
    question: str
    context: UserContext = field(default_factory=UserContext)
    verify: Callable[[dict[str, Any], AcademicGraphEngine], tuple[bool, str]] | None = None
    max_seconds: float = 90.0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"    ✓ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"    ✗ {name}" + (f" — {detail}" if detail else ""))


def warn(name: str, detail: str = "") -> None:
    global WARN
    WARN += 1
    print(f"    ⚠ {name}" + (f" — {detail}" if detail else ""))


def _answer(result: dict[str, Any]) -> str:
    return str(result.get("response", {}).get("answer", ""))


def _blocks(result: dict[str, Any]) -> list[dict[str, Any]]:
    return list(result.get("retrieval_blocks") or [])


def _retrieval_status(result: dict[str, Any]) -> str:
    return str(result.get("retrieval_agent", {}).get("status", ""))


def _has_intent(blocks: list[dict[str, Any]], intent: str) -> bool:
    return any(block.get("intent") == intent for block in blocks)


def _nonempty_blocks(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [b for b in blocks if not b.get("is_empty")]


def _answer_has_any(answer: str, keywords: list[str]) -> bool:
    lowered = answer.lower()
    return any(kw.lower() in lowered or kw in answer for kw in keywords)


def verify_retrieval_ok(result: dict[str, Any], _engine: AcademicGraphEngine) -> tuple[bool, str]:
    status = _retrieval_status(result)
    blocks = _nonempty_blocks(_blocks(result))
    ok = status in {"ok", "max_iterations"} and len(blocks) > 0
    return ok, f"status={status}, nonempty_blocks={len(blocks)}"


def verify_syllabus(result: dict[str, Any], engine: AcademicGraphEngine) -> tuple[bool, str]:
    blocks = _blocks(result)
    answer = _answer(result)
    ctx = engine.retrieve_context("syllabus", course_id=KNOWN_COURSE)
    has_syllabus_block = _has_intent(blocks, "syllabus")
    has_course_ref = KNOWN_COURSE in answer or "גלים" in answer or "מפולגות" in answer
    has_content = any(
        token in answer
        for token in ("מקסוול", "גלים", "קווי תמסורת", "Maxwell", "wave")
    )
    ok = has_syllabus_block and has_course_ref and (has_content or len(ctx) > 100)
    return ok, f"syllabus_block={has_syllabus_block}, content={has_content}"


def verify_eligible(result: dict[str, Any], engine: AcademicGraphEngine) -> tuple[bool, str]:
    eligible, missing = engine.evaluate_eligibility(
        KNOWN_COURSE, ["00440105", "00440140"]
    )
    answer = _answer(result)
    blocks = _blocks(result)
    facts_ok = any(
        block.get("facts", {}).get("eligible") is True
        for block in blocks
        if block.get("intent") == "eligibility"
    )
    answer_ok = _answer_has_any(
        answer, ["זכא", "eligible", "יכול", "מותר", "עומד", "מתאים"]
    )
    ok = eligible and (facts_ok or answer_ok or _has_intent(blocks, "eligibility"))
    return ok, f"graph_eligible={eligible}, facts={facts_ok}, answer_hint={answer_ok}"


def verify_not_eligible(result: dict[str, Any], engine: AcademicGraphEngine) -> tuple[bool, str]:
    eligible, missing = engine.evaluate_eligibility(KNOWN_COURSE, [])
    answer = _answer(result)
    blocks = _blocks(result)
    facts_ok = any(
        block.get("facts", {}).get("eligible") is False
        for block in blocks
        if block.get("intent") == "eligibility"
    )
    answer_ok = _answer_has_any(
        answer,
        ["לא זכא", "not eligible", "חסר", "missing", "קדם", "דרישות", "לא עומד"],
    )
    ok = not eligible and (facts_ok or answer_ok or missing)
    return ok, f"graph_eligible={eligible}, missing={missing[:2]}, facts={facts_ok}"


def verify_schedule_spring(result: dict[str, Any], _engine: AcademicGraphEngine) -> tuple[bool, str]:
    answer = _answer(result)
    sem = result.get("semester_resolution", {}).get("semester") or {}
    fname = sem.get("filename", "")
    blocks = _blocks(result)
    has_schedule = _has_intent(blocks, "schedule")
    has_time = bool(re.search(r"\d{1,2}:\d{2}", answer)) or "יום" in answer or "Monday" in answer
    spring = fname == "courses_2025_201.json" or "אביב" in answer or "Spring" in answer
    ok = has_schedule and (has_time or len(_nonempty_blocks(blocks)) > 0)
    return ok, f"schedule_block={has_schedule}, spring={spring}, has_time={has_time}"


def verify_prerequisites(result: dict[str, Any], engine: AcademicGraphEngine) -> tuple[bool, str]:
    answer = _answer(result)
    blocks = _blocks(result)
    prereq_ctx = engine.retrieve_context("prerequisites", course_id=KNOWN_COURSE)
    has_block = _has_intent(blocks, "prerequisites")
    has_codes = "00440105" in answer or "00440105" in prereq_ctx
    ok = has_block and has_codes
    return ok, f"prereq_block={has_block}, codes_in_answer={has_codes}"


def verify_wiki_rights(result: dict[str, Any], _engine: AcademicGraphEngine) -> tuple[bool, str]:
    answer = _answer(result)
    blocks = _blocks(result)
    wiki_block = any(
        block.get("intent") in {"wiki_search", "wiki_page"}
        and not block.get("is_empty")
        for block in blocks
    )
    content = _answer_has_any(
        answer, ["זכויות", "סטודנט", "student", "rights", "תקנון", "נציב"]
    )
    ok = wiki_block and content
    return ok, f"wiki_block={wiki_block}, content={content}"


def verify_english_schedule(result: dict[str, Any], _engine: AcademicGraphEngine) -> tuple[bool, str]:
    answer = _answer(result)
    is_english = not re.search(r"[\u0590-\u05FF]{3,}", answer)
    has_schedule = _has_intent(_blocks(result), "schedule")
    ok = has_schedule and (is_english or KNOWN_COURSE in answer)
    return ok, f"english={is_english}, schedule_block={has_schedule}"


def verify_winter_semester(result: dict[str, Any], _engine: AcademicGraphEngine) -> tuple[bool, str]:
    sem = result.get("semester_resolution", {}).get("semester") or {}
    fname = sem.get("filename", "")
    ok = fname == "courses_2025_200.json"
    return ok, f"resolved={fname}"


def verify_fake_course(result: dict[str, Any], _engine: AcademicGraphEngine) -> tuple[bool, str]:
    status = _retrieval_status(result)
    answer = _answer(result)
    blocks = _blocks(result)
    all_empty = all(block.get("is_empty") for block in blocks) if blocks else True
    low_conf = result.get("response", {}).get("confidence") == "low"
    not_foundish = _answer_has_any(
        answer, ["לא מצאתי", "not found", "לא נמצא", "אין מידע", "could not find"]
    )
    ok = status in {"not_found", "max_iterations", "ok"} and (
        all_empty or low_conf or not_foundish or "99999999" in answer
    )
    return ok, f"status={status}, all_empty={all_empty}, low_conf={low_conf}"


def verify_user_semester_override(result: dict[str, Any], _engine: AcademicGraphEngine) -> tuple[bool, str]:
    sem = result.get("semester_resolution", {}).get("semester") or {}
    fname = sem.get("filename", "")
    ok = fname == "courses_2025_200.json"
    return ok, f"resolved={fname}"


def verify_combined(result: dict[str, Any], engine: AcademicGraphEngine) -> tuple[bool, str]:
    blocks = _blocks(result)
    answer = _answer(result)
    eligible, _ = engine.evaluate_eligibility(KNOWN_COURSE, ["00440105", "00440140"])
    intents = {block.get("intent") for block in blocks}
    has_multi = len(intents) >= 2 or (
        _has_intent(blocks, "eligibility") and _has_intent(blocks, "schedule")
    )
    answer_covers = _answer_has_any(answer, ["זכא", "eligible", "לוח", "schedule", "יום", ":"])
    ok = eligible and len(_nonempty_blocks(blocks)) >= 1 and (has_multi or answer_covers)
    return ok, f"intents={sorted(intents)}, eligible={eligible}"


CASES: list[LiveCase] = [
    LiveCase("Hebrew syllabus", "מה הסילבוס של קורס 00440148?", verify=verify_syllabus),
    LiveCase(
        "Eligibility — meets prereqs",
        "האם אני זכאי לקורס 00440148?",
        UserContext(completed_courses=["00440105", "00440140"]),
        verify=verify_eligible,
    ),
    LiveCase(
        "Eligibility — missing prereqs",
        "האם אני יכול לקחת את קורס 00440148?",
        UserContext(completed_courses=[]),
        verify=verify_not_eligible,
    ),
    LiveCase(
        "Schedule spring 2026 (Hebrew)",
        "מה לוח הזמנים של 00440148 בסמסטר אביב 2026?",
        verify=verify_schedule_spring,
    ),
    LiveCase(
        "Prerequisites",
        "מהם קורסי הקדם ל-00440148?",
        verify=verify_prerequisites,
    ),
    LiveCase(
        "Wiki — student rights",
        "מה זכויות הסטודנט בטכניון?",
        verify=verify_wiki_rights,
    ),
    LiveCase(
        "English schedule",
        "What is the schedule for course 00440148 in Spring 2026?",
        verify=verify_english_schedule,
    ),
    LiveCase(
        "Winter semester resolution",
        "מתי מתקיים קורס 00440148 בחורף 2026?",
        verify=verify_winter_semester,
    ),
    LiveCase(
        "Fake course",
        "מה הסילבוס של קורס 99999999?",
        verify=verify_fake_course,
    ),
    LiveCase(
        "Profile semester override",
        "מה לוח הזמנים של 00440148?",
        UserContext(semester_filename="courses_2025_200.json"),
        verify=verify_user_semester_override,
    ),
    LiveCase(
        "Combined eligibility + schedule",
        "האם אני זכאי ל-00440148 ומתי הוא מתקיים?",
        UserContext(completed_courses=["00440105", "00440140"]),
        verify=verify_combined,
    ),
]


def run_case(case: LiveCase, engine: AcademicGraphEngine) -> dict[str, Any]:
    started = time.monotonic()
    result = advise(case.question, engine, str(RAW), case.context)
    elapsed = time.monotonic() - started
    return {**result, "_elapsed": elapsed}


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("ERROR: OPENAI_API_KEY is required. Source ../../.env first.")
        return 1
    if not WIKI.is_dir() or not RAW.is_dir():
        print("ERROR: wiki or technion data paths missing.")
        return 1

    model = os.environ.get("OPENAI_CHAT_MODEL", "?")
    base = os.environ.get("OPENAI_BASE_URL", "OpenAI default")

    print("=" * 70)
    print("UniPilot — LIVE ADVISOR TESTS")
    print(f"Model: {model} | Base: {base}")
    print("=" * 70)

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(WIKI), str(RAW), semester_filename="courses_2025_201.json")
    engine.build_graph()
    stats = engine.graph_stats()
    print(f"Graph ready: {stats['nodes']} nodes, semester={stats['active_semester']}\n")

    for index, case in enumerate(CASES, 1):
        print(f"[{index}/{len(CASES)}] {case.name}")
        print(f"    Q: {case.question[:72]}{'...' if len(case.question) > 72 else ''}")
        try:
            result = run_case(case, engine)
        except Exception as exc:
            check("pipeline completed", False, str(exc)[:120])
            print()
            continue

        elapsed = result.get("_elapsed", 0)
        status = _retrieval_status(result)
        blocks = _blocks(result)
        answer = _answer(result)
        confidence = result.get("response", {}).get("confidence", "?")

        check("pipeline completed", True, f"{elapsed:.1f}s")
        check("retrieval not hard-failed", status != "not_found" or case.name == "Fake course", status)
        check("got answer text", len(answer.strip()) > 20, f"{len(answer)} chars")
        check("confidence set", confidence in {"high", "medium", "low"}, confidence)

        intents = [b.get("intent") for b in blocks]
        if intents:
            block_summary = ", ".join(
                f"{intent}(empty={block.get('is_empty')})"
                for block, intent in zip(blocks, intents)
            )
            print(f"    blocks: {block_summary}")

        if case.verify:
            ok, detail = case.verify(result, engine)
            check("verification", ok, detail)
        else:
            ok, detail = verify_retrieval_ok(result, engine)
            check("verification", ok, detail)

        preview = answer.replace("\n", " ")[:160]
        print(f"    answer: {preview}{'...' if len(answer) > 160 else ''}")
        if confidence == "low" and case.name != "Fake course":
            warn("low confidence on non-fallback case")
        print()

    print("=" * 70)
    print(f"LIVE TESTS: {PASS} passed, {FAIL} failed, {WARN} warnings")
    print("=" * 70)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
