"""Turn -> one student-facing sentence about what the agent is doing right now.

The answer is composed only after the loop concludes, so for a question that
takes three minutes this is the only thing that changes on screen the whole
time. It has to earn that place: "Working through your question" three times in
a row is barely better than a spinner.

Two hard rules, because this text goes straight into a student's chat window:

1. NEVER emit an internal name. Not a tool name, not a field name, not an
   ObjectId, not a user id. Every tool is opted IN to a phrase, and every
   subject is opted IN by argument name -- anything unmapped degrades to a
   plainer phrase rather than leaking.
2. NEVER let this cost an answer. Subject extraction is best-effort and total:
   any malformed argument falls back to the bare phrase.

Course codes are rendered through `course_display_name`, so a student reads
"Checking your eligibility for E-Commerce Models", not "... for 00960211".
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agent_core.loop.course_names import course_display_name

GENERIC = "Working through your question"

# Anything shaped like an internal identifier is never shown, whatever argument
# it arrived in: 24-hex Mongo ObjectIds, and long opaque tokens.
_OBJECT_ID = re.compile(r"^[0-9a-f]{24}$", re.I)
_COURSE_CODE = re.compile(r"^\d{8}$")
_MAX_SUBJECT_CHARS = 60


@dataclass(frozen=True)
class _Phrase:
    """How one tool narrates itself.

    `bare` always works. `with_subject` is used only when a safe subject can be
    read from `subject_arg`; `plural` only when a turn batches several calls of
    the same tool.
    """

    bare: str
    with_subject: str | None = None
    subject_arg: str | None = None
    plural: str | None = None


# `get_entity` names a closed vocabulary of entity types, so it gets a real
# phrase per type instead of echoing the raw type name. `entity_id` is a user id
# or ObjectId and is never shown.
_ENTITY_PHRASES = {
    "student_profile": "Reading your profile",
    "completed_courses": "Reading your completed courses",
    "course": "Reading the course details",
    "semester_plans": "Reading your semester plans",
    "semester_plan": "Reading your semester plan",
    "wiki_page": "Reading the program pages",
    "track": "Reading your track",
    "program": "Reading your program",
    "minor": "Reading the minor requirements",
    "faculty": "Reading the faculty pages",
}

_PHRASES: dict[str, _Phrase] = {
    # -- data tools --
    "check_eligibility": _Phrase(
        "Checking your eligibility",
        "Checking whether you can take {subject}",
        "course_id",
        "Checking your eligibility for {count} courses",
    ),
    "get_course_profile": _Phrase(
        "Reading the course details", "Reading the details for {subject}", "course_id",
        "Reading the details for {count} courses",
    ),
    "find_requirement_substitutes": _Phrase(
        "Looking for alternatives", "Looking for alternatives to {subject}", "course_id",
    ),
    "simulate_course_disruption": _Phrase(
        "Working through the knock-on effects",
        "Working out what happens if {subject} changes",
        "course_id",
    ),
    "compare_plans": _Phrase("Comparing your plans", "Comparing your plans around {subject}", "focus_course_id"),
    "get_track_requirements": _Phrase(
        "Reading your track requirements", "Reading the {subject} requirements", "track_slug"
    ),
    "audit_graduation_progress": _Phrase(
        "Auditing your graduation progress", "Auditing your progress against {subject}", "track_slug"
    ),
    "search_knowledge": _Phrase("Searching the catalog and wiki", "Searching for {subject}", "query"),
    "get_policy_answer": _Phrase("Checking Technion regulations", "Checking the rules on {subject}", "question"),
    "traverse_relationship": _Phrase(
        "Following prerequisite chains", "Following the chain from {subject}", "entity"
    ),
    "extract_temporal_pattern": _Phrase(
        "Looking at when this is usually offered", "Checking when {subject} usually runs", "entity"
    ),
    "get_entity": _Phrase("Reading your academic record", subject_arg="entity_type"),
    "get_current_date": _Phrase("Checking today's date"),
    "get_current_semester": _Phrase("Checking the current semester"),
    "search_over_state": _Phrase("Searching your record"),
    "interpret_text": _Phrase("Reading the fine print"),
    "apply_deterministic_rule": _Phrase("Applying the rule"),
    "propose_action": _Phrase("Putting together a suggestion"),
    "mutate_state": _Phrase("Trying that change"),
    "compose_answer": _Phrase("Writing your answer"),
    # -- meta-tools (§_META_TOOLS) --
    # `_preload_student_state` has the record in hand by turn 1, so most turns of
    # a typical question are meta. Leaving these out made every phrase generic.
    # They stay subject-free on purpose: their arguments are field names and fact
    # keys ("track_slug", "call_2"), which is exactly the jargon rule 1 forbids.
    "compute": _Phrase("Doing the arithmetic"),
    "select": _Phrase("Picking out the details that matter"),
    "surface_fact": _Phrase("Pulling out what your record says"),
    "surface_facts": _Phrase("Pulling out what your record says"),
    "map": _Phrase("Checking each course in turn"),
    "spawn_subtask": _Phrase("Breaking this into smaller questions"),
    "final_answer": _Phrase("Writing your answer"),
    "clarify": _Phrase("Working out what to ask you"),
}


def _prettify_slug(slug: str) -> str:
    """`track-information-systems-engineering` -> `Information Systems Engineering`."""
    words = slug.removeprefix("track-").replace("-", " ").replace("_", " ").split()
    # Acronyms stay upper; everything else gets title case.
    return " ".join(word.upper() if len(word) <= 2 else word.capitalize() for word in words)


def _render_subject(tool: str, raw: Any) -> str | None:
    """A safe, readable subject, or None to fall back to the bare phrase."""
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value or _OBJECT_ID.match(value):
        return None
    if tool == "get_entity":
        return None  # handled by _ENTITY_PHRASES, never echoed raw
    if _COURSE_CODE.match(value):
        return course_display_name(value) or f"course {value}"
    if value.startswith("track-") or (("-" in value or "_" in value) and " " not in value):
        return _prettify_slug(value)
    if len(value) > _MAX_SUBJECT_CHARS:
        value = value[: _MAX_SUBJECT_CHARS - 1].rstrip() + "…"
    return f"“{value}”"


def _tool_of(call: dict[str, Any]) -> str:
    """The model emits `tool`; `_split_calls` renames it to `tool_name` when it
    builds data-tool requests. Read both -- reading only the renamed key matched
    nothing and made every turn report the generic phrase."""
    return str(call.get("tool") or call.get("tool_name") or "")


def phrase_for(calls: list[dict[str, Any]]) -> str:
    """One sentence for the tools a turn is about to run."""
    for call in calls:
        tool = _tool_of(call)
        phrase = _PHRASES.get(tool)
        if phrase is None:
            continue

        same = [other for other in calls if _tool_of(other) == tool]
        if len(same) > 1 and phrase.plural:
            return phrase.plural.format(count=len(same))

        arguments = same[0].get("arguments")
        arguments = arguments if isinstance(arguments, dict) else {}

        if tool == "get_entity":
            entity_phrase = _ENTITY_PHRASES.get(str(arguments.get("entity_type") or ""))
            return entity_phrase or phrase.bare

        if phrase.with_subject and phrase.subject_arg:
            subject = _render_subject(tool, arguments.get(phrase.subject_arg))
            if subject:
                return phrase.with_subject.format(subject=subject)
        return phrase.bare
    return GENERIC


__all__ = ["GENERIC", "phrase_for"]
