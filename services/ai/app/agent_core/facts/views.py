"""Derivations moved out of the reasoning loop and into the data layer.

Two sources live here, and both exist for the same measured reason: the model
was rebuilding them, turn by turn, on every question that needed them.

`passed_courses` is the transcript filtered to what COUNTS, with course numbers
already joined. `remaining_courses` is a student's curriculum minus what they
have passed. Neither decides anything -- they join and they filter -- so they
compose with `select`, `group`, `plan_term` and `optimize` exactly as a stored
collection does. That is the line this module stays on the right side of: a
pre-solved `generate_semester_plan(student, track)` would answer the question;
these supply facts and leave the answering to the loop.

**Why they are `ViewSchema` and not aggregation pipelines.** `passed_courses`
could be a pipeline -- it is one store. `remaining_courses` cannot: the
curriculum comes from the wiki knowledge graph, held in memory as `contains`
edges, while the transcript comes from Mongo. No `$lookup` spans a collection and
a networkx graph. Both are views here so that the two read the same way, and so
that moving either one behind a pipeline later changes nothing the model sees.

In `unipilot-agent` these are SQL views over Postgres tables, because there the
graph was materialised at seed time. The declarations are deliberately kept
field-for-field identical to that repo's, so an answer grounded here and an
answer grounded there cite the same field names.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from app.agent_core.facts.find import ViewSchema
from app.agent_core.facts.sources import PASSED_EXPRESSION, PASSING_GRADE
from app.agent_core.facts.types import Basis, ScalarKind

_Q = ScalarKind.QUANTITY
_I = ScalarKind.IDENTIFIER
_T = ScalarKind.TEXT

# Headings on a track's wiki page, and what a course listed under one is.
#
# ELECTIVE IS TESTED FIRST, because the two vocabularies overlap in one
# direction only: a heading like "קורסי בחירה לפי סמסטר" ("elective courses by
# semester") contains the semester word that otherwise means mandatory, while no
# mandatory heading contains an elective word. Testing mandatory first types
# every course under that heading as required.
_ELECTIVE_HEADING = re.compile(
    r"elective|specializ|chain|group\s*\d|בחירה|קבוצה|שרשרת|התמחות|מיקוד", re.I
)
_MANDATORY_HEADING = re.compile(r"required|mandatory|semester\s*\d|core\b|חובה|סמסטר", re.I)

_HEADING = re.compile(r"^(#{1,6})\s*(.+)$")


def track_categories(engine: Any) -> dict[tuple[str, str], str]:
    """`(track slug, course NUMBER) -> "mandatory" | "elective"`, from the headings.

    The graph records that a track page LINKS to a course, and drops the section
    the link sat under -- so `track_courses` could say what a track contains but
    not which part of it was a choice. This reads the section back off the page.

    Keyed by course NUMBER, resolved the same way `build_graph` resolves an edge
    target, so these keys line up with the `contains` edges rather than nearly
    doing so.

    Coverage is 85.7% of track->course links (measured across 67 track pages);
    the remainder sit under headings that do not say, and are left UNTYPED rather
    than guessed. An elective wrongly typed as mandatory is a course the student
    is told they must take.
    """
    from app.retrieval.graph_engine.academic_graph_engine import _extract_wikilinks

    pages = getattr(engine, "wiki_pages", {})
    by_slug = getattr(engine, "slug_to_course_code", {})

    def course_number(slug: str) -> str | None:
        page = pages.get(slug)
        code = (page or {}).get("course_code") or by_slug.get(slug)
        return str(code) if code else None

    categories: dict[tuple[str, str], str] = {}
    for slug, page in pages.items():
        if page.get("kind") != "track":
            continue
        heading = ""
        for line in page.get("content", "").splitlines():
            matched = _HEADING.match(line)
            if matched:
                heading = matched.group(2).strip()
                continue
            if _ELECTIVE_HEADING.search(heading):
                category = "elective"
            elif _MANDATORY_HEADING.search(heading):
                category = "mandatory"
            else:
                continue
            for target, _display in _extract_wikilinks(line):
                code = course_number(target)
                if code:
                    # First heading wins: a course listed once as required and
                    # again in an elective group is required.
                    categories.setdefault((slug, code), category)
    return categories


async def _passed_documents(database: Any) -> list[dict[str, Any]]:
    """Every passing transcript row, with its course code and title joined on.

    The `$addFields` stage is the same expression `completed_courses` declares as
    a computed field, so "passed" means one thing in both places. Sharing the
    expression rather than restating it is the point: a view that filtered on its
    own private copy of the pass rule could drift from the column the model sees.
    """
    pipeline = [
        {"$addFields": {"passed": PASSED_EXPRESSION}},
        {"$match": {"passed": True}},
        {
            "$lookup": {
                "from": "courses",
                "localField": "courseId",
                "foreignField": "_id",
                "as": "_course",
            }
        },
        # `preserveNullAndEmptyArrays`, so a transcript row whose catalog entry is
        # missing still appears -- without a course number. Dropping it would
        # quietly shrink the student's completed credits.
        {"$unwind": {"path": "$_course", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 0,
                "courseId": {"$toString": "$courseId"},
                "userId": {"$toString": "$userId"},
                "courseNumber": "$_course.courseNumber",
                "title": "$_course.title",
                "grade": 1,
                "creditsEarned": 1,
                "creditsCounted": {"$ifNull": ["$creditsEarned", 0]},
                "semesterCode": 1,
                "attempt": 1,
            }
        },
    ]
    return await database["completed_courses"].aggregate(pipeline).to_list(None)


def passed_courses_source(engine: Any) -> ViewSchema:
    """The transcript filtered to what COUNTS, course codes already joined.

    The answer to a defect that appeared three times in three consumers: total
    credits, the term planner's prerequisite flag, and the agent's own
    eligibility reasoning -- which told a student they met 1 of 1 prerequisite
    groups because they had ATTEMPTED the course that satisfies it and been
    graded 32.

    Every one of those was the same mistake, reading a transcript row as a course
    the student HAS, and the first two were fixed at the point of use. This is the
    structural fix: a source that is already filtered cannot be misused that way.

    `completed_courses` stays registered and is still the right source for
    anything about ATTEMPTS -- a failed course that must be re-taken, a grade
    history, how many times something was sat. This view cannot answer those, by
    construction.
    """
    return ViewSchema(
        collection="passed_courses",
        key="courseId",
        fields={
            "courseId": _I,
            "userId": _I,
            "courseNumber": _I,
            "title": _T,
            "grade": _Q,
            "creditsEarned": _Q,
            "creditsCounted": _Q,
            "semesterCode": _I,
            "attempt": _Q,
        },
        field_notes={
            "courseNumber": (
                "the course code, ALREADY joined from `courses`. Absent on a row whose catalog "
                "entry is missing -- which is unrecoverable, not a bug to route around: a "
                "comparison against it simply does not match, so eligibility comes back denied "
                "rather than granted."
            ),
            "grade": f"always {PASSING_GRADE} or above here; failing attempts are not in this view.",
            "creditsCounted": (
                "credits that COUNT toward the degree. Every row here is ALSO a row in "
                "`completed_courses` -- this view is that table filtered, not a second set of "
                "results. Sum ONE of them, never both: adding the two together double-counts "
                "every passed course and reports a student past a requirement they have not met."
            ),
        },
        basis=Basis.OFFICIAL_RECORD,
        joins=(("courseNumber", "courses.courseNumber"), ("courseId", "courses._id")),
        produce=_passed_documents,
        # `courseId` repeats across students and retakes, exactly as it does on
        # `completed_courses`; without a tie-break a truncated fetch returns a
        # different page each run.
        order_tiebreak=("userId", "attempt"),
    )


def remaining_courses_source(engine: Any) -> ViewSchema:
    """The curriculum minus the transcript, computed once instead of in turns.

    Three live planning runs each spent four to six turns rebuilding exactly this
    before reaching `plan_term` -- find the track courses, find the transcript,
    find the catalog rows, then a `difference` on course number -- at roughly
    fifteen seconds a turn. It is also where the courseId/courseNumber mix-up
    silently reported every course as still remaining, because a comparison
    between an ObjectId and an 8-digit code matches nothing and an empty
    difference removes nothing.
    """
    categories = None

    async def produce(database: Any) -> Sequence[Mapping[str, Any]]:
        nonlocal categories
        if categories is None:
            categories = track_categories(engine)
        return await _remaining_documents(database, engine, categories)

    return ViewSchema(
        collection="remaining_courses",
        key="courseNumber",
        fields={
            "userId": _I,
            "courseNumber": _I,
            "title": _T,
            "credits": _Q,
            "category": _I,
            "track": _I,
            "curriculumAvailable": ScalarKind.BOOL,
        },
        field_notes={
            "curriculumAvailable": (
                "PRESENT ONLY WHEN FALSE, AND ONLY ON A ROW THAT IS NOT A COURSE. It means the "
                "catalog has no curriculum for this student's track at all -- the vault covers "
                "undergraduate tracks, and a graduate one has no course list in it. Such a row "
                "carries no title and no credits, and its `courseNumber` is a sentence saying so. "
                "SAY THAT THE CURRICULUM IS NOT AVAILABLE. Do not report it as a course, do not "
                "count it, and above all do not read the absence as a finished degree -- these "
                "students have not completed anything."
            ),
            "courseNumber": (
                "a course in THIS student's track that they have not passed. Filter by `userId` "
                "and this is the whole remaining curriculum, already joined to the catalog for "
                "`title` and `credits` and already typed by `category`. START PLANNING QUESTIONS "
                "HERE."
            ),
            "credits": (
                "from the catalog, for picking WHAT to take. NEVER SUM THEM TO GET WHAT IS LEFT: "
                "a track lists more courses than the degree requires, because its electives are "
                "choices. What is left is `degree_programs.totalCredits` minus the sum of "
                "`passed_courses.creditsCounted`.\n"
                "     THAT INCLUDES A PROJECTED GPA. Weight a projection by the credits still to "
                "EARN, not by the credits of every unfinished course, or the projection is "
                "spread over a longer degree than the student is doing."
            ),
            "category": (
                "\"mandatory\" or \"elective\". Take every mandatory one, then add electives only "
                "until their credits reach what is still needed -- that set is what you plan. "
                "Handing the whole unfinished set to `plan_term` or `optimize` schedules "
                "electives the student never has to take, and reports a longer degree than they "
                "are doing. ABSENT on about one row in seven, where the track page's headings do "
                "not say."
            ),
            "track": (
                "the student's track as `track_courses` names it -- every row here already "
                "belongs to it, so filtering by it as well as by `userId` narrows nothing. It "
                "can differ in form from the profile's `programSlug`, which is why filtering "
                "`track_courses` by a raw `programSlug` can come back empty where this does not."
            ),
        },
        basis=Basis.OFFICIAL_RECORD,
        joins=(("courseNumber", "courses.courseNumber"),),
        produce=produce,
        # `courseNumber` repeats -- once per student whose track lists it.
        order_tiebreak=("userId",),
    )


_TRACK_PREFIX = "track-"

NO_CURRICULUM = "(no curriculum in the catalog for this track)"
"""The `courseNumber` of the row that stands in for a curriculum we do not have.

