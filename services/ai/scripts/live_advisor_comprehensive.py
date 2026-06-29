#!/usr/bin/env python3
"""Comprehensive live advisor tests — all worthy scenarios + performance metrics."""

from __future__ import annotations

import os
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[3]
SRC = ROOT / "src"
WIKI = REPO / "services/data-engineering/data/catalog_valut/catalog_valut/wiki"
RAW = REPO / "services/data-engineering/data/raw/technion"

sys.path.insert(0, str(SRC))

from academic_graph_engine import AcademicGraphEngine  # noqa: E402
from advisor_agent import UserContext, advise  # noqa: E402

KNOWN = "00440148"
SPRING_ONLY = "00440127"
SUMMER_ONLY = "01140074"
FAKE = "99999999"

PASS = FAIL = WARN = 0
METRICS: list[dict[str, Any]] = []


@dataclass
class Case:
    category: str
    name: str
    question: str
    context: UserContext = field(default_factory=UserContext)
    verify: Callable[[dict[str, Any], AcademicGraphEngine], tuple[bool, str]] | None = None
    allow_not_found: bool = False
    slow_threshold: float = 45.0


def check(ok: bool, label: str, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"      ✓ {label}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"      ✗ {label}" + (f" — {detail}" if detail else ""))


def note_warn(msg: str, detail: str = "") -> None:
    global WARN
    WARN += 1
    print(f"      ⚠ {msg}" + (f" — {detail}" if detail else ""))


def ans(r: dict[str, Any]) -> str:
    return str(r.get("response", {}).get("answer", ""))


def blocks(r: dict[str, Any]) -> list[dict[str, Any]]:
    return list(r.get("retrieval_blocks") or [])


def status(r: dict[str, Any]) -> str:
    return str(r.get("retrieval_agent", {}).get("status", ""))


def intents(r: dict[str, Any]) -> set[str]:
    return {str(b.get("intent")) for b in blocks(r)}


def nonempty(r: dict[str, Any]) -> int:
    return sum(1 for b in blocks(r) if not b.get("is_empty"))


def sem_file(r: dict[str, Any]) -> str:
    sem = r.get("semester_resolution", {}).get("semester") or {}
    return str(sem.get("filename", ""))


def has_kw(text: str, kws: list[str]) -> bool:
    return any(k in text or k.lower() in text.lower() for k in kws)


def intent_ok(r: dict[str, Any], *wanted: str) -> tuple[bool, str]:
    got = intents(r)
    ok = any(w in got for w in wanted)
    return ok, f"intents={sorted(got)}"


def sem_ok(r: dict[str, Any], expected: str) -> tuple[bool, str]:
    got = sem_file(r)
    return got == expected, f"semester={got}"


def eligible_graph(engine: AcademicGraphEngine, course: str, done: list[str]) -> bool:
    ok, _ = engine.evaluate_eligibility(course, done)
    return ok


# --- verifiers ---

def v_syllabus(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    a = ans(r)
    ok = "syllabus" in intents(r) and (KNOWN in a or "גלים" in a)
    return ok, f"syllabus intent, course ref"


def v_eligible_full(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    ok = eligible_graph(e, KNOWN, ["00440105", "00440140"])
    facts = any(b.get("facts", {}).get("eligible") for b in blocks(r))
    passed = ok and (facts or has_kw(ans(r), ["זכא", "eligible", "כן"]))
    return passed, "full branch"


def v_eligible_or_alt(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    ok = eligible_graph(e, KNOWN, ["01140246", "00440105"])
    passed = ok and has_kw(ans(r), ["זכא", "eligible", "כן", "00440105"])
    return passed, "OR alt branch"


def v_not_eligible(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return (not eligible_graph(e, KNOWN, []), "empty transcript")


def v_partial_prereq(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    ok = not eligible_graph(e, KNOWN, ["00440105"])
    passed = ok and has_kw(ans(r), ["לא", "חסר", "missing", "00440140", "קדם"])
    return passed, "partial"


def v_schedule_any(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    a = ans(r)
    return "schedule" in intents(r) and (
        bool(re.search(r"\d{1,2}:\d{2}", a)) or "יום" in a or "Sunday" in a
    ), "schedule + times"


def v_spring_sem(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    ok1, d1 = sem_ok(r, "courses_2025_201.json")
    ok2, d2 = v_schedule_any(r, e)
    return ok1 and ok2, f"{d1}; {d2}"


def v_winter_sem(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return sem_ok(r, "courses_2025_200.json")


def v_summer_sem(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return sem_ok(r, "courses_2025_202.json")


def v_spring_2025(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return sem_ok(r, "courses_2024_201.json")


def v_prereq(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return "prerequisites" in intents(r) and "00440105" in ans(r), "prereq codes"


def v_wiki(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    wiki = intents(r) & {"wiki_search", "wiki_page"}
    return bool(wiki) and nonempty(r) > 0, f"wiki intents {wiki}"


def v_wiki_rights(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    ok, d = v_wiki(r, e)
    passed = ok and has_kw(ans(r), ["זכויות", "סטודנט", "student", "rights"])
    return passed, d


def v_fake(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return status(r) in {"not_found", "ok"} and (
        r.get("response", {}).get("confidence") == "low"
        or has_kw(ans(r), ["לא נמצא", "not found", "לא מצאתי", "שגוי"])
    ), status(r)


def v_clarify_sem(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    res = r.get("semester_resolution", {})
    return res.get("needs_clarification") is True, str(res.get("assumption_note", ""))[:60]


def v_multi_intent(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return len(intents(r)) >= 2 and nonempty(r) >= 2, f"{len(intents(r))} intents"


def v_course_info(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return "course_info" in intents(r) or KNOWN in ans(r), intents(r).__str__()


def v_structure(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    got = intents(r)
    a = ans(r)
    ok = (
        "structure" in got
        or has_kw(a, ["מסלול", "track", "belongs", "פקולטה", "faculty"])
    )
    return ok, str(sorted(got))


def v_graceful(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return len(ans(r).strip()) > 15, "non-empty response"


def v_summer_course(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    return SUMMER_ONLY in ans(r) or "schedule" in intents(r), sem_file(r)


def v_assumption(r: dict, e: AcademicGraphEngine) -> tuple[bool, str]:
    res = r.get("semester_resolution", {})
    return bool(res.get("assumption_note")), sem_file(r)


CASES: list[Case] = [
    # A — Course intents
    Case("A: Course intents", "Hebrew syllabus", "מה הסילבוס של קורס 00440148?", verify=v_syllabus),
    Case("A: Course intents", "English syllabus", "What is the syllabus for course 00440148?", verify=v_syllabus),
    Case("A: Course intents", "Short Hebrew query", "סילבוס 00440148", verify=v_syllabus),
    Case("A: Course intents", "Course info", "מה שם הקורס וכמה נקודות ל-00440148?", verify=v_course_info),
    Case("A: Course intents", "Structure / track", "באיזה מסלול/פקולטה נמצא קורס 00440148?", verify=v_structure),
    # B — Eligibility
    Case("B: Eligibility", "Eligible — full AND branch", "האם אני זכאי לקורס 00440148?",
         UserContext(completed_courses=["00440105", "00440140"]), verify=v_eligible_full),
    Case("B: Eligibility", "Eligible — OR alt branch", "האם אני יכול לקחת 00440148?",
         UserContext(completed_courses=["01140246", "00440105"]), verify=v_eligible_or_alt),
    Case("B: Eligibility", "Not eligible — empty", "האם אני זכאי ל-00440148?",
         UserContext(completed_courses=[]), verify=v_not_eligible),
    Case("B: Eligibility", "Not eligible — partial prereqs", "האם אני זכאי ל-00440148?",
         UserContext(completed_courses=["00440105"]), verify=v_partial_prereq),
    Case("B: Eligibility", "English eligibility", "Am I eligible for course 00440148?",
         UserContext(completed_courses=["00440105", "00440140"]), verify=v_eligible_full),
    # C — Schedule + semester
    Case("C: Schedule & semester", "Spring 2026 schedule", "מה לוח הזמנים של 00440148 בסמסטר אביב 2026?", verify=v_spring_sem),
    Case("C: Schedule & semester", "Winter 2026 schedule", "מתי מתקיים 00440148 בחורף 2026?", verify=v_winter_sem),
    Case("C: Schedule & semester", "Summer 2026 schedule", "מה לוח הזמנים של 00440148 בקיץ 2026?", verify=v_summer_sem),
    Case("C: Schedule & semester", "English Spring schedule", "Schedule for 00440148 Spring 2026", verify=v_schedule_any),
    Case("C: Schedule & semester", "Year-only vague", "מתי הקורס 00440148 ב-2026?", verify=v_assumption),
    Case("C: Schedule & semester", "Historical Spring 2025", "לוח זמנים 00440148 באביב 2025", verify=v_spring_2025),
    Case("C: Schedule & semester", "Plan code summer", "schedule 00440148 plan 2025-3", verify=v_summer_sem),
    # D — Prerequisites
    Case("D: Prerequisites", "Hebrew prereqs", "מהם קורסי הקדם ל-00440148?", verify=v_prereq),
    Case("D: Prerequisites", "English prereqs", "What are the prerequisites for 00440148?", verify=v_prereq),
    # E — Wiki / regulations
    Case("E: Wiki", "Student rights", "מה זכויות הסטודנט בטכניון?", verify=v_wiki_rights),
    Case("E: Wiki", "Discipline regulations", "מה אומר תקנון משמעת הסטודנטים?", verify=v_wiki),
    Case("E: Wiki", "Ombudsman", "מי הנציב לקבילות סטודנטים ומה תפקידו?", verify=v_wiki),
    Case("E: Wiki", "Exam regulations search", "מה הכללים לגבי מבחנים מיוחדים?", verify=v_wiki),
    # F — Semester edge cases
    Case("F: Semester edge", "Contradictory Hebrew terms", "לוח זמנים 00440148 חורף ואביב 2026", verify=v_clarify_sem),
    Case("F: Semester edge", "Contradictory English terms", "00440148 schedule Winter Spring 2026", verify=v_clarify_sem),
    Case("F: Semester edge", "Profile semester override", "מה לוח הזמנים של 00440148?",
         UserContext(semester_filename="courses_2025_200.json"), verify=v_winter_sem),
    Case("F: Semester edge", "Profile plan code override", "סילבוס 00440148",
         UserContext(plan_semester_code="2025-3"), verify=v_summer_sem),
    Case("F: Semester edge", "Unspecified semester syllabus", "מה הסילבוס של 00440148?", verify=v_assumption),
    # G — Catalog edge cases
    Case("G: Catalog edge", "Fake course", f"מה הסילבוס של {FAKE}?", verify=v_fake, allow_not_found=True),
    Case("G: Catalog edge", "Spring-only in summer query", f"לוח זמנים {SPRING_ONLY} בקיץ 2026", verify=v_graceful),
    Case("G: Catalog edge", "Summer-only course", f"מתי מתקיים קורס {SUMMER_ONLY} בקיץ 2026?", verify=v_summer_course),
    # H — Multi-intent / complex
    Case("H: Multi-intent", "Eligibility + schedule", "האם אני זכאי ל-00440148 ומתי הוא מתקיים?",
         UserContext(completed_courses=["00440105", "00440140"]), verify=v_multi_intent),
    Case("H: Multi-intent", "Syllabus + prereqs + schedule", "תן סילבוס, קדם ולוח זמנים ל-00440148", verify=v_multi_intent),
    Case("H: Multi-intent", "Two courses mentioned", "מה הקדם של 00440148 ושל 00440105?", verify=v_graceful),
    # I — Out of scope / vague
    Case("I: Out of scope", "Off-topic weather", "מה מזג האוויר בחיפה מחר?", verify=v_graceful, allow_not_found=True),
    Case("I: Out of scope", "Vague study advice", "איך להתכונן למבחן בקורס 00440148?", verify=v_graceful),
    Case("I: Out of scope", "Greeting only", "שלום, אני סטודנט חדש", verify=v_graceful),
]


def run(engine: AcademicGraphEngine, case: Case) -> dict[str, Any]:
    t0 = time.monotonic()
    result = advise(case.question, engine, str(RAW), case.context)
    elapsed = time.monotonic() - t0
    return {**result, "_elapsed": elapsed}


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        print("ERROR: OPENAI_API_KEY required (source ../../.env)")
        return 1

    model = os.environ.get("OPENAI_CHAT_MODEL", "?")
    base = os.environ.get("OPENAI_BASE_URL", "OpenAI")

    print("=" * 72)
    print("UniPilot — COMPREHENSIVE LIVE ADVISOR TESTS")
    print(f"Model: {model} | API: {base}")
    print("=" * 72)

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(WIKI), str(RAW), semester_filename="courses_2025_201.json")
    engine.build_graph()
    print(f"Graph: {engine.graph_stats()['nodes']} nodes\n")

    current_cat = ""
    for i, case in enumerate(CASES, 1):
        if case.category != current_cat:
            current_cat = case.category
            print(f"\n{'─' * 72}\n{current_cat}\n{'─' * 72}")

        print(f"  [{i:02d}/{len(CASES)}] {case.name}")
        print(f"       Q: {case.question[:70]}{'…' if len(case.question) > 70 else ''}")

        try:
            result = run(engine, case)
        except Exception as exc:
            check(False, "pipeline", str(exc)[:100])
            METRICS.append({"name": case.name, "error": str(exc), "elapsed": 0})
            continue

        elapsed = float(result.get("_elapsed", 0))
        st = status(result)
        iters = int(result.get("retrieval_agent", {}).get("iterations", 0))
        nblocks = len(blocks(result))
        conf = result.get("response", {}).get("confidence", "?")
        answer = ans(result)

        METRICS.append({
            "name": case.name,
            "category": case.category,
            "elapsed": elapsed,
            "iterations": iters,
            "blocks": nblocks,
            "nonempty": nonempty(result),
            "status": st,
            "confidence": conf,
        })

        check(True, "pipeline", f"{elapsed:.1f}s | iter={iters} | blocks={nblocks} | {st}")
        if not case.allow_not_found:
            check(st != "not_found", "retrieval found data", st)
        check(len(answer.strip()) > 10, "answer length", f"{len(answer)} chars")
        check(conf in {"high", "medium", "low"}, "confidence", conf)

        if case.verify:
            ok, detail = case.verify(result, engine)
            check(ok, "verification", detail)

        if elapsed > case.slow_threshold:
            note_warn("slow case", f"{elapsed:.1f}s > {case.slow_threshold}s")

        preview = answer.replace("\n", " ")[:120]
        print(f"       → {preview}{'…' if len(answer) > 120 else ''}")

    # Performance summary
    times = [m["elapsed"] for m in METRICS if m.get("elapsed")]
    iters_list = [m["iterations"] for m in METRICS if "iterations" in m]
    blocks_list = [m["blocks"] for m in METRICS if "blocks" in m]

    print(f"\n{'=' * 72}")
    print("PERFORMANCE SUMMARY")
    print("=" * 72)
    if times:
        print(f"  Latency  — min {min(times):.1f}s | median {statistics.median(times):.1f}s | "
              f"max {max(times):.1f}s | total {sum(times):.1f}s")
    if iters_list:
        print(f"  Iterations — min {min(iters_list)} | median {statistics.median(iters_list):.0f} | max {max(iters_list)}")
    if blocks_list:
        print(f"  Blocks   — min {min(blocks_list)} | median {statistics.median(blocks_list):.0f} | max {max(blocks_list)}")

    slowest = sorted(METRICS, key=lambda m: m.get("elapsed", 0), reverse=True)[:5]
    print("\n  Slowest cases:")
    for m in slowest:
        if m.get("elapsed"):
            print(f"    {m.get('elapsed', 0):.1f}s — {m.get('name')}")

    by_cat: dict[str, list[float]] = {}
    for m in METRICS:
        by_cat.setdefault(m.get("category", "?"), []).append(m.get("elapsed", 0))
    print("\n  Median latency by category:")
    for cat, vals in sorted(by_cat.items()):
        print(f"    {cat}: {statistics.median(vals):.1f}s ({len(vals)} cases)")

    conf_counts: dict[str, int] = {}
    for m in METRICS:
        c = str(m.get("confidence", "?"))
        conf_counts[c] = conf_counts.get(c, 0) + 1
    print(f"\n  Confidence distribution: {conf_counts}")

    print(f"\n{'=' * 72}")
    print(f"RESULTS: {PASS} passed | {FAIL} failed | {WARN} warnings | {len(CASES)} cases")
    print("=" * 72)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
