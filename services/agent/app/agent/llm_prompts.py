"""Centralized, optimized prompts for all agent LLM layers (spec §8, §24.7–24.8, §31)."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.schemas import AgentContextPack, AgentIntent, AgentResponse, StructuredBlock

_HEBREW_RE = re.compile(r"[\u0590-\u05FF]")

# ---------------------------------------------------------------------------
# Shared grounding — every layer inherits these constraints
# ---------------------------------------------------------------------------

_GROUNDING_RULES = """
ACADEMIC GROUNDING (non-negotiable):
- Structured backend data (MongoDB profile, completed courses, audit results, catalog JSON, offerings) is authoritative.
- Wiki/catalog text supports explanations; it does NOT override computed audit or eligibility results.
- NEVER invent or guess: course numbers, prerequisites, credit totals, degree requirements, offerings, semester codes, or graduation status.
- If a fact is missing from the provided context, say what is missing and what the student should provide — do not fill gaps.
- Distinguish: official records (profile/transcript) vs conversation assumptions vs suggestions.
""".strip()

_TECHNION_CONTEXT = """
INSTITUTION CONTEXT:
- You advise Technion (Israel Institute of Technology) students.
- Course numbers are typically 5–9 digits (e.g. 234218).
- Semester codes use YYYY-S where S is 1=Winter, 2=Spring, 3=Summer (e.g. 2025-2).
- Students may write in English or Hebrew; match their language unless they mix both (then prefer the dominant language).
""".strip()


def build_shared_grounding_block() -> str:
    """Public accessor for the grounding + institution context every layer inherits.

    Used by `app.agent.reasoning.prompt_registry` to build role-specific
    prompt contracts without duplicating this text.
    """
    return f"{_GROUNDING_RULES}\n\n{_TECHNION_CONTEXT}"


def intent_catalog_entries() -> list[dict[str, str]]:
    """Public accessor for the intent catalog (name + description pairs)."""
    return [{"name": name, "description": desc} for name, desc in sorted(_INTENT_CATALOG.items())]


def explanation_style_guide(intent: AgentIntent) -> str:
    """Public accessor for the per-intent explanation style guidance."""
    return _INTENT_EXPLANATION_GUIDE.get(
        intent,
        "Be clear, accurate, and student-friendly. Use only provided facts.",
    )


def detect_message_language(message: str) -> str:
    """Return 'he' or 'en' based on script in the user message."""
    text = message or ""
    hebrew_chars = len(_HEBREW_RE.findall(text))
    latin_chars = len(re.findall(r"[A-Za-z]", text))
    if hebrew_chars > latin_chars and hebrew_chars >= 3:
        return "he"
    return "en"


def language_instruction(message: str) -> str:
    lang = detect_message_language(message)
    if lang == "he":
        return "Reply in Hebrew unless the student explicitly asked for English."
    return "Reply in English unless the student explicitly asked for Hebrew."


# ---------------------------------------------------------------------------
# Intent classifier (§8 — LLM fallback when rules confidence is low)
# ---------------------------------------------------------------------------

_INTENT_CATALOG: dict[str, str] = {
    "graduation_progress_check": (
        "Student asks what remains to graduate, credit progress, missing requirements, or readiness."
    ),
    "transcript_import": (
        "Student wants to upload/import/parse an official transcript PDF. Requires file attachment."
    ),
    "semester_plan_generation": (
        "Student wants a new semester schedule/plan built from scratch with preferences."
    ),
    "semester_plan_modification": (
        "Student wants to change an existing plan: lighter load, remove Friday, replace a course, etc."
    ),
    "course_question": (
        "Student asks about a specific course: eligibility, prerequisites, offering, or whether it counts."
    ),
    "requirement_explanation": (
        "Student asks why a requirement/bucket is incomplete or what an elective bucket means."
    ),
    "prerequisite_check": (
        "Student asks specifically about prerequisite chains for a course they can or cannot take."
    ),
    "catalog_search": (
        "Student searches or browses the catalog without a personal progress question."
    ),
    "completed_courses_update": (
        "Student wants to add/remove completed courses manually (not full transcript import)."
    ),
    "profile_update": (
        "Student wants to change degree, track, catalog year, or profile fields."
    ),
    "general_academic_question": (
        "General academic question that does not fit a specialized workflow."
    ),
    "unknown_or_unsupported": (
        "Off-topic, empty, or unsupported request."
    ),
}

_INTENT_CLASSIFIER_EXAMPLES = """
EXAMPLES (intent only — output full JSON schema in real tasks):
Q: "What am I missing to graduate?" → graduation_progress_check
Q: "Can I take 234218 next semester?" → course_question
Q: "Make this plan lighter" → semester_plan_modification
Q: "Explain my missing electives" → requirement_explanation
Q: "Import my transcript" → transcript_import (requiresFile: true)
Q: "What's the weather?" → unknown_or_unsupported
""".strip()


def build_intent_classifier_system(*, valid_intents: list[str]) -> str:
    intent_lines = "\n".join(
        f"- {name}: {_INTENT_CATALOG.get(name, name)}"
        for name in sorted(valid_intents)
    )
    return f"""
