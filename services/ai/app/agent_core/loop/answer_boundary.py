"""The Answer Boundary -- the single verification (AGENT_ARCHITECTURE_V2.md §9).

Replaces V1's entire verification network (Planner Council, critics, Specialist
Router re-checks, per-step success-checks, Monitor). Runs once, at the end:

1. Grounding check (`resolve_final`) -- CODE, no LLM, always. Slot-fill the prose
   from fact refs, then require every numeral in the rendered prose to trace to a
   slotted fact (or to the student's own question). The model literally cannot
   write `92.5`; it writes `{gap}` bound to a computed ref.
2. Completeness check (`completeness_gate`) -- <=1 LLM call. Does the answer
   address every sub-ask? The one verification LLM call V2 permits, run once over
   the finished answer, not per step. Fails OPEN.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Any

from app.agent_core.loop.course_names import course_codes_in, course_display_name
from app.agent_core.response_language import response_language_directive
from app.agent_core.loop.working_set import AUTHORITATIVE_BASES, Fact, summarize_value
from app.agent_core.reasoning.llm_adapter import ChatLLMAdapter, LLMAdapterError

_NUM = re.compile(r"\d+(?:\.\d+)?")
_SLOT = re.compile(r"\{(\w+)\}")
# Markdown ordered-list markers ("1. ", "2) ") at line start are FORMATTING, not
# factual claims -- exempt them from the numeral backstop so a legitimately
# enumerated answer isn't rejected for its own bullet numbers. Anything mid-
# sentence stays checked, so a fabricated "92.5" is still caught.
_LIST_MARKER = re.compile(r"(?m)^\s*\d+[.)]\s")
_GATE_TIMEOUT_S = 60.0

# How a qualified (non-authoritative) fact's value is hedged in the answer's
# certainty note (§4.2) -- keyed by the fact's basis. An official record needs no
# entry (it renders flat); everything else names why the value is not firm.
_BASIS_QUALIFIER = {
    "predicted_pattern": "predicted from recent offering history (not a guaranteed future schedule)",
    "llm_interpretation": "interpreted from catalog/wiki text (confirm against the official source)",
    "wiki_derived": "drawn from the program catalog text",
    "hypothetical_simulation": "from the hypothetical you described (a simulation, not your current record)",
    "simulated": "from a simulated what-if (not your current record)",
    "unknown": "from a source of uncertain authority (verify before relying on it)",
}


_CERTAINTY_MARKER = "\n\nOn certainty: "

# Guards on the readability pass, each one a failure it was watched committing.
# The rewrite is unconstrained prose, so every property we need from it has to be
# checked deterministically here -- a prompt rule it can simply not follow is not
# a guarantee, and each of these was in the prompt when it was broken.
_INTERNAL_VOCABULARY = (
    "predicted_pattern",
    "official_record",
    "wiki_derived",
    "confidence 0",
    "fact_refs",
    "basis:",
)


def _course_codes(text: str) -> set[str]:
    return course_codes_in(text)


def _split_certainty_note(text: str) -> tuple[str, str]:
    """`(body, note)` -- the note including its leading separator, or `""`.

    The hedge is appended structurally, so it can be lifted off and put back
    verbatim. That is what makes it survivable across a rewrite.
    """
    head, marker, tail = text.partition(_CERTAINTY_MARKER)
    return (head, marker + tail) if marker else (text, "")


def _certainty_note(qualified: list[tuple[str, str]]) -> str:
    """A single trailing hedge sentence naming which slotted values are not firm
    records and why (§4.2). Empty when every slotted fact is authoritative -- an
    all-official answer renders flat, a prediction/interpretation renders hedged."""
    by_basis: dict[str, list[str]] = {}
    for value, basis in qualified:
        seen = by_basis.setdefault(basis, [])
        if value not in seen:
            seen.append(value)
    notes = [
        f"{', '.join(values)} -- {_BASIS_QUALIFIER.get(basis, _BASIS_QUALIFIER['unknown'])}"
        for basis, values in by_basis.items()
    ]
    return _CERTAINTY_MARKER + "; ".join(notes) + "." if notes else ""

_COMPLETENESS_SYSTEM = """You verify whether a DRAFT answer addresses every required sub-question.
Output ONLY JSON: {"unaddressed": ["<verbatim sub-ask>", ...]} -- list each sub-ask the
draft does NOT substantively address; empty list if all are addressed.

