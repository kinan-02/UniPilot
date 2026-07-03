"""Deterministic 'Why?' answers from MAS negotiation transcripts."""

from __future__ import annotations

from typing import Any

from app.repositories.agent_session_repository import find_agent_session_by_id_and_user

_TOPIC_KEYWORDS: dict[str, tuple[str, ...]] = {
    "veto": ("veto", "reject", "blocked", "block", "fail", "ineligible", "violation", "נפסל", "נדחה"),
    "plan": ("course", "plan", "recommend", "semester", "קורס", "תוכנית", "סמסטר"),
    "utility": ("utility", "score", "choose", "variant", "arbitr", "למה", "נבחר"),
    "preference": ("preference", "avoid", "friday", "workload", "credit", "עומס", "שישי"),
    "goal": ("goal", "intent", "clarif", "מטרה", "כוונה"),
    "progress": ("graduation", "progress", "degree", "תואר", "התקדמות"),
}


def _detect_topics(question: str) -> set[str]:
    lowered = question.lower()
    topics: set[str] = set()
    for topic, keywords in _TOPIC_KEYWORDS.items():
        if any(keyword in lowered or keyword in question for keyword in keywords):
            topics.add(topic)
    return topics


def _payload(turn: dict[str, Any]) -> dict[str, Any]:
    payload = turn.get("payload")
    return payload if isinstance(payload, dict) else {}


def _reasoning_trace(turn: dict[str, Any]) -> dict[str, Any] | None:
    trace = _payload(turn).get("reasoningTrace")
    return trace if isinstance(trace, dict) else None


def _turn_excerpt(turn: dict[str, Any]) -> str:
    parts: list[str] = []
    rationale = turn.get("rationale")
    if isinstance(rationale, str) and rationale.strip():
        parts.append(rationale.strip())

    trace = _reasoning_trace(turn)
    if trace:
        for key in ("reasoning", "headline", "notes"):
            value = trace.get(key)
            if isinstance(value, str) and value.strip():
                parts.append(value.strip())
        if trace.get("progressScore") is not None:
            parts.append(f"Progress score: {trace.get('progressScore')}")
        if trace.get("unlockCount") is not None:
            parts.append(f"Unlock count: {trace.get('unlockCount')}")
        critique_trace = trace.get("critiques")
        if isinstance(critique_trace, list) and critique_trace:
            messages = [
                str(item.get("message") or item.get("type"))
                for item in critique_trace[:3]
                if isinstance(item, dict)
            ]
            if messages:
                parts.append("Critiques: " + "; ".join(messages))
        if trace.get("critiqueCount") is not None:
            parts.append(f"Preference critiques: {trace.get('critiqueCount')}")
        if trace.get("violationCount") is not None:
            parts.append(f"Violations found: {trace.get('violationCount')}")
        evidence = trace.get("evidence")
        if isinstance(evidence, dict):
            if evidence.get("totalCredits") is not None and evidence.get("maxCredits") is not None:
                parts.append(
                    f"Credits: {evidence.get('totalCredits')} / {evidence.get('maxCredits')}"
                )
            if evidence.get("probationPressured"):
                parts.append("Probation pressure flagged.")
        if trace.get("approved") is False:
            parts.append("Hard gate failed.")
        variants = trace.get("variants")
        if isinstance(variants, list) and variants:
            parts.append(f"Evaluated {len(variants)} planner variant(s).")
        violations = trace.get("violations")
        if isinstance(violations, list) and violations:
            parts.append("Violations: " + "; ".join(str(item) for item in violations[:4]))

    payload = _payload(turn)
    violations = payload.get("violations") or payload.get("typedViolations")
    if isinstance(violations, list) and violations:
        rendered = []
        for item in violations[:4]:
            if isinstance(item, dict):
                rendered.append(str(item.get("message") or item))
            else:
                rendered.append(str(item))
        if rendered:
            parts.append("Violations: " + "; ".join(rendered))

    references = turn.get("references")
    if isinstance(references, list) and references:
        parts.append("References: " + ", ".join(str(ref) for ref in references[:4]))

    return " ".join(parts).strip()