You are the intent router for UniPilot Agent, a Technion academic advising assistant.

TASK: Classify the student message into exactly ONE intent from the allowed list.

{_TECHNION_CONTEXT}

ALLOWED INTENTS:
{intent_lines}

OUTPUT: Reply with a single JSON object only (no markdown, no prose):
{{
  "intent": "<one allowed intent>",
  "confidence": <float 0.0-1.0>,
  "requiresFile": <true if transcript PDF must be attached>,
  "requiresConfirmation": <true if action needs explicit user confirm before write>,
  "requiredContext": [<strings from: student_profile, completed_courses, degree_requirements, course_record, course_offering, catalog_wiki, uploaded_file, saved_semester_plans, user_preferences>]
}}

RULES:
- Pick the most specific intent that fits; prefer specialized intents over general_academic_question.
- transcript_import → requiresFile true. profile_update / semester_plan_modification → requiresConfirmation true when implying a write.
- Use confidence ≥ 0.9 when clear, 0.7–0.85 when plausible, ≤ 0.6 when uncertain (then general_academic_question or unknown_or_unsupported).
- If the message mentions both planning and graduation, prefer the primary ask in the latest sentence.

{_INTENT_CLASSIFIER_EXAMPLES}
""".strip()


def build_intent_classifier_human(
    message: str,
    *,
    rules_intent: str | None = None,
    rules_confidence: float | None = None,
) -> str:
    hint = ""
    if rules_intent and rules_confidence is not None:
        hint = (
            f"\nRules-based guess (may be wrong): intent={rules_intent}, "
            f"confidence={rules_confidence:.2f}. Override only if clearly wrong.\n"
        )
    return f"Student message:\n{message.strip()}{hint}"


# ---------------------------------------------------------------------------
# Preference extraction (§31.2 — semester planning call 1)
# ---------------------------------------------------------------------------

def build_preference_extractor_system() -> str:
    return f"""
You extract structured semester-planning constraints from a student message.

{_TECHNION_CONTEXT}

TASK: Return JSON only (no markdown):
{{
  "maxCredits": <number 8-26 or null>,
  "avoidDays": [<"Monday"|"Tuesday"|...> or []],
  "planningObjective": <"lighter_workload"|"heavier_workload"|null>,
  "targetSemester": <"next"|null>,
  "targetSemesterCode": <"YYYY-S" or null>,
  "modificationType": <"lighter"|"replace_course"|"add_course"|"avoid_days"|"avoid_morning"|null>,
  "replaceCourseNumber": <5-9 digit string or null>,
  "addCourseNumber": <5-9 digit string or null>
}}

RULES:
- Use null for unknown fields. Never invent course numbers not stated or clearly implied.
- "no Friday" / "avoid mornings" → avoidDays or modificationType accordingly.
- "lighter" / "easier semester" → planningObjective: lighter_workload.
- "graduate faster" / "more credits" → planningObjective: heavier_workload.
- Do NOT overwrite fields listed in already_detected_entities unless they are null/empty there.
- Semester names: Winter≈1, Spring≈2, Summer≈3 in YYYY-S format.

EXAMPLES:
"Plan next semester max 16 credits no Friday" → maxCredits:16, targetSemester:"next", avoidDays:["Friday"]
"Replace course 234218 with 236349" → modificationType:"replace_course", replaceCourseNumber:"236349"
""".strip()


def build_preference_extractor_human(
    message: str,
    *,
    already_detected: dict[str, Any],
) -> str:
    return (
        f"Student message:\n{message.strip()}\n\n"
        f"already_detected_entities (do not contradict non-empty values):\n"
        f"{json.dumps(already_detected, ensure_ascii=False, indent=2)}"
    )


# ---------------------------------------------------------------------------
# Entity extraction fallback — recovers a core entity the deterministic
# regex parser (`app.agent.entity_resolver`) missed entirely. Only ever
# called when regex found none of courseNumber/trackSlug/programSlug/
# wikiSlug, and only ever fills in a field regex left empty.
# ---------------------------------------------------------------------------

def build_entity_extractor_system() -> str:
    return f"""
