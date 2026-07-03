"""Unit tests for MAS schedule summary builder."""

from __future__ import annotations

from app.services.academic_graph_engine import AcademicGraphEngine
from app.services.plan_schedule import build_plan_schedule_summary


def test_build_plan_schedule_summary_includes_courses_and_semester(tmp_path) -> None:
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (raw / "courses_2025_201.json").write_text(
        """
        [
          {
            "general": {"מספר מקצוע": "00940139", "שם מקצוע": "Intro Stats", "נקודות": "3"},
            "schedule": [{"יום": "שני", "שעה": "10:30 - 12:30", "סוג": "הרצאה", "קבוצה": 11}]
          }
        ]
        """.strip(),
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()

    summary = build_plan_schedule_summary(
        engine=engine,
        course_ids=["00940139"],
        semester_filename="courses_2025_201.json",
    )

    assert summary["planSemesterCode"] == "2025-2"
    assert summary["totalCredits"] == 3.0
    assert len(summary["courses"]) == 1
    assert summary["courses"][0]["slots"][0]["day"] == "שני"
