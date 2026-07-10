"""Output Compliance Agent (AGT-9c) — LLM semantic verifier after deterministic guard."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from app.services.advisor_agent import _build_llm, _extract_json_object, _llm_base_url
from app.services.compliance_guard import _downgrade_confidence

if TYPE_CHECKING:
    from app.services.advisor_agent import AdvisorResponse

HEBREW_RE = re.compile(r"[\u0590-\u05FF]")
DEFAULT_CONTACT_EN = "faculty undergraduate studies office"
DEFAULT_CONTACT_HE = "לשכת לימודי הסמכה בפקולטה"


class OutputScopeVerdict(BaseModel):
    status: Literal["passed", "failed"] = Field(
        description="passed when the answer is supported by retrieval blocks."
    )
    unsupported_claims: list[str] = Field(
        default_factory=list,
        description="Claims in the answer that are not grounded in retrieval blocks.",
    )
    reasoning: str = Field(description="Brief explanation of the verification result.")
    confidence: Literal["high", "medium", "low"] = "medium"


@dataclass
class OutputComplianceResult:
    status: Literal["passed", "failed", "skipped"]
    unsupported_claims: list[str] = field(default_factory=list)
    reasoning: str = ""
    method: Literal["llm", "skipped"] = "llm"
    remediations: list[str] = field(default_factory=list)
    response: "AdvisorResponse | None" = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "unsupportedClaims": list(self.unsupported_claims),
            "reasoning": self.reasoning,
            "method": self.method,
            "remediations": list(self.remediations),
        }


def _question_is_hebrew(question: str) -> bool:
    return bool(HEBREW_RE.search(question))


def compact_blocks_for_verifier(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for block in blocks:
        context = str(block.get("context") or "")
        compact.append(
            {
                "source": block.get("source"),
                "intent": block.get("intent"),
                "courseId": block.get("course_id"),
                "wikiSlug": block.get("wiki_slug"),
                "context": context[:800],
                "facts": block.get("facts"),
            }
        )
    return compact[:20]


def _output_verifier_messages(
    question: str,
    answer: str,
    blocks: list[dict[str, Any]],
) -> list[Any]:
    system = SystemMessage(
        content=(
            "You are the UniPilot output compliance verifier.\n"
            "Compare the advisor answer ONLY against the supplied retrieval_blocks.\n"
            "Flag unsupported_claims when the answer states facts not present in blocks, "
            "especially eligibility, credits, prerequisites, schedules, or regulations.\n"
            "General guidance and contact suggestions are acceptable.\n"
            "Return JSON: status (passed|failed), unsupported_claims (string[]), "
            "reasoning, confidence.\n"
            "Use failed only when there are concrete unsupported factual claims."
        )
    )
    human = HumanMessage(
        content=json.dumps(
            {
                "question": question,
                "answer": answer,
                "retrieval_blocks": compact_blocks_for_verifier(blocks),
            },
            ensure_ascii=False,
        )
    )
    return [system, human]


def _remediate_semantic_failures(
    response: "AdvisorResponse",
    *,
    question: str,
    unsupported_claims: list[str],
) -> tuple["AdvisorResponse", list[str]]:
    from app.services.advisor_agent import AdvisorResponse

    remediations: list[str] = []
    confidence = _downgrade_confidence(response.confidence)
    remediations.append(f"downgraded_confidence_to_{confidence}")

    claims_preview = "; ".join(unsupported_claims[:3])
    disclaimer_en = (
        f"\n\n[Semantic compliance note: the following could not be verified against "
        f"retrieved sources: {claims_preview}. Confirm with official catalog data.]"
    )
    disclaimer_he = (
        f"\n\n[הערת אמינות סמנטית: לא ניתן לאמת מול המקורות שנשלפו: {claims_preview}. "
        f"אמתו מול נתוני הקטלוג הרשמיים.]"
    )
    answer = response.answer
    if unsupported_claims and not answer.endswith(disclaimer_en) and not answer.endswith(disclaimer_he):
        answer = answer + (disclaimer_he if _question_is_hebrew(question) else disclaimer_en)
        remediations.append("appended_semantic_compliance_disclaimer")

    contacts = list(response.contacts or [])
    contact = DEFAULT_CONTACT_HE if _question_is_hebrew(question) else DEFAULT_CONTACT_EN
    if contact not in contacts:
        contacts.append(contact)
        remediations.append("added_faculty_contact")

    return (
        AdvisorResponse(
            answer=answer,
            confidence=confidence,
            course_ids=list(response.course_ids or []),
            wiki_slugs=list(response.wiki_slugs or []),
            sources=list(response.sources or []),
            eligibility=response.eligibility,
            contacts=contacts,
        ),
        remediations,
    )


def run_output_compliance_guard(
    *,
    question: str,
    response: "AdvisorResponse",
    retrieval_blocks: list[dict[str, Any]],
    llm_factory: Callable[[], Any] | None = None,
) -> OutputComplianceResult:
    """LLM semantic verification of the synthesized answer against retrieval blocks."""
    if not retrieval_blocks:
        return OutputComplianceResult(
            status="skipped",
            reasoning="No retrieval blocks to verify against.",
            method="skipped",
            response=response,
        )

    factory = llm_factory or _build_llm
    try:
        llm = factory()
    except RuntimeError:
        return OutputComplianceResult(
            status="skipped",
            reasoning="LLM unavailable for semantic verification.",
            method="skipped",
            response=response,
        )

    messages = _output_verifier_messages(question, response.answer, retrieval_blocks)
    if _llm_base_url():
        llm = llm.bind(response_format={"type": "json_object"})
        raw = llm.invoke(messages)
        content = raw.content if isinstance(raw.content, str) else str(raw.content)
        data = _extract_json_object(content)
        verdict = OutputScopeVerdict.model_validate(data)
    else:
        structured = llm.with_structured_output(OutputScopeVerdict)
        result = structured.invoke(messages)
        verdict = (
            result
            if isinstance(result, OutputScopeVerdict)
            else OutputScopeVerdict.model_validate(result)
        )

    if verdict.status == "passed" or not verdict.unsupported_claims:
        return OutputComplianceResult(
            status="passed",
            reasoning=verdict.reasoning,
            method="llm",
            response=response,
        )

    remediated, remediations = _remediate_semantic_failures(
        response,
        question=question,
        unsupported_claims=verdict.unsupported_claims,
    )
    return OutputComplianceResult(
        status="failed",
        unsupported_claims=list(verdict.unsupported_claims),
        reasoning=verdict.reasoning,
        method="llm",
        remediations=remediations,
        response=remediated,
    )