Deliberately a sentence and not a code. Every real course number is eight digits,
so this cannot collide with one, cannot be looked up as one, and reads as an
explanation wherever it surfaces -- including if a model quotes it verbatim.
"""


def _resolve_track(program_slug: str, contains: Mapping[str, Any]) -> str | None:
    """A profile's `programSlug` as the graph names it, or `None`.

    The two namespaces very nearly agree. Every one of the graph's 52 track
    pages is slugged `track-<name>`, and most profiles store exactly that -- but
    some store the bare `<name>`, and a bare one matches no node at all.

    That mismatch does not fail; it returns an empty curriculum, which reads as
    "you have nothing left to take". Measured before this fallback existed: every
    `electrical-engineering` profile got `remaining=0` while
    `track-electrical-engineering` sat in the graph with a full course list.

    The fallback is exact-then-prefixed, never fuzzy: a near-miss on a track name
    would plan someone else's degree, which is worse than declining to plan.
    """
    if program_slug in contains:
        return program_slug
    prefixed = f"{_TRACK_PREFIX}{program_slug}"
    return prefixed if prefixed in contains else None


async def _remaining_documents(
    database: Any, engine: Any, categories: Mapping[tuple[str, str], str]
) -> list[dict[str, Any]]:
    """One row per (student, unpassed course in their track).

    Built for every student with a track rather than for one, because a
    `ViewSchema` producer does not see the predicate: `find` filters what comes
    back. That is affordable here -- a track lists on the order of a hundred
    courses and few profiles carry a `programSlug` -- and it keeps the view's
    semantics identical to the SQL one, which is also defined over all students.
    """
    graph = getattr(engine, "graph", None)
    if graph is None:
        return []

    contains: dict[str, list[str]] = {}
    for source, target, data in graph.edges(data=True):
        if data.get("relation") != "contains":
            continue
        contains.setdefault(str(source), []).append(str(target))

    catalog = {
        str(document["courseNumber"]): document
        async for document in database["courses"].find(
            {"courseNumber": {"$exists": True}}, {"courseNumber": 1, "title": 1, "credits": 1}
        )
    }

    passed_by_user: dict[str, set[str]] = {}
    for row in await _passed_documents(database):
        number = row.get("courseNumber")
        if number:
            passed_by_user.setdefault(str(row["userId"]), set()).add(str(number))

    documents: list[dict[str, Any]] = []
    async for profile in database["student_profiles"].find(
        {"programSlug": {"$exists": True, "$ne": None}}, {"userId": 1, "programSlug": 1}
    ):
        track = _resolve_track(str(profile["programSlug"]), contains)
        if track is None:
            # The student HAS a track and the graph has no page for it. This used
            # to `continue`, on the reasoning that emitting nothing reads as
            # absence rather than as an empty curriculum. It does not. `find`
            # filters by `userId`, so both cases arrive as zero records marked
            # COMPLETE, and a complete zero is exactly what a finished degree
            # looks like. Measured: 8 of the 81 profiles carrying a track are on
            # `grad-direct-doctorate-track`, and the vault holds 52 undergraduate
            # tracks and no graduate ones -- so 8 students were being told they
            # had nothing left to take, permanently, and correctly-absent data
            # was doing it.
            #
            # The row says so instead. It carries NO courseNumber, title or
            # credits, because a row with them would be counted, summed and
            # planned as a course to take -- trading a silent wrong answer for a
            # loud one.
            # It carries a `courseNumber` because it has to: `_from_documents`
            # converts EVERY document before filtering, and a row missing the key
            # is a DataDefect that it returns immediately -- so one keyless row
            # here would break `remaining_courses` for every student, not just
            # this one. The value is a sentence rather than an 8-digit code, so
            # nothing reads it as a course.
            documents.append(
                {
                    "userId": str(profile["userId"]),
                    "courseNumber": NO_CURRICULUM,
                    "track": str(profile["programSlug"]),
                    "curriculumAvailable": False,
                }
            )
            continue
        user_id = str(profile["userId"])
        already = passed_by_user.get(user_id, set())
        for code in contains.get(track, ()):
            if code in already:
                continue
            course = catalog.get(code, {})
            row = {
                "userId": user_id,
                "courseNumber": code,
                "track": track,
                "title": course.get("title"),
                "credits": course.get("credits"),
            }
            category = categories.get((track, code))
            # OMITTED rather than set to a placeholder when the headings do not
            # say. An undeclared field is simply absent, and a filter on it fails
            # to match; a "unknown" string would be a category the model could
            # reason about as though it meant something.
            if category:
                row["category"] = category
            documents.append(row)

    return documents


__all__ = [
    "passed_courses_source",
    "remaining_courses_source",
    "track_categories",
]
