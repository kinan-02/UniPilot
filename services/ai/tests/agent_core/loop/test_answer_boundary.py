"""Unit tests for the grounding backstop (resolve_final, §4.2/§9.1). No LLM."""

from __future__ import annotations

from app.agent_core.loop.answer_boundary import resolve_final
from app.agent_core.loop.working_set import Fact


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


def test_list_of_scalars_slot_renders_comma_separated():
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
