"""Tests for vault OCR course-reference resolution."""

from app.vault.ocr_course_resolution import apply_ocr_resolutions_to_catalog


def test_apply_ocr_resolutions_removes_known_artifacts() -> None:
    document = {
        "programs": [
            {
                "programCode": "009216-1-000",
                "requirementGroups": [
                    {
                        "groupId": "009216-1-000:semester-2-matrix",
                        "courseReferences": [
                            {"courseNumber": "02300401", "titleHint": "bad ocr"},
                            {"courseNumber": "00940345", "titleHint": "valid"},
                        ],
                    }
                ],
            }
        ],
        "curationReport": {},
    }
    resolutions = apply_ocr_resolutions_to_catalog(
        document,
        ingestible_course_numbers={"00940345"},
    )
    refs = document["programs"][0]["requirementGroups"][0]["courseReferences"]
    numbers = [ref["courseNumber"] for ref in refs]
    assert numbers == ["00940345"]
    assert any(item.from_course_number == "02300401" for item in resolutions)


def test_cross_faculty_reference_is_preserved() -> None:
    document = {
        "programs": [
            {
                "programCode": "009009-1-000",
                "requirementGroups": [
                    {
                        "groupId": "009009-1-000:semester-1-matrix",
                        "courseReferences": [{"courseNumber": "01040042"}],
                    }
                ],
            }
        ],
        "curationReport": {},
    }
    apply_ocr_resolutions_to_catalog(
        document,
        ingestible_course_numbers={"00940345"},
    )
    refs = document["programs"][0]["requirementGroups"][0]["courseReferences"]
    assert refs[0]["courseNumber"] == "01040042"
