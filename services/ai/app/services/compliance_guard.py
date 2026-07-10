"""Compliance Guard (AGT-9) — deterministic post-synthesis response verifier."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Literal

from app.schemas.advisor import UserContextPayload
from app.services.academic_graph_engine import AcademicGraphEngine

if TYPE_CHECKING:
    from app.services.advisor_agent import AdvisorResponse

COURSE_CODE_RE = re.compile(r"\d{8}")

ComplianceIssueCode = Literal[
    "unknown_course",
    "eligibility_mismatch",
    "block_contradiction",
    "credit_mismatch",
]
ComplianceSeverity = Literal["high", "medium"]
ConfidenceLevel = Literal["high", "medium", "low"]

CREDIT_CLAIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:credits?|credit\s+points?|נקודות|נ[\"']?ז)",
    re.IGNORECASE,
)
COMPLETION_CLAIM_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*%",
)
ELIGIBLE_POSITIVE_RE = re.compile(
    r"\b(eligible|you are eligible|yes, you are eligible|זכאי|אתה זכאי|את זכאית)\b",
    re.IGNORECASE,
)
ELIGIBLE_NEGATIVE_RE = re.compile(
    r"\b(not eligible|you are not eligible|no, you are not eligible|אינך זכאי|לא זכאי)\b",
    re.IGNORECASE,
)

DEFAULT_CONTACT_EN = "faculty undergraduate studies office"
DEFAULT_CONTACT_HE = "לשכת לימודי הסמכה בפקולטה"


@dataclass(frozen=True)
class ComplianceIssue:
    code: ComplianceIssueCode
    severity: ComplianceSeverity
    message: str
    course_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComplianceGuardResult:
    status: Literal["passed", "failed"]
    issues: list[ComplianceIssue] = field(default_factory=list)
    remediations: list[str] = field(default_factory=list)
    response: "AdvisorResponse | None" = None

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "issueCount": len(self.issues),
            "issues": [
                {
                    "code": issue.code,
                    "severity": issue.severity,
                    "message": issue.message,
                    "courseId": issue.course_id,
                    "details": issue.details,
                }
                for issue in self.issues
            ],
            "remediations": list(self.remediations),
        }


def _course_exists_in_graph(engine: AcademicGraphEngine, course_id: str) -> bool:
    if course_id in engine.course_catalog:
        return True
    node = engine.graph.nodes.get(course_id, {})
    return bool(node.get("name") or node.get("node_type") == "course")


def _ground_truth_eligibility_from_blocks(
    blocks: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    truth: dict[str, dict[str, Any]] = {}
    for block in blocks:
        facts = block.get("facts")
        if not isinstance(facts, dict):
            continue
        course_id = facts.get("course_id") or block.get("course_id")
        if course_id is None or "eligible" not in facts:
            continue
        truth[str(course_id)] = {
            "eligible": bool(facts.get("eligible")),
            "missing_prerequisites": list(facts.get("missing_prerequisites") or []),
            "source": block.get("source") or block.get("intent"),
        }
    return truth


def _graduation_facts_from_blocks(
    blocks: list[dict[str, Any]],
    planning_context: dict[str, Any] | None,
) -> dict[str, Any]:
    for block in blocks:
        if block.get("intent") != "graduation_progress":
            continue
        facts = block.get("facts")
        if isinstance(facts, dict) and facts:
            return facts

    envelope = planning_context or {}
    graduation = envelope.get("graduation")
    return graduation if isinstance(graduation, dict) else {}


def _collect_response_course_ids(response: "AdvisorResponse") -> list[str]:
    codes = list(response.course_ids or [])
    for match in COURSE_CODE_RE.findall(response.answer or ""):
        if match not in codes:
            codes.append(match)
    eligibility = response.eligibility or {}
    course_id = eligibility.get("course_id")
    if course_id and str(course_id) not in codes:
        codes.append(str(course_id))
    return codes


def _downgrade_confidence(confidence: ConfidenceLevel) -> ConfidenceLevel:
    if confidence == "high":
        return "medium"
    if confidence == "medium":
        return "low"
    return "low"


def _answer_claims_eligible(answer: str, course_id: str) -> bool | None:
    if course_id not in answer:
        return None
    if ELIGIBLE_NEGATIVE_RE.search(answer):
        return False
    if ELIGIBLE_POSITIVE_RE.search(answer):
        return True
    return None


def _check_unknown_courses(
    course_ids: list[str],
    engine: AcademicGraphEngine,
) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    for course_id in course_ids:
        if _course_exists_in_graph(engine, course_id):
            continue
        issues.append(
            ComplianceIssue(
                code="unknown_course",
                severity="high",
                message=f"Course {course_id} is not in the active catalog graph.",
                course_id=course_id,
            )
        )
    return issues


def _check_eligibility_consistency(
    response: "AdvisorResponse",
    *,
    ground_truth: dict[str, dict[str, Any]],
    completed_courses: list[str],
    engine: AcademicGraphEngine,
) -> list[ComplianceIssue]:
    issues: list[ComplianceIssue] = []
    checked: set[str] = set()

    eligibility = response.eligibility or {}
    response_course = eligibility.get("course_id")
    if response_course and "eligible" in eligibility:
        course_id = str(response_course)
        checked.add(course_id)
        engine_eligible, engine_missing = engine.evaluate_eligibility(
            course_id,
            completed_courses,
        )
        claimed_eligible = bool(eligibility.get("eligible"))
        if claimed_eligible != engine_eligible:
            issues.append(
                ComplianceIssue(
                    code="eligibility_mismatch",
                    severity="high",
                    message=(
                        f"Response eligibility for {course_id} does not match "
                        f"evaluate_eligibility (claimed={claimed_eligible}, engine={engine_eligible})."
                    ),
                    course_id=course_id,
                    details={
                        "claimedEligible": claimed_eligible,
                        "engineEligible": engine_eligible,
                        "engineMissingPrerequisites": engine_missing,
                    },
                )
            )

    for course_id, facts in ground_truth.items():
        if course_id in checked:
            continue
        engine_eligible, engine_missing = engine.evaluate_eligibility(
            course_id,
            completed_courses,
        )
        block_eligible = bool(facts.get("eligible"))
        if block_eligible != engine_eligible:
            issues.append(
                ComplianceIssue(
                    code="eligibility_mismatch",
                    severity="medium",
                    message=(
                        f"Retrieval block eligibility for {course_id} disagrees with "
                        f"evaluate_eligibility."
                    ),
                    course_id=course_id,
                    details={
                        "blockEligible": block_eligible,
                        "engineEligible": engine_eligible,
                        "engineMissingPrerequisites": engine_missing,
                        "blockSource": facts.get("source"),
                    },
                )
            )

    for course_id in _collect_response_course_ids(response):
        if course_id in checked or course_id not in ground_truth:
            continue
        answer_claim = _answer_claims_eligible(response.answer or "", course_id)
        if answer_claim is None:
            continue
        block_eligible = bool(ground_truth[course_id].get("eligible"))
        if answer_claim != block_eligible:
            issues.append(
                ComplianceIssue(
                    code="block_contradiction",
                    severity="high",
                    message=(
                        f"Answer text eligibility claim for {course_id} contradicts "
                        f"retrieval block facts."
                    ),
                    course_id=course_id,
                    details={
                        "answerClaimsEligible": answer_claim,
                        "blockEligible": block_eligible,
                        "blockSource": ground_truth[course_id].get("source"),
                    },
                )
            )

    return issues


def _check_credit_consistency(
    answer: str,
    graduation_facts: dict[str, Any],
) -> list[ComplianceIssue]:
    if not graduation_facts or not answer.strip():
        return []

    issues: list[ComplianceIssue] = []
    completed = graduation_facts.get("completedCredits")
    required = graduation_facts.get("totalRequiredCredits")
    remaining = graduation_facts.get("creditsRemaining")
    completion_pct = graduation_facts.get("completionPercentage")

    known_credit_values: list[float] = []
    for value in (completed, required, remaining):
        if value is not None:
            known_credit_values.append(float(value))

    if known_credit_values:
        for match in CREDIT_CLAIM_RE.finditer(answer):
            claimed = float(match.group(1))
            if any(abs(claimed - known) <= 0.5 for known in known_credit_values):
                continue
            if not re.search(
                r"completed|earned|remaining|נקודות|credits|credit",
                answer,
                re.IGNORECASE,
            ):
                continue
            issues.append(
                ComplianceIssue(
                    code="credit_mismatch",
                    severity="medium",
                    message=(
                        f"Answer cites {claimed} credits but graduation snapshot "
                        f"reports completed={completed}, required={required}, "
                        f"remaining={remaining}."
                    ),
                    details={
                        "claimedCredits": claimed,
                        "completedCredits": completed,
                        "totalRequiredCredits": required,
                        "creditsRemaining": remaining,
                    },
                )
            )
            break

    if completion_pct is not None:
        truth_pct = float(completion_pct)
        for match in COMPLETION_CLAIM_RE.finditer(answer):
            claimed_pct = float(match.group(1))
            if abs(claimed_pct - truth_pct) <= 1.0:
                continue
            issues.append(
                ComplianceIssue(
                    code="credit_mismatch",
                    severity="medium",
                    message=(
                        f"Answer cites {claimed_pct:.0f}% completion but graduation "
                        f"snapshot reports {truth_pct:.0f}%."
                    ),
                    details={
                        "claimedCompletionPercentage": claimed_pct,
                        "snapshotCompletionPercentage": truth_pct,
                    },
                )
            )
            break

    return issues


def _remediate_response(
    response: "AdvisorResponse",
    issues: list[ComplianceIssue],
    *,
    ground_truth: dict[str, dict[str, Any]],
    completed_courses: list[str],
    engine: AcademicGraphEngine,
    question: str,
) -> tuple["AdvisorResponse", list[str]]:
    from app.services.advisor_agent import AdvisorResponse
    remediations: list[str] = []
    confidence: ConfidenceLevel = response.confidence
    answer = response.answer
    contacts = list(response.contacts or [])
    eligibility = dict(response.eligibility) if response.eligibility else None
    course_ids = list(response.course_ids or [])

    high_count = sum(1 for issue in issues if issue.severity == "high")
    medium_count = sum(1 for issue in issues if issue.severity == "medium")
    downgrade_steps = high_count + (medium_count // 2)
    for _ in range(downgrade_steps):
        confidence = _downgrade_confidence(confidence)
        remediations.append(f"downgraded_confidence_to_{confidence}")

    for issue in issues:
        if issue.code != "unknown_course" or not issue.course_id:
            continue
        course_ids = [code for code in course_ids if code != issue.course_id]
        remediations.append(f"removed_unknown_course_{issue.course_id}")

    for issue in issues:
        if issue.code not in {"eligibility_mismatch", "block_contradiction"}:
            continue
        if not issue.course_id:
            continue
        engine_eligible, engine_missing = engine.evaluate_eligibility(
            issue.course_id,
            completed_courses,
        )
        eligibility = {
            "course_id": issue.course_id,
            "eligible": engine_eligible,
            "missing_prerequisites": engine_missing,
        }
        remediations.append(f"corrected_eligibility_for_{issue.course_id}")

    disclaimer_he = (
        "\n\n[הערת אמינות: חלק מהפרטים עודכנו לפי נתוני המערכת. לאימות סופי פנו ללשכת לימודי הסמכה.]"
    )
    disclaimer_en = (
        "\n\n[Compliance note: some details were adjusted to match system data. "
        "Confirm with your faculty studies office for final decisions.]"
    )
    if issues and not answer.endswith(disclaimer_en) and not answer.endswith(disclaimer_he):
        answer = answer + (disclaimer_he if _question_is_hebrew(question) else disclaimer_en)
        remediations.append("appended_compliance_disclaimer")

    contact = DEFAULT_CONTACT_HE if _question_is_hebrew(question) else DEFAULT_CONTACT_EN
    if issues and contact not in contacts:
        contacts.append(contact)
        remediations.append("added_faculty_contact")

    return (
        AdvisorResponse(
            answer=answer,
            confidence=confidence,
            course_ids=course_ids,
            wiki_slugs=list(response.wiki_slugs or []),
            sources=list(response.sources or []),
            eligibility=eligibility,
            contacts=contacts,
        ),
        remediations,
    )


def _question_is_hebrew(question: str) -> bool:
    return bool(re.search(r"[\u0590-\u05FF]", question))


def run_compliance_guard(
    *,
    question: str,
    response: "AdvisorResponse",
    retrieval_blocks: list[dict[str, Any]],
    user_context: UserContextPayload | None,
    engine: AcademicGraphEngine,
) -> ComplianceGuardResult:
    """Validate synthesized response against graph + retrieval ground truth."""
    ctx = user_context or UserContextPayload()
    completed_courses = list(ctx.completed_courses or [])
    planning_context = ctx.planning_context or {}

    ground_truth = _ground_truth_eligibility_from_blocks(retrieval_blocks)
    graduation_facts = _graduation_facts_from_blocks(retrieval_blocks, planning_context)
    course_ids = _collect_response_course_ids(response)

    issues: list[ComplianceIssue] = []
    issues.extend(_check_unknown_courses(course_ids, engine))
    issues.extend(
        _check_eligibility_consistency(
            response,
            ground_truth=ground_truth,
            completed_courses=completed_courses,
            engine=engine,
        )
    )
    issues.extend(_check_credit_consistency(response.answer or "", graduation_facts))

    if not issues:
        return ComplianceGuardResult(status="passed", issues=[], response=response)

    remediated, remediations = _remediate_response(
        response,
        issues,
        ground_truth=ground_truth,
        completed_courses=completed_courses,
        engine=engine,
        question=question,
    )
    return ComplianceGuardResult(
        status="failed",
        issues=issues,
        remediations=remediations,
        response=remediated,
    )
