"""Unit tests for the grounding backstop (resolve_final, §4.2/§9.1) and the
readability pass that runs behind it. No real LLM."""

from __future__ import annotations

from app.agent_core.loop.answer_boundary import polish_answer, resolve_final
from app.agent_core.loop.working_set import Fact
from app.agent_core.reasoning.llm_adapter import LLMAdapterError


def _facts(**kw: object) -> dict[str, Fact]:
    return {k: Fact(v, "src", "computed", 1.0) for k, v in kw.items()}


def test_slot_filled_number_is_grounded():
    rendered, problems = resolve_final(
        "How many credits remain?",
        _facts(gap=62.5),
        "You still need {gap} credits.",
        {"gap": "gap"},
    )
    assert rendered == "You still need 62.5 credits."
    assert problems == []


def test_bare_number_in_prose_is_rejected():
    rendered, problems = resolve_final(
        "How many credits remain?",
        _facts(gap=62.5),
        "You still need 92.5 credits.",  # typed, not slotted
        {},
    )
    assert "92.5" in problems


def test_number_echoed_from_question_is_allowed():
    rendered, problems = resolve_final(
        "Will I be able to take 00960211?",
        {},
        "Yes, you can take 00960211.",
        {},
    )
    assert problems == []


def test_unresolved_slot_is_flagged():
    _, problems = resolve_final(
        "q",
        {},  # no facts -- the ref binds to nothing
        "You need {gap} credits.",
        {"gap": "gap"},
    )
    assert any(p.startswith("unresolved_slot:") for p in problems)


def test_non_scalar_record_slot_is_rejected():
    _, problems = resolve_final(
        "q",
        _facts(rec={"grade": 85}),
        "Your record is {rec}.",
        {"rec": "rec"},
    )
    # Sharpened: names the fields so the model can select the scalar it meant.
    assert any("dict with keys" in p and "grade" in p for p in problems)


def test_list_of_scalars_slot_renders_comma_separated(monkeypatch):
    """Course codes now render with their names (see the readability tests
    below), so this pins the comma-joining itself with the lookup stubbed --
    otherwise the assertion silently depends on the real catalog's contents."""
    _named(monkeypatch, {})
    rendered, problems = resolve_final(
        "Which courses have I completed?",
        _facts(codes=["00940224", "00960211", "00110001"]),
        "You completed: {codes}.",
        {"codes": "codes"},
    )
    assert rendered == "You completed: 00940224, 00960211, 00110001."
    assert problems == []  # every listed code is grounded via the slot


def test_none_valued_slot_is_rejected_not_rendered_as_none():
    _, problems = resolve_final(
        "q",
        _facts(sem=None),
        "The target semester is {sem}.",
        {"sem": "sem"},
    )
    assert any("None" in p for p in problems)


def test_list_of_records_slot_is_still_rejected():
    _, problems = resolve_final(
        "q",
        _facts(recs=[{"courseNumber": "00940224"}]),
        "Your courses: {recs}.",
        {"recs": "recs"},
    )
    assert any("list of 1 records" in p for p in problems)


def test_record_list_rejection_names_projections_the_loop_already_holds():
    """The 2026-07-18 post-fix run lost `completed_courses` here. Turn 3 had
    already run `select ... field=courseNumber` and held the 17 codes; turns 5
    and 6 then slotted the RECORD list, were told twice to "select a field to
    enumerate them", and gave up -- advice to do the thing it had done three
    turns earlier. The rejection can see the working set, so it should say which
    facts are ready to slot instead of describing the move abstractly."""
    facts = _facts(
        recs=[{"courseNumber": "00940224"}, {"courseNumber": "00940704"}],
        course_numbers=["00940224", "00940704"],
        grades=[85, 95],
    )
    _, problems = resolve_final("q", facts, "Your courses: {recs}.", {"recs": "recs"})

    slot_problem = next(p for p in problems if p.startswith("unresolved_slot:recs"))
    assert "course_numbers" in slot_problem
    assert "grades" in slot_problem


def test_record_list_rejection_does_not_name_a_mismatched_list():
    """Only projections OF this list help. A list of a different length is some
    other fact, and naming it would send the model to the wrong data."""
    facts = _facts(
        recs=[{"courseNumber": "00940224"}, {"courseNumber": "00940704"}],
        unrelated=["a", "b", "c"],
    )
    _, problems = resolve_final("q", facts, "Your courses: {recs}.", {"recs": "recs"})

    slot_problem = next(p for p in problems if p.startswith("unresolved_slot:recs"))
    assert "unrelated" not in slot_problem
    assert "select a field" in slot_problem  # falls back to the generic recovery


