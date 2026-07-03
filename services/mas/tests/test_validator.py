"""Unit tests for MAS pre-commit validator."""

from __future__ import annotations

from app.services.academic_graph_engine import AcademicGraphEngine
from app.validator.pre_commit import validate_plan_proposal


def test_validate_plan_rejects_unknown_course(tmp_path):
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (raw / "courses_2025_201.json").write_text(
        '[{"general": {"מספר מקצוע": "00940139", "שם מקצוע": "Stats"}, "schedule": []}]',
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()

    ok, violations, _refs = validate_plan_proposal(
        course_ids=["99999999"],
        engine=engine,
        completed_courses=[],
    )
    assert ok is False
    assert any("not in the active semester catalog" in item for item in violations)


def test_validate_plan_rejects_schedule_conflict(tmp_path):
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (raw / "courses_2025_201.json").write_text(
        """
        [
          {
            "general": {"מספר מקצוע": "00940111", "שם מקצוע": "A"},
            "schedule": [{"יום": "שני", "שעה": "10:30 - 12:30", "סוג": "הרצאה"}]
          },
          {
            "general": {"מספר מקצוע": "00940112", "שם מקצוע": "B"},
            "schedule": [{"יום": "שני", "שעה": "11:00 - 13:00", "סוג": "הרצאה"}]
          }
        ]
        """.strip(),
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()

    ok, violations, _refs = validate_plan_proposal(
        course_ids=["00940111", "00940112"],
        engine=engine,
        completed_courses=[],
    )
    assert ok is False
    assert any("Schedule conflict" in item for item in violations)


def test_validate_plan_accepts_catalog_course(tmp_path):
    raw = tmp_path / "technion"
    raw.mkdir()
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    (raw / "courses_2025_201.json").write_text(
        '[{"general": {"מספר מקצוע": "00940139", "שם מקצוע": "Stats"}, "schedule": []}]',
        encoding="utf-8",
    )
    (wiki / "index.md").write_text("# index\n", encoding="utf-8")

    engine = AcademicGraphEngine()
    engine.load_from_paths(str(wiki), str(raw), semester_filename="courses_2025_201.json")
    engine.build_graph()

    ok, violations, _refs = validate_plan_proposal(
        course_ids=["00940139"],
        engine=engine,
        completed_courses=[],
    )
    assert ok is True
    assert violations == []