A sub-ask is "addressed" only if the draft states the relevant fact. "I could not determine
it" counts as addressed ONLY for genuinely external/unknowable facts -- NEVER for a sub-ask
about the student's OWN record (their status/grade on a course, their completed courses),
because that data is always in the record and must be looked up. For a status sub-ask, the
draft must actually REFLECT the status (e.g. that the course is already completed, with the
grade) -- merely NAMING the course, or claiming it could not be determined, does NOT count.

IMPORTANT distinction -- reporting the ACTUAL recorded status IS addressing the sub-ask, even
when that status is "already completed in an earlier semester (state the grade and that
semester) and therefore NOT currently in progress." A course passed in a prior semester
legitimately has no current-semester attempt; a draft that gives the real grade and semester
and notes there is no current attempt HAS addressed the status -- and correctly surfaces a
false "failing it this semester" premise, which is exactly what the student needs. Reject ONLY
a draft that names NO concrete status or grade at all for the course (a bare "I could not
determine it"). A stated grade like "85 in 2025-1" is an addressed status, not a cop-out."""


# A slot takes a VALUE: a number, a code, a date, a short phrase like an enriched
# course name ("Introduction to Economics or Principles of Economics (00940591)",
# 63 chars). Anything appreciably longer, or built of whole sentences, is prose
# that belongs in the model's own writing rather than inside a slot.
_MAX_SLOT_CHARS = 120
_SENTENCE_BREAK = re.compile(r"[.!?]\s+\S")
# Length floor for the sentence test, so a name carrying a full stop ("Intro to
# C.S. M") is not mistaken for prose.
_PROSE_SENTENCE_FLOOR = 40
# How many slots one fact may fill. Repeating a value is occasionally natural
# ("your GPA is {gpa}, and {gpa} clears the bar"); seven times is a template
# being padded.
_MAX_SLOT_REPEATS = 3
# A prose-valued fact gets exactly one. See the repeat check for why position
# turned out to be the wrong thing to police.
_MAX_PROSE_SLOT_REPEATS = 1


def _is_prose(text: str) -> bool:
    """Whether a string is written-out prose rather than a slottable value."""
    stripped = text.strip()
    if len(stripped) > _MAX_SLOT_CHARS:
        return True
    return len(stripped) > _PROSE_SENTENCE_FLOOR and bool(_SENTENCE_BREAK.search(stripped))


def resolve_final(
    question: str, facts: dict[str, Fact], prose: str, fact_refs: dict[str, Any]
) -> tuple[str, list[str]]:
    """Slot-fill the prose from fact refs, then run the deterministic grounding
    backstop. Returns (rendered_prose, problems): any numeral in the final prose
    that traces to no slotted fact and did not come from the student's question,
    plus any unresolved or non-scalar slot.

    §4.2: every slot must bind to a fact whose value is a scalar. A slot bound to
    no fact (a compute that never produced its fact) or to a whole record/list is
    a grounding failure -- flagged, so the answer is rejected and the model must
    `select` the specific field or fix the ref.
    """
    slotted_values: list[str] = []
    unresolved: list[str] = []
    filled_refs: list[str] = []  # one entry per slot actually filled, for the repeat guard
    qualified: list[tuple[str, str]] = []  # (rendered_value, basis) for the certainty note

    def _readable(value: str) -> str:
        """`00940224` -> `Data Structures and Algorithms (00940224)`.

        Applied BEFORE the value is recorded, which is what keeps it safe: the
        recorded string feeds `allowed`, so digits inside a name ("Algebra 1M2")
        are grounded like any other slotted numeral. Enriching after recording
        would make the loop reject its own correct answer.
        """
        name = course_display_name(value)
        return f"{name} ({value})" if name else value

    def _render_scalar(value: Any) -> str:
        """One fact value as answer prose.

        `str()` alone leaked Python literals into student-facing text -- the live
        eval shipped "the student is True". Booleans must be checked before
        anything numeric, since `isinstance(True, int)` is true.
        """
        if value is None:
            # A null INSIDE a list. The fact-level guard in `_sub` catches a fact
            # that is wholly None; this catches one null element among many, which
            # the 2026-07-19 live run rendered as "..., ספרי יסוד (03260008), None,
            # Optimization Methods...". Seven of that student's 53 completed
            # courses reference a catalog row carrying no courseNumber (a
            # transcript import that never matched the catalog), so the join
            # legitimately has nothing to show.
            #
            # Named rather than dropped on purpose: omitting the element would
            # silently render 46 courses for a record that holds 53, turning a
            # visible blemish into a wrong answer.
            return "(not recorded)"
        if isinstance(value, bool):
            return "yes" if value else "no"
        return _readable(str(value))

    def _record_scalar(rendered_value: str, ref: str) -> None:
        slotted_values.append(rendered_value)
        filled_refs.append(ref)
        basis = facts[ref].basis
        if basis not in AUTHORITATIVE_BASES:
            qualified.append((rendered_value, basis))

    question_numerals = set(_NUM.findall(question))

    def _sub(match: re.Match) -> str:
        slot = match.group(1)
        ref = fact_refs.get(slot)
        if ref in facts:
            value = facts[ref].value
            # A None-valued fact must never render the literal "None" into an
            # answer (a live eval shipped "target semester None"). Treat it as
            # unresolved so the draft is rejected and the model drops the slot or
            # fills it with a real value.
            if value is None:
                unresolved.append(f"{slot}->None (fact has no value; drop this slot)")
                return match.group(0)
            # A list of scalars renders comma-separated -- this is how a "list my
            # courses" answer slots an enumerated fact (e.g. select(field=...) over
            # the completed-courses list). Still grounded: every element traces to
            # the fact.
            if isinstance(value, list) and all(not isinstance(item, (dict, list)) for item in value):
                # An empty list is a real, grounded answer ("no missing
                # prerequisites") -- joined bare it left "Missing prerequisites
                # are ." with a hole where the answer should be.
                rendered_value = ", ".join(_render_scalar(item) for item in value) if value else "none"
                _record_scalar(rendered_value, ref)
                return rendered_value
            # A dict or a list of records is not a single value. Reject with the
            # concrete recovery (name the fields) so the model can `select` the
            # scalar it meant instead of shipping "{...}" -- a live eval bound a
            # whole record to a scalar slot and had no actionable way back.
            if isinstance(value, dict):
                # Auto-repair (#2): if the slot NAME matches exactly one scalar field
                # of the record, read it -- the model's intent is unambiguous. Turns a
                # record->scalar rejection wander into a direct, grounded fill.
                field_value = value.get(slot)
                if field_value is not None and not isinstance(field_value, (dict, list)):
                    rendered_value = _render_scalar(field_value)
                    _record_scalar(rendered_value, ref)
                    return rendered_value
                unresolved.append(
                    f"{slot}->dict with keys {sorted(value.keys())} (not a single value; select one field of it)"
                )
                return match.group(0)
            if isinstance(value, list):
                # Detect-and-correct (§19 #1): the loop has usually ALREADY made the
                # projection this rejection is about to describe. `completed_courses`
                # died exactly here -- it held the 17 selected course numbers and was
                # told twice to "select a field to enumerate them", then gave up. Name
                # the slottable facts covering the same items instead of restating the
                # move abstractly. Same-length is what makes a fact a projection OF
                # this list rather than some unrelated list.
                ready = [
                    key
                    for key, candidate in facts.items()
                    if key != ref
                    and isinstance(candidate.value, list)
                    and len(candidate.value) == len(value)
                    and all(not isinstance(item, (dict, list)) for item in candidate.value)
                ]
                # Named, never auto-substituted: with codes, grades and semesters all
                # equally valid projections, picking one would be guessing the intent.
                recovery = (
                    f"you ALREADY hold {sorted(ready)} covering the same {len(value)} items -- "
                    "slot one of those"
                    if ready
                    else "select a field to enumerate them, or add a where to pick one"
                )
                unresolved.append(f"{slot}->list of {len(value)} records ({recovery})")
                return match.group(0)
            # A PARAGRAPH IS NOT A VALUE. `str` satisfies "the slot must bind to a
            # scalar" -- that check rejects dicts and lists, and prose is neither --
            # so a 400-character interpretation blob slotted cleanly, and every
            # numeral inside it counted as grounded because the blob itself was the
            # slotted fact. Both invariants held; the answer was unreadable.
            #
            # 2026-07-19, live: an `interpret_text` summary went into SEVEN slots of
            # a Hebrew sentence, giving "ניתן להגיש ערעור בתוך The source states
            # that a grade appeal is handled under... מרגע שעתק הבחינה זמין" where
            # "4 ימים" belonged. Reject with the two ways out the model actually
            # has: pull the value out, or stop trying to slot it.
            # Prose in a slot is judged by REPETITION, not by position -- see the
            # repeat check after the substitution pass. Two attempts to police
            # position both misfired: rejecting every prose slot, then rejecting
            # only embedded ones, each left the model with no legal move (it
            # cannot type the numbers itself -- the numeral backstop -- and
            # quoting the paragraph was the only other option), so it emitted
            # empty turns and the request died on the exhaustion floor with the
            # correct answer sitting in `policy_answer` the whole time.
            #
            # One quoted paragraph is clumsy and TRUE. Seven copies of one is the
            # unreadable thing, and that is a count, not a position.
            rendered_value = _render_scalar(value)
            _record_scalar(rendered_value, ref)
            return rendered_value
        # Auto-repair (#2): the model sometimes binds a slot straight to a literal
        # code/number from the QUESTION instead of a fact key (fact_refs
        # {"course": "00960211"}). If that literal is a numeral in the question it is
        # grounded-by-question -- render it, rather than rejecting into a wander (the
        # action_boundary failure mode).
        if isinstance(ref, str) and ref in question_numerals:
            # Named too: "register me for 00960211" should come back as the
            # course, not the digits the student pasted in.
            return _readable(ref)
        unresolved.append(f"{slot}->{ref}")
        return match.group(0)

    rendered = _SLOT.sub(_sub, prose)
    # One fact answering many slots is a tell in itself: the model is padding a
    # template it cannot actually fill. The 2026-07-19 grade-appeal answer bound
    # ONE fact to seven slots, and each individual substitution looked fine --
    # only the count gave it away.
    for ref, uses in Counter(filled_refs).items():
        # A paragraph gets ONE slot. Quoting it once is clumsy and true; quoting
        # it in every gap of a sentence is what made the live answer unreadable,
        # and it is far likelier to be prose that gets abused this way than a
        # number, which is why the allowance differs.
        limit = _MAX_PROSE_SLOT_REPEATS if _is_prose(str(facts[ref].value)) else _MAX_SLOT_REPEATS
        if uses > limit:
            unresolved.append(
                f"{ref} fills {uses} slots but is allowed {limit}. One fact cannot be that many "
                "different values -- slot the distinct facts you actually hold, or state this one "
                "once and write the rest of the sentence in your own words."
            )
    allowed: set[str] = set()
    for slotted in slotted_values:
        allowed.update(_NUM.findall(slotted))
    allowed.update(_NUM.findall(question))  # echoing a code from the question is fine
    # Check numerals against the prose with ordered-list markers stripped, so a
    # numbered list's own bullet numbers don't read as ungrounded claims.
    check_target = _LIST_MARKER.sub("", rendered)
    problems = [tok for tok in _NUM.findall(check_target) if tok not in allowed]
    problems += [f"unresolved_slot:{u}" for u in unresolved]
    # Only annotate an answer we will actually accept; a rejected draft is
    # re-composed, so its certainty note would be discarded anyway.
    if not problems:
        rendered += _certainty_note(qualified)
    return rendered, problems


_POLISH_SYSTEM = """You rewrite an academic advisor's answer so a student can read it easily.
The answer is already correct and complete -- you are NOT checking it, adding to it, or
reasoning about it. You are rewriting it.

Output ONLY JSON: {"prose": "<the rewritten answer>", "fact_refs": {"<slot>": "<fact key>"}}

RULES -- a rewrite that breaks any of these is thrown away:
- Every number, code, grade, date and name you state MUST be a {slot} bound in fact_refs to a
  fact key. NEVER type a value into the prose yourself. This is not a style rule: a typed value
  is discarded along with your whole rewrite.
- Keep EVERY fact the draft referenced. You may add another fact from the list if it genuinely
  helps; you may not drop one.
- Do not add caveats, hedges, or confidence statements -- those are appended automatically.
- Do not invent advice, next steps, or reassurance the draft does not contain.

STYLE:
- Address the student directly ("you"), never "the student".
- Plain sentences a first-year undergraduate reads once and understands.
- No raw field names, JSON, booleans, or internal vocabulary.
- Keep it short. Do not pad."""


async def polish_answer(
    adapter: ChatLLMAdapter,
    question: str,
    facts: dict[str, Fact],
    draft: str,
    draft_refs: dict[str, Any],
    *,
    temperature: float,
    reasoning_effort: str,
) -> str | None:
    """Rewrite an ACCEPTED answer for readability. Returns the rewrite, or None
    to keep the original.

    The live evals shipped grounded, complete, badly phrased answers -- "For
    course 00960211, the student is True. Missing prerequisites are ." Phrasing
    is the one thing no deterministic renderer can fix, because the sentence
    structure is the composing model's.

    Safe because the rewrite is not trusted, only re-checked. It re-emits the
    same {prose, fact_refs} shape and goes back through `resolve_final`, so a
    typed number is structurally impossible and the certainty note regenerates
    from whatever it slots. It must also reference every fact the draft did --
    a set comparison, so a fact quietly dropped to read better is caught without
    a second completeness call. Any failure returns None and the caller ships
    the draft, which already passed grounding AND completeness.

    ONE attempt, never a repair loop: retrying a rewrite that just tried to
    fabricate is how a polish step turns into a fabrication generator.
    """
    # The hedge is withheld from the rewrite and re-attached afterwards. Shown
    # the note and told not to write hedges, the model folded it into flat prose
    # instead -- so it never sees it, and cannot restate, soften, or lose it.
    draft_body, draft_note = _split_certainty_note(draft)
    draft = draft_body
    try:
        out = await adapter.complete_json(
            system_prompt=_POLISH_SYSTEM,
            user_prompt=(
                f"QUESTION: {question}\n\n"
                f"{response_language_directive(question)}\n\n"
                f"FACTS (slot these by key; the ONLY values you may state):\n"
                + "\n".join(f"  {key} = {summarize_value(f.value)}" for key, f in facts.items())
                + f"\n\nDRAFT ANSWER (correct -- rewrite it, do not re-derive it):\n{draft}\n\n"
                "Emit the rewritten JSON now."
            ),
            temperature=temperature,
            thinking_enabled=False,
            reasoning_effort=reasoning_effort,
            timeout=_GATE_TIMEOUT_S,
        )
    except LLMAdapterError:
        return None

    prose = str((out or {}).get("prose") or "")
    if not prose:
        return None
    refs = (out or {}).get("fact_refs") or {}
    # Kept every fact the accepted draft stood on? Compare the fact KEYS, not the
    # slot names -- the rewrite is free to name its own slots.
    #
    # Only refs whose slot actually APPEARS in the prose count. A declared-but-
    # unwritten ref satisfied a naive set check while contributing nothing to the
    # text, which is how the 2026-07-18 run shipped "It has been offered in spring
    # in 3 recorded semesters" -- the course it was about silently gone.
    used = {key for slot, key in refs.items() if "{" + slot + "}" in prose}
    if not used >= set(draft_refs.values()):
        return None
    rendered, problems = resolve_final(question, facts, prose, refs)
    if problems:
        return None
    # Every course the draft named must still be named. A code reaching the draft
    # from the QUESTION never appears in fact_refs, so the ref check above cannot
    # protect it -- and twice the rewrite replaced it with "This course".
    if not _course_codes(rendered) >= _course_codes(draft):
        return None
    # Internal vocabulary is not for students. Told plainly not to, a rewrite
    # still shipped "based on predicted_pattern with confidence 0.95".
    lowered = rendered.lower()
    if any(term in lowered for term in _INTERNAL_VOCABULARY):
        return None
    # The hedge is PRESERVED, never re-derived. Re-deriving let the rewrite slot
    # its way out of one: the same run turned "On certainty: 3 -- predicted from
    # recent offering history (not a guaranteed future schedule)" into "The
    # spring pattern is marked reliable" -- a calibrated uncertainty replaced by
    # reassurance. A rewrite may not change what we claim to know.
    body, _ = _split_certainty_note(rendered)
    return body + draft_note


async def completeness_gate(
    adapter: ChatLLMAdapter,
    question: str,
    sub_asks: list[str],
    answer: str,
    *,
    temperature: float,
    reasoning_effort: str,
) -> list[str]:
    """§9.2: the sub-asks the draft answer leaves unaddressed (empty = complete).

    Fails OPEN -- a gate-call failure returns "complete" rather than trapping the
    student behind a broken checker; the turn budget still bounds continuations.
    """
    try:
        out = await adapter.complete_json(
            system_prompt=_COMPLETENESS_SYSTEM,
            user_prompt=json.dumps(
                {"question": question, "sub_asks": sub_asks, "draft_answer": answer},
                ensure_ascii=False,
            ),
            temperature=temperature,
            thinking_enabled=True,
            reasoning_effort=reasoning_effort,
            timeout=_GATE_TIMEOUT_S,
        )
    except LLMAdapterError:
        return []
    unaddressed = out.get("unaddressed")
    if isinstance(unaddressed, list):
        return [str(s).strip() for s in unaddressed if str(s).strip()]
    return []


__all__ = ["resolve_final", "completeness_gate"]