def test_record_list_rejection_keeps_generic_advice_when_nothing_is_ready():
    facts = _facts(recs=[{"courseNumber": "00940224"}])
    _, problems = resolve_final("q", facts, "Your courses: {recs}.", {"recs": "recs"})

    assert any("select a field to enumerate them" in p for p in problems)


# -- polish pass ---------------------------------------------------------------
#
# A readability pass over an answer that already passed grounding AND the
# completeness gate. It re-emits the SAME {prose, fact_refs} shape and is
# re-validated through resolve_final, so it cannot type a number; and it must
# keep every fact the accepted draft referenced, so it cannot drop one to read
# more smoothly. Anything else about it -> discard, ship the original. A free
# rewrite here would be a hidden repair loop: able to make a hedged, correct
# answer sound confident, with nothing downstream to catch it.


class _PolishAdapter:
    def __init__(self, response: object) -> None:
        self._response = response
        self.calls = 0

    async def complete_json(self, **_kw: object) -> object:
        self.calls += 1
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


async def test_polish_replaces_the_draft_when_it_stays_grounded(monkeypatch):
    _named(monkeypatch, {"00940224": "Data Structures"})
    adapter = _PolishAdapter({"prose": "You are eligible for {c}.", "fact_refs": {"c": "course"}})
    out = await polish_answer(
        adapter, "Am I eligible?", _facts(course="00940224"),
        "Eligibility: yes.", {"x": "course"}, temperature=0.0, reasoning_effort="low",
    )
    assert out == "You are eligible for Data Structures (00940224)."


async def test_polish_that_invents_a_number_is_discarded(monkeypatch):
    """The whole point: an ungrounded numeral in the rewrite must not reach the
    user, and must not be repaired -- the accepted draft is already correct."""
    _named(monkeypatch, {})
    adapter = _PolishAdapter({"prose": "You need 42 more credits.", "fact_refs": {}})
    out = await polish_answer(
        adapter, "q", _facts(course="00940224"),
        "Eligibility: yes.", {"x": "course"}, temperature=0.0, reasoning_effort="low",
    )
    assert out is None


async def test_polish_that_drops_a_fact_is_discarded(monkeypatch):
    """Dropping a referenced fact makes the answer read better and say less --
    a deterministic set check, so no second completeness call is needed."""
    _named(monkeypatch, {})
    adapter = _PolishAdapter({"prose": "You are eligible.", "fact_refs": {}})
    out = await polish_answer(
        adapter, "q", _facts(course="00940224", grade=85),
        "You got 85 in 00940224.", {"a": "course", "b": "grade"},
        temperature=0.0, reasoning_effort="low",
    )
    assert out is None


async def test_polish_may_add_a_fact_it_did_not_have_to_drop(monkeypatch):
    """Superset, not equality -- mentioning one more grounded fact is fine."""
    _named(monkeypatch, {"00940224": "Data Structures"})
    adapter = _PolishAdapter(
        {"prose": "You scored {g} in {c}.", "fact_refs": {"g": "grade", "c": "course"}}
    )
    out = await polish_answer(
        adapter, "q", _facts(course="00940224", grade=85),
        "00940224: 85.", {"a": "course"}, temperature=0.0, reasoning_effort="low",
    )
    assert out == "You scored 85 in Data Structures (00940224)."


async def test_polish_cannot_strip_the_certainty_hedge(monkeypatch):
    """Live-observed regression, 2026-07-18 run 3. "…3 recorded semesters.
    On certainty: 3 -- predicted from recent offering history (not a guaranteed
    future schedule)." came back as "…3 recorded semesters. The spring pattern is
    marked reliable." -- calibrated uncertainty traded for reassurance.

    Re-deriving the note from the rewrite's own slots was the mistake: the
    rewrite controlled the derivation. The note is now lifted off, withheld from
    the model, and re-attached verbatim."""
    _named(monkeypatch, {})
    facts = {"count": Fact(3, "src", "predicted_pattern", 0.95)}
    draft, _ = resolve_final("q", facts, "Offered in {c} semesters.", {"c": "count"})
    assert "On certainty" in draft  # precondition

    adapter = _PolishAdapter(
        {"prose": "It ran {c} times. The pattern is reliable.", "fact_refs": {"c": "count"}}
    )
    out = await polish_answer(
        adapter, "q", facts, draft, {"c": "count"}, temperature=0.0, reasoning_effort="low"
    )
    assert out is not None
    assert "On certainty: 3 -- predicted from recent offering history" in out


