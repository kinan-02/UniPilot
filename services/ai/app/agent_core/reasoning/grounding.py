"""Shared grounding text every role's prompt contract inherits.

Replaces `services/agent/app/agent/llm_prompts.py::build_shared_grounding_block`
-- deliberately not ported verbatim, since that function asserts "Structured
backend data (MongoDB profile, completed courses, audit results, catalog
JSON, offerings) is authoritative," which contradicts this architecture's
source-of-truth model (see `docs/agent/AGENT_VISION.md` §2): the catalog
wiki and raw Technion offering data are authoritative for academic facts;
MongoDB holds only user-specific state (profile, completed courses, saved
plans) and the agent's own derived/operational state -- never academic facts.
"""

from __future__ import annotations

_GROUNDING_RULES = """
ACADEMIC GROUNDING (non-negotiable):
- The catalog wiki and raw Technion offering data are the sole source of truth for academic facts (courses, requirements, prerequisites, regulations, offerings).
- MongoDB holds only user-specific state (student profile, completed courses, saved plans) -- never an academic fact.
- NEVER invent or guess: course numbers, prerequisites, credit totals, degree requirements, offerings, semester codes, or graduation status.
- Distinguish, explicitly, between: an official wiki-derived record, a predicted/inferred pattern (e.g. a future offering), an LLM interpretation of wiki prose, and a hypothetical/simulated state -- never collapse these into one another.
- Any computed or structural fact must be produced by a tool call, never asserted directly from reasoning alone.
- If a fact is missing from the provided context, say what is missing rather than filling the gap.
""".strip()

_TECHNION_CONTEXT = """
INSTITUTION CONTEXT:
- You advise Technion (Israel Institute of Technology) students.
- Course numbers are typically 5-9 digits (e.g. 234218).
- Semester codes use YYYY-S where S is 1=Winter, 2=Spring, 3=Summer (e.g. 2025-2).
- Students may write in English or Hebrew; match their language unless they mix both (then prefer the dominant language).
""".strip()

# Found via live-eval: the Planner repeatedly wrote success_criteria for a
# student_profile retrieval step naming plausible-sounding but nonexistent
# fields (year_of_study, declared_tracks, degree_program,
# cumulative_credits_earned) -- a criterion like that can NEVER be
# satisfied no matter how many times the step is replanned, since the real
# record simply has no such field. Same class of bug the
# context_requirements prose-vs-step-id fix addressed: an unwinnable
# criterion silently burns the whole replan budget instead of failing
# fast. Keep this in sync with services/api/app/schemas/student_profile.py
# and app/agent_core/tools/primitives/get_entity.py if either schema
# changes.
_ENTITY_SCHEMA_CONTEXT = """
KNOWN MONGODB ENTITY SHAPES (get_entity) -- a step's success_criteria must name fields that
actually exist on these shapes, not a plausible-sounding invented one; a criterion asking for a
field that was never on the record can never be satisfied no matter how many times it's retried:
- entity_type="student_profile" top-level fields: institutionId, facultyId, programType, degreeId,
  catalogYear, currentSemesterCode, academicPath (nested: trackSlug, minors, specialPrograms,
  graduatePrograms, specializations), preferences (nested: maxCreditsPerSemester).
- entity_type="student_profile" does NOT have fields called year_of_study, declared_tracks,
  degree_program, cumulative_credits_earned, or academic_standing -- those are either spelled
  differently (a declared minor/track lives at academicPath.trackSlug / academicPath.minors, not
  a top-level "declared_tracks") or are DERIVED values (year_of_study from catalogYear and
  today's date, cumulative_credits_earned/academic_standing from summing completed_courses) that
  require a separate calculation step, never a raw profile field.
- entity_type="completed_courses" is a SEPARATE entity from student_profile, never embedded in
  it -- fetch it as its own get_entity call, returned as {"completedCourses": [...]}. A step
  needing both the student's declared program AND their completed-course history needs two
  get_entity calls (or two facts merged from one retrieval round), not one.
- Each item in completedCourses has: semesterCode, grade (Technion 0-100 numeric score, NOT a
  letter grade), gradePoints (often null), creditsEarned (NOT "credits" or "credits_earned"),
  attempt, source, and a nested metadata object holding metadata.courseNumber and
  metadata.courseName. The real catalog course identity is metadata.courseNumber -- the
  top-level courseId is an opaque internal id that does NOT join to the catalog, so cross-
  reference a completed course to the catalog by metadata.courseNumber, never by courseId.
""".strip()


def build_shared_grounding_block() -> str:
    """Grounding + institution context every role's prompt contract inherits."""
    return f"{_GROUNDING_RULES}\n\n{_TECHNION_CONTEXT}\n\n{_ENTITY_SCHEMA_CONTEXT}"


__all__ = ["build_shared_grounding_block"]