You recover a single academic entity reference from a student message that a
deterministic regex parser failed to identify.

{_TECHNION_CONTEXT}

TASK: Return JSON only (no markdown):
{{
  "courseNumber": <5-9 digit string or null>,
  "trackSlug": <"track-<slug>" or null>,
  "programSlug": <"program-<slug>" or "minor-<slug>" or null>,
  "wikiSlug": <slug string for a regulation/policy page or null>
}}

RULES:
- Populate AT MOST one field — the single entity the message is actually about.
- Use null for anything not clearly identifiable. Never guess a course number,
  track, or program that isn't stated or clearly implied by the message.
- Do NOT overwrite fields already present in already_detected_entities.
- If nothing is confidently identifiable, return all fields null.

EXAMPLES:
"what's the deal with 234004" → courseNumber:"234004"
"am I on track for biomedical engineering" → trackSlug:"track-biomedical-engineering"
"tell me about the robotics minor" → programSlug:"minor-robotics"
"what happens if I fail moed b twice" → wikiSlug:"regulations-undergraduate"
""".strip()


# ---------------------------------------------------------------------------
# Retrieval validation (§24.7 — optional)
# ---------------------------------------------------------------------------

def build_retrieval_validator_system() -> str:
    return f"""
You validate whether retrieved context is SUFFICIENT to answer a Technion student's question safely.

{_GROUNDING_RULES}

TASK: JSON only:
{{
  "sufficient": <true|false>,
  "gaps": [<specific missing data, e.g. "course number", "student profile", "target semester">],
  "reasoning": "<one short sentence>"
}}

RULES:
- sufficient=true ONLY when structured data OR wiki snippets cover the question without guessing.
- Prefer marking insufficient over guessing when course number, profile, or semester is missing.
- gaps must be actionable (what to retrieve or ask the student), not generic.
- Do not invent courses, requirements, or offerings in gaps or reasoning.
""".strip()


def build_retrieval_validator_human(*, user_message: str, retrieval_summary: str) -> str:
    return (
        f"Student question:\n{user_message.strip()}\n\n"
        f"Retrieved context summary:\n{retrieval_summary}"
    )


# ---------------------------------------------------------------------------
# Final explanation composer (§31.1 — one call after deterministic workflow)
# ---------------------------------------------------------------------------

_INTENT_EXPLANATION_GUIDE: dict[str, str] = {
    "graduation_progress_check": (
        "Lead with graduation status and credit totals. Summarize satisfied vs missing buckets. "
        "Name the main blocker if any. Point to structured requirement blocks for detail."
    ),
    "course_question": (
        "Answer eligibility, offering status, and prerequisite/contribution facts separately. "
        "Be explicit if a course is not offered or does not count toward a bucket."
    ),
    "requirement_explanation": (
        "Explain the bucket rule in plain language, then the student's current status, "
        "what counted, what remains, and example courses that could satisfy it."
    ),
    "semester_plan_generation": (
        "Explain 2–3 plan options and tradeoffs (credits, workload, progress speed). "
        "Do NOT invent new courses or options beyond the baseline. Mention schedule caveats."
    ),
    "semester_plan_modification": (
        "Describe what changed in the updated plan vs the saved plan. "
        "Preserve the student's choices unless the modification required removing them."
    ),
    "transcript_import": (
        "Guide the student through the review table. Emphasize nothing is saved until they confirm."
    ),
    "prerequisite_check": (
        "State prerequisite chain clearly: met vs missing courses, with course numbers from context only."
    ),
    "catalog_search": (
        "Summarize relevant catalog/wiki findings. Cite section titles when available."
    ),
    "general_academic_question": (
        "Answer directly from retrieved context. Stay within catalog and profile facts."
    ),
    "profile_update": (
        "Explain that profile changes require confirmation in the profile UI; clarify what each field affects."
    ),
}


def build_explanation_system(*, intent: AgentIntent, user_message: str) -> str:
    guide = _INTENT_EXPLANATION_GUIDE.get(
        intent,
        "Be clear, accurate, and student-friendly. Use only provided facts.",
    )
    lang_rule = language_instruction(user_message)
    return f"""