async def test_polish_never_sees_the_hedge_it_must_not_touch(monkeypatch):
    _named(monkeypatch, {})
    facts = {"count": Fact(3, "src", "predicted_pattern", 0.95)}
    draft, _ = resolve_final("q", facts, "Offered in {c} semesters.", {"c": "count"})
    seen: dict[str, str] = {}

    class _Capture(_PolishAdapter):
        async def complete_json(self, **kw: object) -> object:
            seen["user"] = str(kw.get("user_prompt"))
            return await super().complete_json(**kw)

    adapter = _Capture({"prose": "Ran {c} times.", "fact_refs": {"c": "count"}})
    await polish_answer(
        adapter, "q", facts, draft, {"c": "count"}, temperature=0.0, reasoning_effort="low"
    )
    assert "On certainty" not in seen["user"]


async def test_a_ref_declared_but_never_written_does_not_count_as_kept(monkeypatch):
    """The other half of the same live failure: the rewrite declared the fact in
    fact_refs, wrote no {slot} for it, and passed a naive set check -- shipping
    "It has been offered in spring…" with the course silently gone."""
    _named(monkeypatch, {})
    adapter = _PolishAdapter(
        {"prose": "It has been offered in spring.", "fact_refs": {"c": "course"}}
    )
    out = await polish_answer(
        adapter, "q", _facts(course="00960211"),
        "Course 00960211 is offered in spring.", {"c": "course"},
        temperature=0.0, reasoning_effort="low",
    )
    assert out is None


async def test_polish_cannot_replace_a_named_course_with_this_course(monkeypatch):
    """Live-observed twice. Run 4: "Course 00960211 is not offered in summer"
    came back as "This course is marked never for the summer semester" -- the
    subject gone. A code reaching the draft from the QUESTION is never in
    fact_refs, so the ref check cannot see it; codes are compared on the text."""
    _named(monkeypatch, {})
    adapter = _PolishAdapter({"prose": "This course is not offered in summer.", "fact_refs": {}})
    out = await polish_answer(
        adapter, "Is 00960211 offered in summer?", {},
        "Course 00960211 is not offered in summer.", {},
        temperature=0.0, reasoning_effort="low",
    )
    assert out is None


async def test_polish_cannot_leak_internal_vocabulary(monkeypatch):
    """Run 4 shipped "based on predicted_pattern with confidence 0.95" to a
    student -- with "no internal vocabulary" already in the prompt. A rule the
    model can simply not follow is not a guarantee."""
    _named(monkeypatch, {})
    for leak in (
        "Marked never, based on predicted_pattern with confidence 0.95.",
        "This is from the official_record.",
    ):
        adapter = _PolishAdapter({"prose": leak, "fact_refs": {}})
        out = await polish_answer(
            adapter, "q", {}, "It is not offered.", {}, temperature=0.0, reasoning_effort="low"
        )
        assert out is None, leak


async def test_polish_is_told_which_language_to_write_in(monkeypatch):
    """A rewrite is exactly where a language switch creeps in: the facts are full
    of Hebrew course names even when the student wrote English. The draft's own
    language is not stated anywhere in the polish input, so the directive has to
    be."""
    _named(monkeypatch, {})
    seen: dict[str, str] = {}

    class _Capture(_PolishAdapter):
        async def complete_json(self, **kw: object) -> object:
            seen["user"] = str(kw.get("user_prompt"))
            return await super().complete_json(**kw)

    adapter = _Capture({"prose": "ok {c}", "fact_refs": {"c": "course"}})
    await polish_answer(
        adapter, "Am I eligible?", _facts(course="00940224"),
        "draft", {"x": "course"}, temperature=0.0, reasoning_effort="low",
    )
    assert "Write the answer in English" in seen["user"]

    await polish_answer(
        adapter, "האם אני זכאי?", _facts(course="00940224"),
        "draft", {"x": "course"}, temperature=0.0, reasoning_effort="low",
    )
    assert "Write the answer in Hebrew" in seen["user"]


