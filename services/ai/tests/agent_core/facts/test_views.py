"""The four sources the standalone agent has and this one did not.

Two of them -- `prerequisite_edges` and `track_courses` -- were already derived
from the knowledge graph here. What was missing was the pass/fail distinction
underneath everything else: Mongo stores `grade` and `creditsEarned` and nothing
that says whether a course COUNTS, so every consumer re-derived it and three of
them got it wrong in three different ways.

These tests are about the failure that has no symptom. A guard that goes silent,
a join that matches nothing, a filter on a field that does not exist yet: all of
them keep a suite green while the answer goes quietly wrong. So the assertions
here are mostly of the form "this is not empty" and "this filtered result still
counts itself honestly".
"""

from __future__ import annotations

import pytest

from tests.agent_core.ise_student_fixture import (  # noqa: F401 -- autouse fixture
    _fresh_mongo_client_per_test,
)
from app.agent_core.facts.find import find
from app.agent_core.facts.predicate import Comparison, Op, Path
from app.agent_core.facts.sources import COMPLETED_COURSES, PASSING_GRADE
from app.agent_core.facts.sources import REGISTRY as REGISTRY_FOR_SEEDING
from app.agent_core.facts.types import Collection, Scalar, ScalarKind
from app.agent_core.facts.views import NO_CURRICULUM, _resolve_track, track_categories

B = ScalarKind.BOOL
I = ScalarKind.IDENTIFIER

# A transcript in miniature, carrying the exact shape that caused the defect:
# `failed` was sat and graded 32 and STILL records its full 5.5 credits, which is
# real registrar data, not a contrivance -- one live row looks precisely so.
TRANSCRIPT = [
    {"courseId": "c1", "userId": "u1", "grade": 95.0, "creditsEarned": 3.5, "attempt": 1},
    {"courseId": "c2", "userId": "u1", "grade": 32.0, "creditsEarned": 5.5, "attempt": 1},
    {"courseId": "c2", "userId": "u1", "grade": 78.0, "creditsEarned": 5.5, "attempt": 2},
    {"courseId": "c3", "userId": "u1", "creditsEarned": 4.0, "attempt": 1},  # never graded
]


@pytest.fixture
async def database():
    from app.db.mongo import get_database

    try:
        handle = await get_database()
        await handle.command("ping")
        client = handle.client
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"NOT VERIFIED: no database ({type(exc).__name__}). "
            "The pass/fail derivation and the two views are UNCHECKED in this run."
        )
    db = client["unipilot_views_test"]
    await db["completed_courses"].delete_many({})
    await db["completed_courses"].insert_many([dict(d) for d in TRANSCRIPT])
    yield db
    await client.drop_database("unipilot_views_test")
    client.close()


def passed_is(value: bool) -> Comparison:
    return Comparison(Path.parse("passed"), Op.EQ, Scalar(B, value))


class TestTheDerivedPassFlag:
    async def test_a_failed_attempt_counts_no_credits(self, database) -> None:
        """The whole point. `creditsEarned` is 5.5 on a course graded 32, and
        summing it is how a student was told 135 credits when the answer was
        129.5."""
        result = await find(database, COMPLETED_COURSES)
        failed = [r for r in result.records if r.fields.get("grade") and r.fields["grade"].value == 32.0][0]
        assert failed.fields["creditsEarned"].value == 5.5
        assert failed.fields["creditsCounted"].value == 0
        assert failed.fields["passed"].value is False

    async def test_a_retake_of_the_same_course_counts_once_it_is_passed(self, database) -> None:
        result = await find(database, COMPLETED_COURSES)
        retake = [r for r in result.records if r.fields.get("grade") and r.fields["grade"].value == 78.0][0]
        assert retake.fields["passed"].value is True
        assert retake.fields["creditsCounted"].value == 5.5

    async def test_an_ungraded_row_is_not_passed(self, database) -> None:
        """A missing grade must fail CLOSED. Mongo orders null below every
        number, so the comparison is false rather than an error -- and false is
        the safe direction: an ungraded row is not a course the student has."""
        result = await find(database, COMPLETED_COURSES)
        ungraded = [r for r in result.records if "grade" not in r.fields][0]
        assert ungraded.fields["passed"].value is False
        assert ungraded.fields["creditsCounted"].value == 0

    async def test_the_pass_mark_is_the_one_the_rest_of_the_product_states(self) -> None:
        """55, from `PASSING_GRADE_THRESHOLD` in the web client -- and told to
        the student in as many words. Not a number invented in this layer."""
        assert PASSING_GRADE == 55


