"""Unit tests for semester-matrix filtering in graduation progress."""

from __future__ import annotations

from app.services.matrix_semester_filters import (
    filter_executable_matrix_documents,
    is_executable_matrix_reference,
)


def test_is_executable_matrix_reference_rejects_advisory_rows() -> None:
    assert not is_executable_matrix_reference(
        {"courseNumber": "00000004", "titleHint": "Science slot"}
    )
    assert not is_executable_matrix_reference(
        {"courseNumber": "01340058", "titleHint": "מקצוע מדעי"}
    )
    assert not is_executable_matrix_reference(
        {"courseNumber": "01040135", "titleHint": "קורס מתמטי נוסף"}
    )
    assert is_executable_matrix_reference(
        {"courseNumber": "02340118", "titleHint": "ארגון ותכנות המחשב"}
    )


def test_filter_executable_matrix_documents_keeps_concrete_courses() -> None:
    documents = [
        {
            "groupId": "023044-1-000:semester-4-matrix",
            "courseReferences": [
                {"courseNumber": "02340118", "titleHint": "ארגון ותכנות המחשב"},
                {"courseNumber": "01340058", "titleHint": "מקצוע מדעי"},
                {"courseNumber": "00000004", "titleHint": "placeholder"},
            ],
        }
    ]
    filtered = filter_executable_matrix_documents(documents)
    assert len(filtered) == 1
    numbers = {ref["courseNumber"] for ref in filtered[0]["courseReferences"]}
    assert numbers == {"02340118"}