async def test_polish_failure_never_breaks_the_answer(monkeypatch):
    """One attempt, no retry. An adapter error or empty prose falls back."""
    _named(monkeypatch, {})
    for response in (LLMAdapterError("llm_call_failed"), {"prose": "", "fact_refs": {}}, {}):
        adapter = _PolishAdapter(response)
        out = await polish_answer(
            adapter, "q", _facts(course="00940224"),
            "Eligibility: yes.", {"x": "course"}, temperature=0.0, reasoning_effort="low",
        )
        assert out is None
        assert adapter.calls == 1


# -- scalar rendering ----------------------------------------------------------


def test_empty_list_renders_as_none_not_as_nothing():
    """The live eval shipped "Missing prerequisites are ." -- an empty list
    joined to the empty string, leaving a sentence with a hole in it."""
    rendered, problems = resolve_final(
        "q", _facts(missing=[]), "Missing prerequisites are {missing}.", {"missing": "missing"}
    )
    assert rendered == "Missing prerequisites are none."
    assert problems == []


def test_booleans_render_as_words_not_python_literals():
    """"For course 00960211, the student is True." -- `str(True)` reaching prose."""
    yes, _ = resolve_final("q", _facts(ok=True), "Eligible: {ok}.", {"ok": "ok"})
    no, _ = resolve_final("q", _facts(ok=False), "Eligible: {ok}.", {"ok": "ok"})
    assert yes == "Eligible: yes."
    assert no == "Eligible: no."


def test_booleans_inside_a_list_render_as_words_too():
    rendered, _ = resolve_final("q", _facts(flags=[True, False]), "Flags: {flags}.", {"flags": "flags"})
    assert rendered == "Flags: yes, no."


# -- course-code readability --------------------------------------------------
#
# 7 of 10 answers in the 2026-07-18 run shipped bare 8-digit codes ("The courses
# on your record with a final grade above 90 are: 00940704, 00940219, 03240033").
# Names are looked up in code, never composed: the backstop checks numerals only,
# so a typed name is unvalidated, and a convincing fake name on a real code is
# worse than no name.


def _named(monkeypatch, mapping: dict[str, str]) -> None:
    import app.agent_core.loop.answer_boundary as module

    monkeypatch.setattr(module, "course_display_name", lambda code: mapping.get(code))


def test_slotted_course_code_renders_with_its_name(monkeypatch):
    _named(monkeypatch, {"00940224": "Data Structures and Algorithms"})
    rendered, problems = resolve_final(
        "q", _facts(course="00940224"), "You completed {course}.", {"course": "course"}
    )
    assert rendered == "You completed Data Structures and Algorithms (00940224)."
    assert problems == []


def test_every_code_in_a_slotted_list_is_named(monkeypatch):
    _named(monkeypatch, {"00940704": "Intro to Data Engineering", "00940219": "Software Engineering"})
    rendered, problems = resolve_final(
        "q", _facts(codes=["00940704", "00940219"]), "Your top courses: {codes}.", {"codes": "codes"}
    )
    assert rendered == "Your top courses: Intro to Data Engineering (00940704), Software Engineering (00940219)."
    assert problems == []


def test_a_name_containing_digits_does_not_read_as_an_ungrounded_number(monkeypatch):
    """The trap. "Algebra 1M2" puts 1 and 2 into the prose, and the backstop
    flags any numeral not traceable to a slotted fact -- so enrichment applied
    after the value was recorded would reject the loop's own correct answer."""
    _named(monkeypatch, {"01040065": "Algebra 1M2"})
    rendered, problems = resolve_final(
        "q", _facts(course="01040065"), "You took {course}.", {"course": "course"}
    )
    assert rendered == "You took Algebra 1M2 (01040065)."
    assert problems == []


def test_unknown_code_degrades_to_the_bare_code(monkeypatch):
    """49 course pages carry no title; a missing name costs readability, never
    correctness."""
    _named(monkeypatch, {})
    rendered, problems = resolve_final(
        "q", _facts(course="00940224"), "You completed {course}.", {"course": "course"}
    )
    assert rendered == "You completed 00940224."
    assert problems == []


def test_non_course_values_are_never_renamed(monkeypatch):
    """A grade and a credit total must not be looked up as course codes."""
    _named(monkeypatch, {"00940224": "Data Structures and Algorithms"})
    rendered, _ = resolve_final(
        "q", _facts(grade=85, credits=92.5), "Grade {grade}, {credits} left.", {"grade": "grade", "credits": "credits"}
    )
    assert rendered == "Grade 85, 92.5 left."