class TestTheFlagIsAnOrdinaryFieldAndNotAnAfterthought:
    async def test_it_can_be_filtered_on(self, database) -> None:
        """The regression that has no symptom. Computed AFTER the fetch, this
        filter would compile against a field that does not exist yet, match
        nothing, and report an empty transcript as complete."""
        result = await find(database, COMPLETED_COURSES, predicate=passed_is(True))
        assert len(result.records) == 2
        assert {r.fields["grade"].value for r in result.records} == {95.0, 78.0}

    async def test_a_filtered_fetch_still_counts_itself_honestly(self, database) -> None:
        """Completeness is measured against the PREDICATE. If the count ran
        without the `$addFields` stage the total would be the whole collection,
        and a complete result would report itself truncated."""
        result = await find(database, COMPLETED_COURSES, predicate=passed_is(True))
        assert result.completeness.total == 2
        assert result.completeness.complete is True

    async def test_the_negative_case_is_reachable_too(self, database) -> None:
        result = await find(database, COMPLETED_COURSES, predicate=passed_is(False))
        assert result.completeness.total == 2

    async def test_a_truncated_fetch_returns_the_same_page_every_time(self, database) -> None:
        """`courseId` repeats across retakes, so sorting by the key alone is not
        a total order -- and without one, the same query returns a different
        page each run and every answer built on it moves."""
        pages = [
            [r.fields["courseId"].value for r in (await find(database, COMPLETED_COURSES, limit=3)).records]
            for _ in range(4)
        ]
        assert all(page == pages[0] for page in pages)


class TestTrackCategories:
    """`category` is what lets a planner tell a requirement from a choice."""

    def test_an_elective_heading_wins_over_a_semester_word_inside_it(self) -> None:
        """The one ordering that matters. A heading like "elective courses by
        semester" contains the semester word that otherwise means mandatory, so
        testing mandatory first types every course under it as REQUIRED --
        telling a student they must take a course they may choose."""
        engine = _StubEngine(
            {
                "track-x": {
                    "kind": "track",
                    "content": "## קורסי בחירה לפי סמסטר\n[[course-a]]\n## Semester 1\n[[course-b]]\n",
                }
            },
            {"course-a": "00000001", "course-b": "00000002"},
        )
        categories = track_categories(engine)
        assert categories[("track-x", "00000001")] == "elective"
        assert categories[("track-x", "00000002")] == "mandatory"

    def test_a_course_under_no_recognised_heading_is_left_untyped(self) -> None:
        """Absent, not guessed. An unclassified course is one the model must
        look up; a wrongly-classified one is a wrong answer that looks sound."""
        engine = _StubEngine(
            {"track-x": {"kind": "track", "content": "## Related Programs\n[[course-a]]\n"}},
            {"course-a": "00000001"},
        )
        assert track_categories(engine) == {}

    def test_a_course_listed_as_required_stays_required_if_also_listed_elsewhere(self) -> None:
        engine = _StubEngine(
            {
                "track-x": {
                    "kind": "track",
                    "content": "## Semester 1\n[[course-a]]\n## Electives\n[[course-a]]\n",
                }
            },
            {"course-a": "00000001"},
        )
        assert track_categories(engine)[("track-x", "00000001")] == "mandatory"


class TestResolvingAStudentsTrack:
    def test_an_exact_slug_is_used_as_is(self) -> None:
        assert _resolve_track("track-ee", {"track-ee": []}) == "track-ee"

    def test_a_bare_slug_finds_its_prefixed_track(self) -> None:
        """Measured: every `electrical-engineering` profile got `remaining=0`
        while `track-electrical-engineering` sat in the graph with a full course
        list. An empty curriculum reads as "nothing left to take"."""
        assert _resolve_track("electrical-engineering", {"track-electrical-engineering": []}) == (
            "track-electrical-engineering"
        )

    def test_an_unknown_track_resolves_to_nothing_rather_than_to_a_near_miss(self) -> None:
        """Declining to plan beats planning someone else's degree."""
        assert _resolve_track("physics", {"track-electrical-engineering": []}) is None


class _StubEngine:
    """The two attributes `track_categories` reads, and nothing else."""

    def __init__(self, pages: dict, slugs: dict) -> None:
        self.wiki_pages = pages
        self.slug_to_course_code = slugs


PROFILE_USER = "6a3ba4e039685de852ac3382"
DEGREE = "6a3fc102d3e414b0b8faefe3"


