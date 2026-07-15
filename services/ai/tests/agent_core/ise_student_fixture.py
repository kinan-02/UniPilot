"""Seeds the realistic 2nd-year Information Systems Engineering student the
correctness eval asserts against.

Ground truth and provenance: `docs/agent/ISE_EVAL_FIXTURE.md`. Every course code
here was verified against the dev catalog: it exists in `courses`, and it was
actually offered in the term it is assigned to (17/17).

WHY courseIds are resolved, never fabricated
--------------------------------------------
`services/api`'s `student_user_context_service` resolves a transcript STRICTLY
through `courseId` -> `courses._id`:

    course_ids      = list(effective_completions.keys())
    catalog_courses = await find_courses_by_ids(database, course_ids)
    completed_numbers = [number_by_id[cid] for cid in course_ids if cid in number_by_id]

`metadata.courseNumber` is never consulted. A `courseId` that matches no catalog
course is silently dropped from `completed_courses` and merely bumps an
`unresolved_course_count` data-quality warning -- the agent then sees a student
with an EMPTY transcript.

The older EE fixture seeds `courseId=ObjectId()` (a random id matching nothing),
so its student's transcript resolves to zero completed courses. That is the
likely real cause of live-eval failures previously blamed on the agent (e.g.
`ref 'completed_courses' not found in facts (available: [])`).

So this fixture looks each course up by `courseNumber` at seed time and
**raises if any code fails to resolve** -- a fixture that silently seeds a
transcript into the void is worse than a failing test.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, AsyncIterator

import pytest
from bson import ObjectId

import app.db.mongo as mongo_module
from app.db.mongo import get_database


@pytest.fixture(autouse=True)
async def _fresh_mongo_client_per_test() -> AsyncIterator[None]:
    """`get_mongo_client()` memoizes an `AsyncIOMotorClient` at module scope,
    but `pytest.ini` sets `asyncio_default_fixture_loop_scope = function` -- a
    fresh event loop per test. Reusing a client created under a prior test's
    (now-closed) loop raises `RuntimeError: Event loop is closed`. Autouse here
    so it travels with `ise_student` to every module that imports it."""
    mongo_module._mongo_client = None
    yield
    if mongo_module._mongo_client is not None:
        mongo_module._mongo_client.close()
        mongo_module._mongo_client = None

# --- The student -----------------------------------------------------------

# Mirrors a REAL fully-registered ISE profile in the dev cluster:
#   facultyId "faculty-dds", programType "BSc", a real degreeId, and the track
#   declared under academicPath.trackSlug (NOT just programSlug).
#
# An earlier revision copied the older EE fixture's half-declared shape
# (degreeId=None, facultyId=None, academicPath={}). Live, the agent correctly
# refused to compute against it and asked a clarifying question instead:
#   "your degree program is not fully declared ... Are you pursuing the standard
#    4-year undergraduate degree in Information Systems Engineering ...?"
# That was honest agent behaviour exposing an unrealistic fixture -- a student
# who had really registered would have these populated.
PROGRAM_SLUG = "track-information-systems-engineering"
TRACK_SLUG = "track-information-systems-engineering"
CATALOG_YEAR = 2025
INSTITUTION_ID = "technion"
PROGRAM_TYPE = "BSc"
FACULTY_ID = "faculty-dds"
# The ISE degree program, matched by its verified programCode rather than a
# hardcoded ObjectId: real ISE profiles carry several degreeIds and most are
# orphaned (they resolve to no degree_programs doc at all).
DEGREE_PROGRAM_CODE = "009118-1-000"

# Semester 4 (spring). Verified: `YYYY-N` maps to `academicYear=YYYY`,
# `semesterCode=200+(N-1)` (200 winter, 201 spring, 202 summer) -- corroborated
# by a real plan named "תוכנית 2025-2026 · אביב (201)".
CURRENT_SEMESTER_CODE = "2025-2"

TOTAL_PROGRAM_CREDITS = 155.0

# Physical Education (1.0cr in semester 1 per the wiki plan) is deliberately NOT
# counted. It has no catalog course code, so it cannot be seeded as a
# `completed_courses` record -- meaning the agent has no way to see it. An
# earlier revision added it to `credits_earned` anyway, which invented 1.0
# credits of ground truth that exists nowhere in the data and made the eval
# demand an answer no correct agent could give. Ground truth is what is SEEDED:
# the 17 catalog courses, 62.5 credits.

# Completed transcript: semesters 1-3, exactly as the wiki track page documents
# it. Codes are seeded verbatim -- NO alternates are substituted. See the doc:
# the plan is authoritative, and two courses' registrar prereq lists simply do
# not name the `1מ2` variants ISE actually takes.
COMPLETED_BY_TERM: dict[str, list[tuple[str, float]]] = {
    # term: [(courseNumber, grade)]
    "2024-1": [
        ("00940345", 88.0),  # מתמטיקה דיסקרטית ת'
        ("00940704", 95.0),  # סדנת תכנות בשפת סי
        ("01040065", 76.0),  # אלגברה 1מ2
        ("01040042", 81.0),  # חשבון דיפרנציאלי ואינטגרלי 1מ2
        ("02340221", 90.0),  # מבוא למדעי המחשב נ'
    ],
    "2024-2": [
        ("00940210", 84.0),  # ארגון המחשב ומערכות הפעלה
        ("00940219", 91.0),  # הנדסת תוכנה
        ("00940411", 79.0),  # הסתברות ת'
        ("00940202", 87.0),  # מבוא לניתוח נתונים
        ("01040044", 72.0),  # חשבון דיפרנציאלי ואינטגרלי 2מ2
        ("03240033", 93.0),  # אנגלית טכנית-מתקדמים ב'
    ],
    "2025-1": [
        ("00940224", 85.0),  # מבני נתונים ואלגוריתמים
        ("00940241", 89.0),  # ניהול מסדי נתונים
        ("00940312", 77.0),  # מודלים דטרמיניסטים בחקר ביצועים
        ("00940424", 83.0),  # סטטיסטיקה 1
        ("00940564", 90.0),  # מבוא לניהול פיננסי
        ("00960570", 86.0),  # תורת המשחקים והתנהגות כלכלית
    ],
}

# Semester 4 plan. `00960211` (NOT the stale PDF code `0960221`, which appears
# nowhere in the system) -- confirmed by the project owner as the same course.
CURRENT_PLAN_COURSES: list[str] = [
    "00940314",  # מודלים סטוכסטיים בחקר ביצועים
    "00950605",  # מבוא לפסיכולוגיה
    "00960211",  # מודלים למסחר אלקטרוני
    "00960411",  # למידה חישובית 1
    "00970800",  # עקרונות השיווק
    "01140051",  # פיסיקה 1
]


class IseStudent:
    """The seeded student plus the ground truth an assertion may rely on."""

    def __init__(self, user_id: str, credits_earned: float) -> None:
        self.user_id = user_id
        self.credits_earned = credits_earned

    @property
    def credits_remaining(self) -> float:
        return TOTAL_PROGRAM_CREDITS - self.credits_earned

    @property
    def completed_course_numbers(self) -> list[str]:
        return [code for courses in COMPLETED_BY_TERM.values() for code, _ in courses]


async def _resolve_course_ids(database: Any, numbers: list[str]) -> dict[str, dict[str, Any]]:
    """Map courseNumber -> {_id, credits} from the real catalog.

    Raises on any miss: a transcript seeded with an unresolvable `courseId` is
    invisible to `student_user_context_service` (see module docstring), which
    would make the eval assert against a student with no completed courses.
    """
    resolved: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    for number in numbers:
        document = await database["courses"].find_one({"courseNumber": number}, {"_id": 1, "credits": 1})
        if document is None:
            missing.append(number)
            continue
        resolved[number] = {"_id": document["_id"], "credits": document.get("credits")}
    if missing:
        raise RuntimeError(
            f"ISE fixture cannot resolve {len(missing)} course code(s) against the catalog: {missing}. "
            "Seeding them would produce a student whose transcript silently resolves to nothing. "
            "See docs/agent/ISE_EVAL_FIXTURE.md."
        )
    return resolved


async def _resolve_degree_id(database: Any) -> Any:
    """The real `degree_programs._id` for ISE, matched by programCode.

    Raises on a miss: a null `degreeId` leaves the profile half-declared, and
    the agent then (correctly) asks which program the student is in rather than
    answering -- which looks like an agent failure but is a fixture defect.
    """
    document = await database["degree_programs"].find_one(
        {"programCode": DEGREE_PROGRAM_CODE}, {"_id": 1, "totalCredits": 1}
    )
    if document is None:
        raise RuntimeError(
            f"ISE fixture cannot resolve degree program {DEGREE_PROGRAM_CODE}. "
            "Seeding a null degreeId produces a half-declared student the agent will "
            "refuse to compute against. See docs/agent/ISE_EVAL_FIXTURE.md."
        )
    return document["_id"]


@pytest.fixture
async def ise_student() -> AsyncIterator[IseStudent]:
    """A 2nd-year ISE student in semester 4 (spring `2025-2`), seeded with real
    catalog `courseId`s so the transcript actually resolves."""
    database = await get_database()
    user_id = ObjectId()
    now = datetime.now(timezone.utc)

    all_numbers = [code for courses in COMPLETED_BY_TERM.values() for code, _ in courses]
    resolved = await _resolve_course_ids(database, all_numbers)
    degree_id = await _resolve_degree_id(database)

    # A FULLY-declared profile, matching the shape of real registered ISE
    # students: faculty + BSc + a real degreeId + the track under
    # academicPath.trackSlug. Anything less and the agent rightly asks which
    # program applies instead of answering.
    profile_document = {
        "userId": user_id,
        "institutionId": INSTITUTION_ID,
        "facultyId": FACULTY_ID,
        "programType": PROGRAM_TYPE,
        "degreeId": degree_id,
        "programSlug": PROGRAM_SLUG,
        "catalogYear": CATALOG_YEAR,
        "currentSemesterCode": CURRENT_SEMESTER_CODE,
        "academicPath": {
            "trackSlug": TRACK_SLUG,
            "minors": [],
            "specialPrograms": [],
            "graduatePrograms": [],
            "specializations": [],
        },
        "preferences": {},
        "revision": 1,
        "createdAt": now,
        "updatedAt": now,
    }

    completed_documents: list[dict[str, Any]] = []
    credits_earned = 0.0
    for term, courses in COMPLETED_BY_TERM.items():
        for number, grade in courses:
            entry = resolved[number]
            credits = float(entry["credits"])
            credits_earned += credits
            completed_documents.append(
                {
                    "userId": user_id,
                    # The real catalog _id -- the ONLY field the API resolves by.
                    "courseId": entry["_id"],
                    "courseOfferingId": None,
                    "semesterCode": term,
                    "grade": grade,
                    "gradePoints": None,
                    "creditsEarned": credits,
                    "attempt": 1,
                    "source": "manual",
                    # Real records carry an empty metadata dict; the API never
                    # reads courseNumber from here.
                    "metadata": {},
                    "recordedAt": now,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )

    await database["student_profiles"].insert_one(profile_document)
    await database["completed_courses"].insert_many(completed_documents)
    try:
        yield IseStudent(user_id=str(user_id), credits_earned=credits_earned)
    finally:
        await database["student_profiles"].delete_one({"userId": user_id})
        await database["completed_courses"].delete_many({"userId": user_id})