def test_predicted_fact_appends_a_certainty_note():
    # §4.2: a non-authoritative basis renders hedged -- the value still slots, but
    # a trailing note names why it is not a firm record.
    facts = {"season": Fact("Spring", "extract(...)", "predicted_pattern", 0.7)}
    rendered, problems = resolve_final(
        "When is 00940224 offered?", facts, "It is usually offered in {season}.", {"season": "season"}
    )
    assert problems == []
    assert "Spring" in rendered
    assert "On certainty:" in rendered
    assert "predicted from recent offering history" in rendered


def test_official_fact_renders_flat_without_a_certainty_note():
    facts = {"grade": Fact(85, "select(...)", "official_record", 1.0)}
    rendered, problems = resolve_final(
        "What did I get in 00940224?", facts, "You scored {grade}.", {"grade": "grade"}
    )
    assert rendered == "You scored 85."
    assert "On certainty" not in rendered


def test_ordered_list_markers_are_not_flagged_as_ungrounded():
    # The "1." / "2." are Markdown list formatting, not factual claims.
    _, problems = resolve_final(
        "What are my options?",
        {},
        "Your options:\n1. Retake the course next winter\n2. Petition the committee",
        {},
    )
    assert problems == []


def test_autorepair_slot_bound_to_a_question_code_renders_directly():
    # #2 auto-repair: the model bound {course} to the literal "00960211" (a question
    # code), not a fact key. It is grounded-by-question, so render it -- don't reject
    # into a wander (the action_boundary failure mode).
    rendered, problems = resolve_final(
        "Please register me for course 00960211.",
        {},
        "I can't register you, but course {course} is the one you asked about.",
        {"course": "00960211"},
    )
    assert problems == []
    assert "00960211" in rendered and "{course}" not in rendered


def test_autorepair_slot_name_matching_a_record_field_auto_selects_it():
    # #2 auto-repair: {grade} bound to a whole record, but the slot NAME names a
    # scalar field -- read it instead of rejecting the record->scalar mismatch.
    facts = {"rec": Fact({"courseNumber": "00940224", "grade": 85}, "select(...)", "official_record", 1.0)}
    rendered, problems = resolve_final(
        "What did I get in 00940224?", facts, "You scored {grade}.", {"grade": "rec"}
    )
    assert problems == []
    assert rendered == "You scored 85."


def test_autorepair_does_not_fire_when_slot_name_matches_no_field():
    facts = {"rec": Fact({"courseNumber": "00940224", "grade": 85}, "s", "official_record", 1.0)}
    _, problems = resolve_final("q", facts, "Value: {foo}.", {"foo": "rec"})
    assert any("dict with keys" in p for p in problems)  # no 'foo' field -> still rejected


def test_a_null_inside_a_list_never_renders_the_python_literal():
    """The 2026-07-19 live run shipped "..., ספרי יסוד (03260008), None, Optimization
    Methods ..." to a student. Seven of that user's 53 completed courses reference a
    catalog row with no courseNumber, so the join genuinely had nothing to show --
    but "None" reads as a software fault, which is exactly what it was."""
    facts = {
        "courses": Fact(
            value=["00940224", None, "00960211"],
            source="get_entity",
            basis="official_record",
            confidence=0.95,
        )
    }

    rendered, problems = resolve_final("what did i complete?", facts, "You completed {courses}.", {"courses": "courses"})

    assert "None" not in rendered
    assert "(not recorded)" in rendered
    assert problems == []


def test_a_null_element_is_named_rather_than_dropped():
    """Dropping it would render two courses for a record that holds three -- a
    visible blemish traded for a wrong answer."""
    facts = {
        "courses": Fact(value=[None, None, "00940224"], source="get_entity", basis="official_record", confidence=0.95)
    }

    rendered, _ = resolve_final("q", facts, "{courses}", {"courses": "courses"})

    assert rendered.count("(not recorded)") == 2


def test_a_wholly_null_fact_is_still_rejected_not_rendered():
    """The element-level placeholder must not weaken the fact-level guard: a slot
    bound to a fact with no value at all is still a grounding failure."""
    facts = {"sem": Fact(value=None, source="get_entity", basis="official_record", confidence=0.9)}

    _, problems = resolve_final("q", facts, "Target semester is {sem}.", {"sem": "sem"})

    assert any("None" in problem for problem in problems)


# -- a paragraph is not a value ------------------------------------------------