@pytest.fixture
async def student_database():
    """A student, their degree, and a transcript with one failed course."""
    from bson import ObjectId

    from app.db.mongo import get_database

    try:
        handle = await get_database()
        await handle.command("ping")
        client = handle.client
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"NOT VERIFIED: no database ({type(exc).__name__}). Profile lookup UNCHECKED.")

    db = client["unipilot_profile_test"]
    for name in ("student_profiles", "degree_programs", "completed_courses"):
        await db[name].delete_many({})
    await db["student_profiles"].insert_one(
        {
            "userId": ObjectId(PROFILE_USER),
            "degreeId": ObjectId(DEGREE),
            "programSlug": "track-ise",
            "catalogYear": 2025,
            "currentSemesterCode": "2026-1",
            # NO maxCreditsPerSemester: absent on every live profile checked, and
            # the seeding must omit it rather than invent one.
        }
    )
    await db["degree_programs"].insert_one({"_id": ObjectId(DEGREE), "totalCredits": 155.0})
    await db["completed_courses"].insert_many(
        [
            {"courseId": "c1", "userId": ObjectId(PROFILE_USER), "grade": 95.0, "creditsEarned": 3.5},
            {"courseId": "c2", "userId": ObjectId(PROFILE_USER), "grade": 32.0, "creditsEarned": 5.5},
            # Another student's row, to prove the sum is scoped to one person.
            {"courseId": "c3", "userId": ObjectId(), "grade": 90.0, "creditsEarned": 99.0},
        ]
    )
    yield db
    await client.drop_database("unipilot_profile_test")
    client.close()


class TestTheStudentProfileLookup:
    """One query proving the student exists and carrying their credit standing."""

    async def test_it_counts_only_passed_credits_and_only_this_student(self, student_database) -> None:
        """The failed 5.5 must not count, and neither must the other student's
        99.0. Both are the same class of error -- a sum over the wrong rows --
        and both produce a number that looks entirely plausible."""
        from app.agent_core.facts.service import _profile_of

        profile = await _profile_of(student_database, PROFILE_USER)
        assert profile["creditsCompleted"] == 3.5
        assert profile["creditsRequired"] == 155.0

    async def test_an_unknown_student_is_none_rather_than_an_empty_record(
        self, student_database
    ) -> None:
        """The failure this check exists to prevent: an unknown student has no
        transcript, so every `find` returns empty, `sum` over empty is 0, and the
        run answers "you have completed 0 credits" -- confident, grounded in a
        real fetch, and about nobody."""
        from bson import ObjectId

        from app.agent_core.facts.service import _profile_of

        assert await _profile_of(student_database, str(ObjectId())) is None

    async def test_a_malformed_id_is_refused_rather_than_raised(self, student_database) -> None:
        """A caller mistake, not a database outage. Raising here would report a
        client error as an infrastructure failure."""
        from app.agent_core.facts.service import _profile_of

        assert await _profile_of(student_database, "not-an-object-id") is None


class TestSeedingTheOpeningFacts:
    async def test_a_missing_field_is_omitted_rather_than_defaulted(self, student_database) -> None:
        """This profile has no `maxCreditsPerSemester`. Seeding a 0 would make
        every plan refuse, and seeding a guess would plan against a limit the
        student does not have -- absent lets the model `find` it or say so."""
        from app.agent_core.facts.dispatch import DispatchContext
        from app.agent_core.facts.service import _profile_of, _seed_profile_facts

        context = DispatchContext(schemas=REGISTRY_FOR_SEEDING)
        _seed_profile_facts(context, await _profile_of(student_database, PROFILE_USER))
        assert "program_slug" in context.facts
        assert "max_credits_per_semester" not in context.facts

    async def test_the_credit_standing_is_seeded_from_the_same_query(
        self, student_database
    ) -> None:
        from app.agent_core.facts.dispatch import DispatchContext
        from app.agent_core.facts.service import _profile_of, _seed_credit_standing

        context = DispatchContext(schemas=REGISTRY_FOR_SEEDING)
        _seed_credit_standing(context, await _profile_of(student_database, PROFILE_USER))
        assert context.facts["credits_completed"].value.value == 3.5
        assert context.facts["credits_needed"].value.value == 151.5


