#!/usr/bin/env python3
"""Dry-run verification for the academic advisor stack (no OPENAI_API_KEY)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
WIKI = REPO / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
RAW = REPO / "services/data-engineering/data/raw/technion"

sys.path.insert(0, str(SRC))

from academic_graph_engine import AcademicGraphEngine, parse_prerequisites_string  # noqa: E402
from advisor_agent import UserContext, synthesize_answer  # noqa: E402
from graph_tools import _retrieve_graph_data, build_graph_tools  # noqa: E402
from semester_catalog import (  # noqa: E402
    discover_semester_catalogs,
    format_semester_catalog_summary,
    resolve_semester_from_query,
)

PASS = 0
FAIL = 0
COURSE = "00440148"


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ✓ {name}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"  ✗ {name}" + (f" — {detail}" if detail else ""))


def main() -> int:
    print("=" * 60)
    print("UniPilot AI Advisor — DRY RUN (no API key)")
    print("=" * 60)

    print("\n[1] Data paths")
    check("Wiki directory exists", WIKI.is_dir(), str(WIKI))
    check("Technion raw dir exists", RAW.is_dir(), str(RAW))
    json_files = sorted(RAW.glob("courses_*.json")) if RAW.is_dir() else []
    check("Semester JSON files on disk", len(json_files) > 0, f"{len(json_files)} files")
    for path in json_files:
        print(f"      - {path.name}")

    print("\n[2] Semester catalog discovery & resolution")
    catalogs = discover_semester_catalogs(RAW)
    check("Discovered semester catalogs", len(catalogs) > 0, str(len(catalogs)))
    if catalogs:
        for line in format_semester_catalog_summary(catalogs).splitlines():
            print(f"      {line}")

    expectations = [
        ("מה לוח הזמנים בסמסטר אביב 2026?", "courses_2025_201.json"),
        ("schedule for summer 2026", "courses_2025_202.json"),
        ("סמסטר חורף 2026", "courses_2025_200.json"),
    ]
    for query, expected in expectations:
        result = resolve_semester_from_query(query, catalogs, today=date(2026, 4, 1))
        semester = result.get("semester")
        fname = semester.filename if semester else None
        check(f"Resolve: {query[:42]}", fname == expected, fname or "none")

    default = resolve_semester_from_query("מה הסילבוס?", catalogs, today=date(2026, 4, 1))
    sem = default.get("semester")
    check(
        "Resolve default when semester unspecified",
        sem is not None and bool(default.get("assumption_note")),
        sem.filename if sem else "none",
    )

    print("\n[3] Prerequisite AST parser")
    ast = parse_prerequisites_string("(00440105 ו-00440140) או (00440105 ו-01140245)")
    check("OR/AND AST", ast["type"] == "OR" and len(ast["operands"]) == 2)

    print("\n[4] Graph engine (wiki + semester JSON)")
    engine = AcademicGraphEngine()
    engine.load_from_paths(str(WIKI), str(RAW), semester_filename="courses_2025_201.json")
    engine.build_graph()
    stats = engine.graph_stats()
    check("Graph built", stats.get("built") is True)
    check("Wiki pages loaded", stats.get("wiki_pages", 0) > 1000, str(stats.get("wiki_pages")))
    check("Active semester", stats.get("active_semester") == "courses_2025_201.json")
    check("Courses in catalog", stats.get("courses_in_catalog", 0) > 0, str(stats.get("courses_in_catalog")))
    print(
        f"      nodes={stats['nodes']} edges={stats['edges']} "
        f"relations={stats.get('edge_relations')}"
    )

    print("\n[5] Deterministic retrieval (wiki + JSON, no LLM)")
    for intent, kwargs in [
        ("schedule", {"course_id": COURSE}),
        ("syllabus", {"course_id": COURSE}),
        ("prerequisites", {"course_id": COURSE}),
        ("wiki_search", {"search_query": "זכויות סטודנט"}),
        ("wiki_page", {"wiki_slug": "student-rights"}),
    ]:
        try:
            context = engine.retrieve_context(
                intent,  # type: ignore[arg-type]
                user_completed_courses=["00440105", "00440140"],
                **kwargs,
            )
            ok = len(context) > 20
            check(f"retrieve_context({intent})", ok, f"{len(context)} chars")
        except Exception as exc:
            check(f"retrieve_context({intent})", False, str(exc))

    blocks = engine.execute_retrievals(
        [
            {"intent": "syllabus", "course_id": COURSE},
            {"intent": "eligibility", "course_id": COURSE},
        ],
        user_completed_courses=["00440105", "00440140"],
    )
    check("execute_retrievals (multi)", len(blocks) == 2)
    check("eligibility facts", blocks[1].get("facts", {}).get("eligible") is True)

    print("\n[6] Semester switch")
    summer = RAW / "courses_2025_202.json"
    if summer.is_file():
        engine.set_active_semester("courses_2025_202.json", str(RAW))
        engine.build_graph()
        sched = engine.retrieve_context("schedule", course_id=COURSE)
        check(
            "Summer schedule context",
            "Summer 2026" in sched or "courses_2025_202" in sched,
        )
    else:
        print("      (skipped — courses_2025_202.json not on disk)")

    print("\n[7] Graph tools layer")
    tools = build_graph_tools(engine, str(RAW), ["00440105", "00440140"])
    check("LangChain tools registered", len(tools) == 4, ", ".join(t.name for t in tools))
    tool_payload = json.loads(
        _retrieve_graph_data(engine, str(RAW), ["00440105"], "syllabus", course_id=COURSE)
    )
    check(
        "retrieve_graph_data tool",
        not tool_payload.get("is_empty")
        and tool_payload.get("data_source") == "wiki+semester_json",
    )

    print("\n[8] Fallback synthesis (no LLM)")
    fb = synthesize_answer(
        "מה הסילבוס?",
        [],
        retrieval_status="not_found",
        fallback_message="בדיקה — המידע לא נמצא",
    )
    check("Fallback without API", fb.confidence == "low" and "בדיקה" in fb.answer)

    print("\n[9] graph_bridge CLI")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC)
    env.pop("OPENAI_API_KEY", None)
    bridge_cases = [
        ("stats", {"action": "stats", "md_dir_path": str(WIKI), "technion_raw_dir": str(RAW)}),
        ("list_semesters", {"action": "list_semesters", "md_dir_path": str(WIKI), "technion_raw_dir": str(RAW)}),
        (
            "retrieve schedule",
            {
                "action": "retrieve_context",
                "intent": "schedule",
                "course_id": COURSE,
                "md_dir_path": str(WIKI),
                "technion_raw_dir": str(RAW),
            },
        ),
    ]
    for label, payload in bridge_cases:
        proc = subprocess.run(
            [sys.executable, str(SRC / "graph_bridge.py")],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            env=env,
            cwd=ROOT,
        )
        try:
            out = json.loads(proc.stdout)
            ok = out.get("success") is True and proc.returncode == 0
            check(f"graph_bridge:{label}", ok, proc.stderr[:120] if not ok else "")
        except json.JSONDecodeError as exc:
            check(f"graph_bridge:{label}", False, f"{exc} stdout={proc.stdout[:120]}")

    print("\n[10] LLM paths (expected guard without API key)")
    try:
        from advisor_agent import advise

        advise("test", engine, str(RAW), UserContext())
        check("advise without OPENAI_API_KEY", False, "should have raised")
    except RuntimeError as exc:
        check("advise blocks without OPENAI_API_KEY", "OPENAI_API_KEY" in str(exc))

    print("\n" + "=" * 60)
    print(f"DRY RUN COMPLETE: {PASS} passed, {FAIL} failed")
    print("=" * 60)
    print("\nSkipped (requires OPENAI_API_KEY):")
    print("  - run_retrieval_agent() tool loop")
    print("  - synthesize_answer() with real retrieval blocks")
    print("  - POST /advise end-to-end")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