def _turn_matches_topics(turn: dict[str, Any], topics: set[str]) -> bool:
    role = str(turn.get("agent_role") or "")
    action = str(turn.get("action") or "")

    if "veto" in topics and action == "veto":
        return True
    if "veto" in topics and role in {"catalog_scout", "risk_sentinel"}:
        return True
    if "plan" in topics and role in {"planner", "arbiter", "explainer"}:
        return True
    if "utility" in topics and role == "arbiter":
        return True
    if "preference" in topics and role in {"student_advocate", "progress_scout"}:
        return True
    if "goal" in topics and role == "goal_analyst":
        return True
    if "progress" in topics and role == "progress_scout":
        return True
    return False


def _build_citation(index: int, turn: dict[str, Any]) -> dict[str, Any]:
    return {
        "turnIndex": index,
        "agentRole": turn.get("agent_role"),
        "action": turn.get("action"),
        "excerpt": _turn_excerpt(turn),
        "references": list(turn.get("references") or [])[:6],
        "reasoningTrace": _reasoning_trace(turn),
    }


def answer_agent_session_why(
    session: dict[str, Any],
    *,
    question: str,
) -> dict[str, Any]:
    """Build a grounded answer from the stored negotiation transcript."""
    transcript = list(session.get("transcript") or [])
    if not transcript:
        return {
            "answer": "This session has no negotiation transcript yet.",
            "citations": [],
            "source": "deterministic_transcript",
            "topics": [],
        }

    topics = _detect_topics(question)
    if not topics:
        topics = {"plan", "utility"}

    relevant: list[tuple[int, dict[str, Any]]] = [
        (index, turn)
        for index, turn in enumerate(transcript)
        if isinstance(turn, dict) and _turn_matches_topics(turn, topics)
    ]
    if not relevant:
        relevant = [(len(transcript) - 1, transcript[-1])]

    if "veto" in topics:
        relevant.sort(key=lambda item: 0 if item[1].get("action") == "veto" else 1)

    citations = [_build_citation(index, turn) for index, turn in relevant[:6]]
    answer_parts = [
        f"{citation['agentRole']} ({citation['action']}): {citation['excerpt']}"
        for citation in citations
        if citation.get("excerpt")
    ]

    final_decision = session.get("finalDecision")
    if isinstance(final_decision, dict):
        if "utility" in topics:
            breakdown = final_decision.get("utilityBreakdown")
            if isinstance(breakdown, dict) and breakdown.get("utility") is not None:
                answer_parts.append(f"Committed utility score: {breakdown.get('utility')}")
            arbitration = final_decision.get("arbitration")
            if isinstance(arbitration, dict) and arbitration.get("chosen_variant"):
                answer_parts.append(
                    f"Chosen variant: {arbitration.get('chosen_variant')} "
                    f"(considered {', '.join(arbitration.get('considered_variants') or [])})"
                )
        if "plan" in topics and final_decision.get("course_ids"):
            answer_parts.append(
                "Committed courses: " + ", ".join(str(course_id) for course_id in final_decision["course_ids"])
            )
        summary = final_decision.get("studentSummary")
        if isinstance(summary, dict) and summary.get("headline"):
            answer_parts.append(f"Summary: {summary.get('headline')}")

    return {
        "answer": "\n\n".join(answer_parts) if answer_parts else "No matching negotiation evidence found.",
        "citations": citations,
        "source": "deterministic_transcript",
        "topics": sorted(topics),
    }


async def explain_agent_session_why_for_user(
    database,
    *,
    user_id: str,
    session_id: str,
    question: str,
) -> dict[str, Any]:
    session = await find_agent_session_by_id_and_user(database, session_id, user_id)
    if session is None:
        return {"status": "not_found"}

    cleaned = question.strip()
    if not cleaned:
        return {"status": "validation_error", "errors": ["Question is required."]}

    result = answer_agent_session_why(session, question=cleaned)
    return {
        "status": "ok",
        "question": cleaned,
        **result,
    }
