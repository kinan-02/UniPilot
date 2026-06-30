#!/usr/bin/env python3
"""Creative edge-case simulations for the academic advisor stack (no API key)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
WIKI = REPO / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
RAW = REPO / "services/data-engineering/data/raw/technion"

sys.path.insert(0, str(ROOT))

from app.services.academic_graph_engine import (  # noqa: E402
    AcademicGraphEngine,
    parse_prerequisites_string,
)
from app.services.advisor_agent import (  # noqa: E402
    UserContext,
    _dedupe_blocks,
    _default_fallback,
    _extract_course_codes,
    synthesize_answer,
)
from app.services.graph_tools import _block_is_empty, _retrieve_graph_data, build_graph_tools  # noqa: E402
from app.services.semester_catalog import (  # noqa: E402
    discover_semester_catalogs,
    resolve_semester_from_query,
)

PASS = 0
FAIL = 0
WARN = 0

KNOWN_COURSE = "00440148"
SPRING_ONLY = "00440127"


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))


def warn(name: str, detail: str = "") -> None:
    global WARN
    WARN += 1
    print(f"  ⚠ {name}" + (f" — {detail}" if detail else ""))


def bridge(payload: dict) -> dict:
    from app.services.graph_registry import GraphRegistry

    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    registry = GraphRegistry()
    success, data, error = registry.dispatch_action(payload)
    return {"success": success, "data": data, "error": error}


def section(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


def simulate_semester_resolution(catalogs) -> None:
    section("[A] Semester resolution — creative queries")

    cases = [
        ("סמסטר חורף 2026", "courses_2025_200.json", False),
        ("מה לוח הזמנים בסמסטר אביב 2026?", "courses_2025_201.json", False),
        ("schedule for summer 2026", "courses_2025_202.json", False),
        ("courses_2025_200.json", "courses_2025_200.json", False),
        ("plan 2025-3", "courses_2025_202.json", False),
        ("קיץ 2025", "courses_2024_202.json", False),
        ("Spring 2025", "courses_2024_201.json", False),
        ("חורפי 2026", "courses_2025_200.json", False),  # typo keyword
    ]
    for query, expected, _ in cases:
        result = resolve_semester_from_query(query, catalogs, today=date(2026, 4, 1))
        semester = result.get("semester")
        fname = semester.filename if semester else None
        check(f"resolve: {query[:40]}", fname == expected, fname or "none")

    # Ambiguous / contradictory
    ambiguous = resolve_semester_from_query(
        "Winter Spring 2026", catalogs, today=date(2026, 4, 1)
    )
    check(
        "contradictory Winter+Spring flags clarification",
        ambiguous.get("needs_clarification") is True,
        str(ambiguous.get("assumption_note", ""))[:60],
    )

    hebrew_conflict = resolve_semester_from_query(
        "חורף ואביב 2026", catalogs, today=date(2026, 4, 1)
    )
    check(
        "contradictory חורף+אביב flags clarification",
        hebrew_conflict.get("needs_clarification") is True,
    )

    year_only = resolve_semester_from_query("2026", catalogs, today=date(2026, 4, 1))
    check(
        "year-only defaults to inferred current (April → spring)",
        year_only["semester"].filename == "courses_2025_201.json",
    )

    explicit = resolve_semester_from_query(
        "סמסטר קיץ 2099",
        catalogs,
        today=date(2026, 4, 1),
    )
    check(
        "future semester not on disk falls back with note",
        explicit.get("semester") is not None and bool(explicit.get("assumption_note")),
        explicit["semester"].filename if explicit.get("semester") else "none",
    )

    via_ctx = resolve_semester_from_query(
        "מה הסילבוס?",
        catalogs,
        explicit_filename="courses_2025_200.json",
    )
    check(
        "explicit_filename override",
        via_ctx["semester"].filename == "courses_2025_200.json",
        f"confidence={via_ctx['confidence']}",
    )


def simulate_prerequisite_parser() -> None:
    section("[B] Prerequisite AST — edge cases")

    samples = [
        ("", {"type": "AND", "operands": []}),
        ("אין", {"type": "AND", "operands": []}),
        ("none", {"type": "AND", "operands": []}),
        ("() ", {"type": "AND", "operands": []}),
        (
            "(00440105 ו-00440140) או (00440105 ו-01140245)",
            {"type": "OR"},
        ),
        (
            "01040044 או 01040022 או 01040004",
            {"type": "OR"},
        ),
    ]
    for raw, expected_fragment in samples:
        ast = parse_prerequisites_string(raw)
        if "type" in expected_fragment:
            ok = ast["type"] == expected_fragment["type"]
        else:
            ok = ast == expected_fragment
        check(f"parse: {raw!r:.35}", ok, ast.get("type", "empty"))

    try:
        parse_prerequisites_string("00440105 ו-")
        check("malformed trailing AND raises", False, "no exception")
    except ValueError:
        check("malformed trailing AND raises", True)


def simulate_eligibility(engine: AcademicGraphEngine) -> None:
    section("[C] Eligibility OR-logic simulations")

    cases = [
        (["00440105", "00440140"], True),
        (["01140246", "00440105"], True),
        (["00440105"], False),
        ([], False),
    ]
    for completed, expected_eligible in cases:
        eligible, missing = engine.evaluate_eligibility(KNOWN_COURSE, completed)
        check(
            f"eligibility {KNOWN_COURSE} completed={completed}",
            eligible == expected_eligible,
            f"eligible={eligible} missing={missing}",
        )


def simulate_cross_semester(engine: AcademicGraphEngine) -> None:
    section("[D] Cross-semester catalog behavior")

    engine.set_active_semester("courses_2025_202.json", str(RAW))
    engine.build_graph()
    check("summer catalog smaller than spring", len(engine.course_catalog) < 200)

    summer_sched = engine.retrieve_context("schedule", course_id=KNOWN_COURSE)
    check("known course in summer has schedule", "no schedule data" not in summer_sched.lower())

    spring_only_sched = engine.retrieve_context("schedule", course_id=SPRING_ONLY)
    check(
        "spring-only course in summer → empty schedule marker",
        _block_is_empty(spring_only_sched),
        spring_only_sched.split("\n")[-1][:50],
    )

    engine.set_active_semester("courses_2025_201.json", str(RAW))
    engine.build_graph()
    spring_sched = engine.retrieve_context("schedule", course_id=SPRING_ONLY)
    check(
        "spring-only course in spring has schedule",
        "no schedule data" not in spring_sched.lower(),
    )


def simulate_wiki_and_missing(engine: AcademicGraphEngine) -> None:
    section("[E] Wiki search & missing data")

    nonsense = engine.retrieve_context("wiki_search", search_query="xyzzyplugh qwertyzz")
    check("nonsense wiki search → no matches", _block_is_empty(nonsense))

    rights = engine.retrieve_context("wiki_search", search_query="זכויות סטודנט")
    check("Hebrew student rights search hits", not _block_is_empty(rights), f"{len(rights)} chars")

    fake_slug = engine.retrieve_context("wiki_page", wiki_slug="this-page-does-not-exist-xyz")
    check("fake wiki slug → not found", _block_is_empty(fake_slug))

    fake_course = engine.retrieve_context("course_info", course_id="99999999")
    check("fake course id → not in catalog", "not found in catalog" in fake_course.lower())

    empty_search = engine.search_wiki("   ")
    check("empty wiki search tokens → []", empty_search == [])


def simulate_graph_tools(engine: AcademicGraphEngine) -> None:
    section("[F] Graph tools — agent simulation paths")

    tools = build_graph_tools(engine, str(RAW), ["00440105", "00440140"])
    check("four tools bound", len(tools) == 4)

    payload = json.loads(
        _retrieve_graph_data(
            engine,
            str(RAW),
            ["00440105"],
            "syllabus",
            course_id=KNOWN_COURSE,
            semester_filename="courses_2025_201.json",
        )
    )
    check("tool retrieval not empty", not payload.get("is_empty"))

    bad_semester = json.loads(
        _retrieve_graph_data(
            engine,
            str(RAW),
            [],
            "schedule",
            course_id=KNOWN_COURSE,
            semester_filename="courses_2099_201.json",
        )
    )
    check("invalid semester_filename → error block", bad_semester.get("is_empty") is True)

    dup = _dedupe_blocks(
        [{"intent": "syllabus", "course_id": KNOWN_COURSE, "wiki_slug": None, "search_query": None}],
        [{"intent": "syllabus", "course_id": KNOWN_COURSE, "wiki_slug": None, "search_query": None}],
    )
    check("dedupe duplicate retrieval blocks", len(dup) == 0)


def simulate_advisor_helpers() -> None:
    section("[G] Advisor helpers (no LLM)")

    codes = _extract_course_codes("מה הקדם של 00440148 וגם 02340112 בחורף?")
    check("extract course codes from Hebrew question", codes == ["00440148", "02340112"])

    he_fb = _default_fallback("מה הסילבוס?")
    en_fb = _default_fallback("What is the syllabus?")
    check("Hebrew fallback text", "לא מצאתי" in he_fb)
    check("English fallback text", "could not find" in en_fb.lower())

    max_iter = synthesize_answer(
        "test",
        [],
        retrieval_status="max_iterations",
        fallback_message="stopped",
    )
    check("max_iterations synthesis shortcut", max_iter.confidence == "low" and max_iter.answer == "stopped")


def simulate_graph_bridge_errors() -> None:
    section("[H] graph_bridge error & guard paths")

    bad_json = subprocess.run(
        [sys.executable, str(SCRIPTS / "graph_bridge.py")],
        input="{not json",
        capture_output=True,
        text=True,
        cwd=ROOT,
    )
    out = json.loads(bad_json.stdout)
    check("invalid JSON stdin", out.get("success") is False)

    missing_paths = bridge({"action": "stats"})
    check("missing paths rejected", missing_paths.get("success") is False)

    unknown = bridge(
        {
            "action": "explode",
            "md_dir_path": str(WIKI),
            "technion_raw_dir": str(RAW),
        }
    )
    check("unknown action rejected", unknown.get("success") is False)

    elig = bridge(
        {
            "action": "evaluate_eligibility",
            "course_id": KNOWN_COURSE,
            "user_completed_courses": ["00440105", "00440140"],
            "md_dir_path": str(WIKI),
            "technion_raw_dir": str(RAW),
            "semester_filename": "courses_2025_201.json",
        }
    )
    check(
        "bridge evaluate_eligibility",
        elig.get("success") and elig["data"]["eligible"] is True,
    )

    bad_sem = bridge(
        {
            "action": "stats",
            "md_dir_path": str(WIKI),
            "technion_raw_dir": str(RAW),
            "semester_filename": "courses_2099_201.json",
        }
    )
    check("bridge invalid semester fails gracefully", bad_sem.get("success") is False)


def simulate_data_integrity() -> None:
    section("[I] Data integrity on disk")

    if not RAW.is_dir():
        check("technion raw dir", False, "missing")
        return

    catalogs = discover_semester_catalogs(RAW)
    parse_errors = 0
    empty_courses = 0
    for path in sorted(RAW.glob("courses_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                parse_errors += 1
                continue
            codes = {
                str(e.get("general", {}).get("מספר מקצוע", "")).strip()
                for e in data
                if isinstance(e, dict)
            }
            codes.discard("")
            if not codes:
                empty_courses += 1
        except json.JSONDecodeError:
            parse_errors += 1

    check("all semester JSON files parse", parse_errors == 0, f"errors={parse_errors}")
    check("no empty course catalogs", empty_courses == 0, f"empty={empty_courses}")
    check("discovered catalogs match glob", len(catalogs) == len(list(RAW.glob("courses_*.json"))))

    # Prereq parse resilience across spring catalog
    spring_path = RAW / "courses_2025_201.json"
    if spring_path.is_file():
        data = json.loads(spring_path.read_text(encoding="utf-8"))
        failed = 0
        total_with_prereq = 0
        for entry in data:
            if not isinstance(entry, dict):
                continue
            raw = str(entry.get("general", {}).get("מקצועות קדם", "") or "").strip()
            if not raw:
                continue
            total_with_prereq += 1
            try:
                parse_prerequisites_string(raw)
            except ValueError:
                failed += 1
        check(
            "spring prereq strings parse (strict)",
            failed <= 1,
            f"{failed}/{total_with_prereq} failed",
        )
        if failed:
            warn(
                "catalog prereq strings with source typos (build_graph degrades gracefully)",
                f"{failed} unparseable",
            )


def simulate_student_journey(engine: AcademicGraphEngine) -> None:
    """End-to-end deterministic flows a student might trigger."""
    section("[J] Simulated student journeys (deterministic)")

    journeys = [
        {
            "name": "Can I take Waves? (eligibility)",
            "actions": [
                {"intent": "prerequisites", "course_id": KNOWN_COURSE},
                {"intent": "eligibility", "course_id": KNOWN_COURSE},
            ],
            "completed": ["00440105", "00440140"],
            "assert": lambda blocks: blocks[1]["facts"]["eligible"] is True,
        },
        {
            "name": "What track contains this course?",
            "actions": [{"intent": "structure", "course_id": KNOWN_COURSE}],
            "completed": [],
            "assert": lambda blocks: len(blocks[0]["context"]) > 30,
        },
        {
            "name": "Regulations + schedule combo",
            "actions": [
                {"intent": "wiki_search", "search_query": "נציב קבילות"},
                {"intent": "schedule", "course_id": KNOWN_COURSE},
            ],
            "completed": [],
            "assert": lambda blocks: len(blocks) == 2 and not _block_is_empty(blocks[0]["context"]),
        },
        {
            "name": "Missing prereqs path",
            "actions": [{"intent": "eligibility", "course_id": KNOWN_COURSE}],
            "completed": [],
            "assert": lambda blocks: blocks[0]["facts"]["eligible"] is False,
        },
    ]

    engine.set_active_semester("courses_2025_201.json", str(RAW))
    engine.build_graph()

    for journey in journeys:
        blocks = engine.execute_retrievals(
            journey["actions"],
            user_completed_courses=journey["completed"],
        )
        try:
            ok = journey["assert"](blocks)
        except Exception as exc:
            ok = False
            detail = str(exc)
        else:
            detail = f"{len(blocks)} blocks"
        check(f"journey: {journey['name']}", ok, detail)


def simulate_user_context_override(catalogs) -> None:
    section("[K] UserContext semester override (advise prep)")

    ctx = UserContext(
        semester_filename="courses_2025_200.json",
        completed_courses=["00440105"],
        track_slug="track-electrical-engineering",
    )
    result = resolve_semester_from_query(
        "מה לוח הזמנים של 00440148?",
        catalogs,
        explicit_filename=ctx.semester_filename,
    )
    check(
        "profile semester_filename wins over vague query",
        result["semester"].filename == "courses_2025_200.json",
    )


def main() -> int:
    print("=" * 60)
    print("UniPilot AI — SCENARIO SIMULATIONS (no API key)")
    print("=" * 60)

    if not WIKI.is_dir() or not RAW.is_dir():
        print("ERROR: wiki or technion data paths missing — run from full repo checkout.")
        return 1

    catalogs = discover_semester_catalogs(RAW)
    simulate_semester_resolution(catalogs)
    simulate_prerequisite_parser()

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(WIKI), str(RAW), semester_filename="courses_2025_201.json")
    engine.build_graph()

    simulate_eligibility(engine)
    simulate_cross_semester(engine)
    simulate_wiki_and_missing(engine)
    simulate_graph_tools(engine)
    simulate_advisor_helpers()
    simulate_graph_bridge_errors()
    simulate_data_integrity()
    simulate_student_journey(engine)
    simulate_user_context_override(catalogs)

    print("\n" + "=" * 60)
    print(f"SIMULATIONS COMPLETE: {PASS} passed, {FAIL} failed, {WARN} warnings")
    print("=" * 60)
    print("\nStill requires OPENAI_API_KEY:")
    print("  - Multi-iteration retrieval agent tool loop")
    print("  - Structured synthesis with real blocks")
    print("  - POST /advise via Node.js service")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
