"""Synthetic sample academic records for staging pipeline foundation tests.

These records are NOT real Technion DDS data. They exist only to exercise
validation and staging import without touching production catalog collections.
"""

from datetime import datetime, timezone

SAMPLE_SOURCE_NAME = "synthetic-dds-sample"
SAMPLE_SOURCE_TYPE = "manual_sample"
SAMPLE_RETRIEVED_AT = datetime(2026, 6, 19, tzinfo=timezone.utc)

SAMPLE_COURSES: list[dict] = [
    {
        "institutionId": "technion-dds-sample",
        "subject": "0096",
        "number": "00960001",
        "title": "Sample Introduction to Data Science",
        "credits": 3,
        "description": "Synthetic sample course for staging ingestion foundation tests.",
        "level": "undergraduate",
        "tags": ["sample", "dds-foundation"],
        "prerequisiteCourseIds": [],
        "corequisiteCourseIds": [],
        "catalogYear": 2025,
        "catalogVersion": "sample-2025.1",
        "version": "sample-2025.1",
        "status": "staging",
        "metadata": {
            "isSampleData": True,
            "isCuratedPlaceholder": True,
            "faculty": "Data and Decision Sciences (sample)",
            "note": "NOT real Technion DDS data",
        },
        "sourceRefs": [
            {
                "sourceId": "synthetic-dds-sample-v1",
                "locator": "course:00960001",
                "retrievedAt": SAMPLE_RETRIEVED_AT.isoformat(),
            }
        ],
    },
    {
        "institutionId": "technion-dds-sample",
        "subject": "0096",
        "number": "00960002",
        "title": "Sample Probability for Analytics",
        "credits": 3,
        "description": "Second synthetic sample course linked to the sample requirement set.",
        "level": "undergraduate",
        "tags": ["sample", "mathematics"],
        "prerequisiteCourseIds": ["665f2b0f2a3f7b2a1a9a7f01"],
        "corequisiteCourseIds": [],
        "catalogYear": 2025,
        "catalogVersion": "sample-2025.1",
        "version": "sample-2025.1",
        "status": "staging",
        "metadata": {
            "isSampleData": True,
            "isCuratedPlaceholder": True,
            "faculty": "Data and Decision Sciences (sample)",
            "note": "NOT real Technion DDS data",
        },
        "sourceRefs": [
            {
                "sourceId": "synthetic-dds-sample-v1",
                "locator": "course:00960002",
                "retrievedAt": SAMPLE_RETRIEVED_AT.isoformat(),
            }
        ],
    },
]

SAMPLE_DEGREE_REQUIREMENTS: list[dict] = [
    {
        "degreeId": "665f2b0f2a3f7b2a1a9a7d01",
        "version": "sample-2025.1",
        "catalogYear": 2025,
        "catalogVersion": "sample-2025.1",
        "requirementType": "core",
        "title": "Sample DDS core course set",
        "ruleExpression": {"type": "course_set", "operator": "all_of"},
        "minCredits": 6,
        "courseIds": ["665f2b0f2a3f7b2a1a9a7f01", "665f2b0f2a3f7b2a1a9a7f02"],
        "priority": 1,
        "isMandatory": True,
        "status": "staging",
        "metadata": {
            "isSampleData": True,
            "isCuratedPlaceholder": True,
            "note": "NOT real Technion DDS data",
        },
        "sourceRefs": [
            {
                "sourceId": "synthetic-dds-sample-v1",
                "locator": "requirement:sample-core",
                "retrievedAt": SAMPLE_RETRIEVED_AT.isoformat(),
            }
        ],
    }
]

# Invalid sample used only by validate-sample to demonstrate error capture.
INVALID_SAMPLE_COURSE: dict = {
    "institutionId": "",
    "subject": "0096",
    "number": "bad",
    "title": "Invalid Sample Course",
    "credits": 99,
    "description": "This record should fail validation.",
    "level": "undergraduate",
    "tags": [],
    "prerequisiteCourseIds": ["not-an-object-id"],
    "corequisiteCourseIds": [],
    "catalogYear": 2025,
    "catalogVersion": "sample-2025.1",
    "version": "sample-2025.1",
    "status": "staging",
    "metadata": {"isSampleData": True},
    "sourceRefs": [],
}
