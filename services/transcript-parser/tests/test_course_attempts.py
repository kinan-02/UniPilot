"""Tests for transcript parser attempt numbering."""

from app.services.course_attempts import assign_sequential_course_attempts


def test_assign_sequential_course_attempts_numbers_retakes_across_semesters():
    rows = [
        ("00960401", "2023-1", 1),
        ("00960401", "2024-1", 1),
    ]

    assigned = assign_sequential_course_attempts(
        rows,
        course_number=lambda row: row[0],
        semester_code=lambda row: row[1],
        attempt=lambda row: row[2],
        with_attempt=lambda row, resolved: (row[0], row[1], resolved),
    )

    assert assigned == [
        ("00960401", "2023-1", 1),
        ("00960401", "2024-1", 2),
    ]