_APPEAL_BLOB = (
    'The source states that a grade appeal is handled under "5.4 Grade Appeal (תקנה 2.3.3)". '
    "It gives a deadline of within 4 days from when the exam copy is available, and says the "
    "lecturer must respond within 1 week, no later than 1 week before Moed B. The result may "
    "raise, lower, or leave the grade unchanged, and the entire exam may be re-graded, not just "
    "the appealed question. However, this excerpt does not state the allowed grounds for "
    "appealing a course grade."
)


def _interpretation(value: str) -> dict[str, Fact]:
    return {"appeal": Fact(value=value, source="interpret_text", basis="llm_interpretation", confidence=0.84)}


def test_one_quoted_paragraph_is_allowed_even_mid_sentence():
    """Clumsy and TRUE beats budget_exhausted.

    Policing POSITION was wrong twice: the model cannot type the numbers itself
    (the numeral backstop) and quoting the paragraph was its only other move, so
    rejecting that left it with no legal action -- it emitted empty turns and the
    request died on the exhaustion floor with the correct answer already in hand.
    """
    _, problems = resolve_final(
        "מהן זכויותיי בנוגע לערעור על ציון?",
        _interpretation(_APPEAL_BLOB),
        "ניתן להגיש ערעור בתוך {appeal} מרגע שעתק הבחינה זמין.",
        {"appeal": "appeal"},
    )

    assert problems == [], problems


def test_a_paragraph_quoted_twice_is_rejected():
    """One quote is clumsy; the same paragraph filling gap after gap is the
    unreadable thing, and that is a COUNT, not a position."""
    _, problems = resolve_final(
        "q",
        _interpretation(_APPEAL_BLOB),
        "ניתן להגיש ערעור בתוך {appeal}. תוצאת הערעור: {appeal}.",
        {"appeal": "appeal"},
    )

    message = " ".join(problems)
    assert "fills 2 slots but is allowed 1" in message


def test_a_short_value_is_still_slottable():
    """The guard must not reject the values slots exist for."""
    for value in ("4", "12.5", "00960211", "2025-1", "Data Structures and Algorithms (00940224)"):
        facts = {"v": Fact(value=value, source="s", basis="official_record", confidence=0.95)}
        rendered, problems = resolve_final("q", facts, "The answer is {v}.", {"v": "v"})
        assert problems == [], (value, problems)
        assert value in rendered


def test_a_long_course_name_is_not_mistaken_for_prose():
    """The longest legitimate slot value seen live: an enriched course name."""
    value = "Introduction to Economics or Principles of Economics (00940591)"
    facts = {"course": Fact(value=value, source="s", basis="official_record", confidence=0.95)}

    _, problems = resolve_final("q", facts, "You took {course}.", {"course": "course"})

    assert problems == []


# -- one fact cannot be seven different values ---------------------------------


def test_one_fact_filling_many_slots_is_rejected():
    """Each substitution looked fine on its own; only the count gave it away. The
    live answer bound ONE fact to seven slots of a Hebrew template."""
    facts = {"v": Fact(value="4", source="s", basis="official_record", confidence=0.95)}
    prose = " ".join("{v}" for _ in range(7))

    _, problems = resolve_final("q", facts, prose, {"v": "v"})

    assert any("fills 7 slots" in problem for problem in problems), problems


def test_repeating_one_fact_a_couple_of_times_is_allowed():
    """"Your GPA is {gpa}, and {gpa} clears the bar" is natural writing."""
    facts = {"gpa": Fact(value="88", source="s", basis="official_record", confidence=0.95)}

    _, problems = resolve_final("q", facts, "Your GPA is {gpa}, and {gpa} clears the bar.", {"gpa": "gpa"})

    assert problems == []


def test_a_paragraph_answer_standing_on_its_own_is_allowed():
    """A policy answer legitimately IS a paragraph. Rejecting that too made the
    loop exhaust its budget failing to compose and ship a raw fact dump instead
    -- the guard has to catch the embedded case without blocking this one."""
    facts = _interpretation(_APPEAL_BLOB)

    for prose in ("{appeal}", "Here is what the regulations say: {appeal}", "{appeal}."):
        _, problems = resolve_final("q", facts, prose, {"appeal": "appeal"})
        assert problems == [], (prose, problems)


def test_the_seven_slot_disaster_is_still_rejected():
    """The answer that started this: ONE interpretation paragraph in seven gaps of
    a Hebrew sentence."""
    prose = " ".join("{appeal}" for _ in range(7))

    _, problems = resolve_final("q", _interpretation(_APPEAL_BLOB), prose, {"appeal": "appeal"})

    assert any("fills 7 slots" in problem for problem in problems), problems
