"""Unit tests for schedule conflict detection."""

from __future__ import annotations

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.schedule_conflict import detect_plan_schedule_conflicts


def _build_engine(tmp_path) -> AcademicGraphEngine:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (raw / "courses_2025_201.json").write_text(
        """
        [
          {
            "general": {"מספר מקצוע": "00940111", "שם מקצוע": "Course A"},
            "schedule": [{"יום": "שני", "שעה": "10:30 - 12:30", "סוג": "הרצאה", "קבוצה": 11}]
          },
          {
            "general": {"מספר מקצוע": "00940112", "שם מקצוע": "Course B"},
            "schedule": [{"יום": "שני", "שעה": "11:00 - 13:00", "סוג": "הרצאה", "קבוצה": 12}]
          },
          {
            "general": {"מספר מקצוע": "00940113", "שם מקצוע": "Course C"},
            "schedule": [{"יום": "רביעי", "שעה": "10:30 - 12:30", "סוג": "הרצאה", "קבוצה": 13}]
          }
        ]
        """.strip(),
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()
    return engine


def test_detect_plan_schedule_conflicts_finds_overlap(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    conflicts, refs = detect_plan_schedule_conflicts(engine, ["00940111", "00940112"])
    assert len(conflicts) == 1
    assert conflicts[0]["courseA"] in {"00940111", "00940112"}
    assert any(ref.startswith("schedule_conflict:") for ref in refs)


def test_detect_plan_schedule_conflicts_ignores_non_overlapping(tmp_path) -> None:
    engine = _build_engine(tmp_path)
    conflicts, refs = detect_plan_schedule_conflicts(engine, ["00940111", "00940113"])
    assert conflicts == []
    assert "schedule:no_conflicts" in refs