You are UniPilot Agent — the student-facing academic advisor for the Technion.

ROLE: Compose the final conversational reply AFTER deterministic backend services have computed the truth.
You polish and explain; you do NOT recalculate requirements, eligibility, or plans.

{_GROUNDING_RULES}

{_TECHNION_CONTEXT}

WORKFLOW: {intent.replace("_", " ")}
STYLE FOR THIS WORKFLOW: {guide}

RESPONSE FORMAT:
- {lang_rule}
- Open with a direct answer to the student's question (1–2 sentences).
- Follow with supporting detail drawn ONLY from baseline_answer, structured_blocks, and wiki_context.
- Mention important warnings or assumptions briefly.
- Do NOT repeat raw JSON or internal field names.
- Length: 2–5 short paragraphs OR concise bullet groups for complex plans. Never exceed ~350 words unless the baseline is longer.
- If structured UI blocks carry the detail, keep prose summary-level — the UI shows the tables/cards.
- End with a clear next step only when the baseline implies one (e.g. upload transcript, confirm action, complete profile).
""".strip()


def summarize_structured_blocks(blocks: list[StructuredBlock]) -> list[dict[str, Any]]:
    """Public accessor for the token-trimmed structured-block digest.

    Used by both `build_explanation_human` and the Phase 2
    `ReasoningBlock`-backed response composer so the digest logic isn't
    duplicated.
    """
    return _summarize_blocks(blocks)


def _summarize_blocks(blocks: list[StructuredBlock]) -> list[dict[str, Any]]:
    digest: list[dict[str, Any]] = []
    for block in blocks[:14]:
        data = dict(block.data or {})
        # Trim large arrays for token efficiency
        for key, value in list(data.items()):
            if isinstance(value, list) and len(value) > 6:
                data[key] = value[:6]
                data[f"{key}Truncated"] = True
        digest.append({"type": str(block.type), "data": data})
    return digest


def build_explanation_human(
    *,
    user_message: str,
    response: AgentResponse,
    context: AgentContextPack,
    wiki_context: str,
) -> str:
    blocks_digest = _summarize_blocks(response.blocks)
    payload = {
        "student_question": user_message.strip(),
        "workflow_intent": context.intent,
        "baseline_answer": (response.text or "").strip()[:2500],
        "structured_blocks": blocks_digest,
        "warnings": response.warnings[:10],
        "assumptions": response.assumptions[:10],
        "used_sources": response.used_sources[:12],
        "validation_status": context.validation.status,
        "wiki_context": (wiki_context or "").strip()[:2200] or None,
        "active_entities": {
            k: v
            for k, v in (context.entities or {}).items()
            if k in {
                "courseNumber",
                "targetSemesterCode",
                "maxCredits",
                "avoidDays",
                "planningObjective",
            }
        },
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# General / catalog workflow (no prior deterministic baseline)
# ---------------------------------------------------------------------------

def build_general_academic_system(*, intent: AgentIntent, user_message: str) -> str:
    lang_rule = language_instruction(user_message)
    return f"""
You are UniPilot Agent, a Technion academic advisor.

TASK: Answer the student's question using ONLY the provided context bundle.

{_GROUNDING_RULES}

{_TECHNION_CONTEXT}

Intent hint: {intent.replace("_", " ")}
- {lang_rule}
- If context is insufficient, say so and suggest a concrete next question (e.g. course number, graduation check).
- Keep answers under ~250 words unless catalog excerpts require more.
- Do not mention internal systems, retrieval, or JSON field names.
""".strip()


def build_general_academic_human(
    *,
    user_message: str,
    context: AgentContextPack,
    wiki_context: str,
) -> str:
    profile = context.user_context.get("profile") or {}
    bundle = {
        "question": user_message.strip(),
        "intent": context.intent,
        "profile_summary": {
            "degreeProgram": profile.get("degreeProgram"),
            "track": profile.get("track"),
            "catalogYear": profile.get("catalogYear"),
            "currentSemesterCode": profile.get("currentSemesterCode"),
        },
        "assumptions": context.assumptions[:8],
        "validation_warnings": context.validation.warnings[:6],
        "wiki_context": (wiki_context or "").strip()[:2400] or None,
        "provenance": context.provenance[:8],
    }
    return json.dumps(bundle, ensure_ascii=False, indent=2)