class TestATrackWithNoCurriculumAtAll:
    """`grad-direct-doctorate-track` carries 8 of the 81 profiles that have a
    track, and the graph has no page for it -- the vault covers 52 undergraduate
    tracks and no graduate ones, so the absence is correct and permanent.

    What was not correct is what the student heard. The producer skipped them, so
    `find remaining_courses where userId = X` came back with zero records marked
    COMPLETE, which is the same answer a finished degree gives. `find.py` says it
    outright: silence is the worst failure this layer can produce.

    So an unresolvable track now emits a row SAYING it is unresolvable, rather
    than no row at all. It has to be unmistakably not a course, or it trades a
    silent wrong answer for a loud one.
    """

    @staticmethod
    def _documents(rows: list[dict], contains: dict) -> list[dict]:
        from app.agent_core.facts import views

        class _Engine:
            graph = None

        # Exercise the real branch by driving `_resolve_track` the way the
        # producer does, rather than restating its logic here.
        out = []
        for row in rows:
            track = views._resolve_track(row["programSlug"], contains)
            out.append({"userId": row["userId"], "programSlug": row["programSlug"], "track": track})
        return out

    def test_an_unresolvable_track_still_resolves_to_nothing(self) -> None:
        """The precondition. `_resolve_track` is not being loosened -- a near
        miss would plan someone else's degree."""
        assert _resolve_track("grad-direct-doctorate-track", {"track-electrical-engineering": []}) is None

    async def test_the_student_gets_a_row_rather_than_silence(self, database) -> None:
        from app.agent_core.facts.views import _remaining_documents

        class _Engine:
            graph = _graph_with_contains({"track-ee": ["00940412"]})

        await database["student_profiles"].insert_one(
            {"userId": "phd-1", "programSlug": "grad-direct-doctorate-track"}
        )
        documents = await _remaining_documents(database, _Engine(), {})
        mine = [d for d in documents if d["userId"] == "phd-1"]

        assert mine, "a student whose track has no curriculum must not vanish from the view"

    async def test_the_row_cannot_be_read_as_a_course(self, database) -> None:
        """No courseNumber, no title, no credits. A row that carried them would
        be counted, summed and planned as though it were a course to take."""
        from app.agent_core.facts.views import _remaining_documents

        class _Engine:
            graph = _graph_with_contains({"track-ee": ["00940412"]})

        await database["student_profiles"].insert_one(
            {"userId": "phd-2", "programSlug": "grad-direct-doctorate-track"}
        )
        documents = await _remaining_documents(database, _Engine(), {})
        row = [d for d in documents if d["userId"] == "phd-2"][0]

        assert row.get("curriculumAvailable") is False
        assert "title" not in row
        assert "credits" not in row
        # It DOES carry a courseNumber, because `_from_documents` turns a keyless
        # row into a DataDefect and returns it before filtering -- one such row
        # would break `remaining_courses` for every student. So the value has to
        # be a course number that is unmistakably not a course.
        assert row["courseNumber"] == NO_CURRICULUM
        assert not row["courseNumber"].isdigit()

    async def test_a_resolvable_track_is_not_given_the_flag(self, database) -> None:
        """The flag marks the exception. Putting it on every row would make it
        noise the model learns to skip."""
        from app.agent_core.facts.views import _remaining_documents

        class _Engine:
            graph = _graph_with_contains({"track-ee": ["00940412"]})

        await database["student_profiles"].insert_one(
            {"userId": "ug-1", "programSlug": "track-ee"}
        )
        documents = await _remaining_documents(database, _Engine(), {})
        rows = [d for d in documents if d["userId"] == "ug-1"]

        assert rows and all("curriculumAvailable" not in row for row in rows)


def _graph_with_contains(contains: dict[str, list[str]]):
    """A networkx-shaped stub exposing just the `contains` edges the producer reads."""
    import networkx as nx

    graph = nx.DiGraph()
    for track, courses in contains.items():
        for course in courses:
            graph.add_edge(track, course, relation="contains")
    return graph


class TestTheMarkerRowDoesNotPoisonEveryoneElse:
    """`_from_documents` converts EVERY document before it filters, and returns
    the first DataDefect it makes. So a badly-shaped marker row for one student
    is not a local problem -- it takes out `remaining_courses` for the whole
    cohort. This is the test that would have caught it."""

    async def test_one_students_missing_curriculum_leaves_the_rest_readable(
        self, database
    ) -> None:
        from app.agent_core.facts.views import remaining_courses_source

        class _Engine:
            graph = _graph_with_contains({"track-ee": ["00940412", "00940413"]})

        await database["student_profiles"].delete_many({})
        await database["student_profiles"].insert_many(
            [
                {"userId": "phd-3", "programSlug": "grad-direct-doctorate-track"},
                {"userId": "ug-2", "programSlug": "track-ee"},
            ]
        )
        await database["courses"].delete_many({})
        await database["courses"].insert_many(
            [
                {"courseNumber": "00940412", "title": "A", "credits": 3.0},
                {"courseNumber": "00940413", "title": "B", "credits": 3.0},
            ]
        )

        schema = remaining_courses_source(_Engine())
        for user, expectation in (("ug-2", "courses"), ("phd-3", "the marker")):
            result = await find(
                database,
                schema,
                Comparison(Path.parse("userId"), Op.EQ, Scalar(I, user)),
                limit=100,
            )
            assert isinstance(result, Collection), f"{expectation} for {user} became {result!r}"
            assert result.records, f"{user} got an empty, complete result -- the original bug"
