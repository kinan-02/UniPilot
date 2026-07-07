"""Golden-set final answer evaluation (fact coverage against wiki ground truth)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload, sanitize_eval_payload

FactStatus = Literal["present", "partial", "missing", "contradicted"]
CaseStatus = Literal["passed", "partial", "failed", "errored"]
JudgeMode = Literal["deterministic", "llm", "hybrid"]

_COURSE_CODE_RE = re.compile(r"\b\d{8}\b")
_TRACK_SLUG_RE = re.compile(r"track-[a-z0-9-]+(?:-[a-z0-9-]+)*")
_FACULTY_SLUG_RE = re.compile(r"faculty-[a-z0-9-]+")
_CREDIT_NUMBER_RE = re.compile(r"\b(\d+(?:\.\d+)?)\b")
_GRADE_NUMBER_RE = re.compile(r"\b(\d{1,3})\b")
_HEBREW_RE = re.compile(r"[\u0590-\u05FF]+")
_OR_LOGIC_RE = re.compile(
    r"\b(?:any\s+(?:one|single)\s+condition|or[- ]conditions?|sufficient\b.*\bor\b|one of \d+)",
    re.IGNORECASE,
)
_AND_LOGIC_RE = re.compile(
    r"\b(?:all\s+(?:\d+\s+)?conditions?|must\s+meet\s+all|every\s+condition|and[- ]conditions?)\b",
    re.IGNORECASE,
)
_PREREQUISITE_RE = re.compile(r"prerequisite\s*\d*\s*:\s*(\d{8})", re.IGNORECASE)
_CONDITION_NUMBER_RE = re.compile(r"condition\s*(\d+)\s*:", re.IGNORECASE)


class GoldenAnswerCase(BaseModel):
    id: str
    query_type: str
    difficulty: str
    language: str
    user_request: str
    correct_summary: str
    key_facts: list[str]
    source_wiki_pages: list[str] = Field(default_factory=list)
    evaluation_notes: str | None = None


class FactCheckResult(BaseModel):
    fact: str
    status: FactStatus
    evidence_excerpt: str | None = None
    notes: str | None = None


class FinalAnswerCaseResult(BaseModel):
    case_id: str
    status: CaseStatus
    query_type: str
    difficulty: str
    user_request: str
    final_answer: str
    fact_results: list[FactCheckResult] = Field(default_factory=list)
    required_fact_count: int = 0
    facts_present: int = 0
    facts_partial: int = 0
    facts_missing: int = 0
    facts_contradicted: int = 0
    fact_coverage: float = 0.0
    hallucination_warnings: list[str] = Field(default_factory=list)
    source_warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class FinalAnswerEvalSummary(BaseModel):
    total_cases: int = 0
    passed_cases: int = 0
    partial_cases: int = 0
    failed_cases: int = 0
    errored_cases: int = 0
    average_fact_coverage: float = 0.0
    total_required_facts: int = 0
    total_facts_present: int = 0
    total_facts_partial: int = 0
    total_facts_missing: int = 0
    total_facts_contradicted: int = 0


class GoldenAnswerEvalSet(BaseModel):
    metadata: dict[str, Any] = Field(default_factory=dict)
    cases: list[GoldenAnswerCase]

    @model_validator(mode="after")
    def _validate_case_count(self) -> GoldenAnswerEvalSet:
        expected = self.metadata.get("case_count")
        if expected is not None and int(expected) != len(self.cases):
            raise ValueError(
                f"metadata.case_count ({expected}) does not match cases length ({len(self.cases)})"
            )
        return self


def load_golden_answer_cases(path: str | Path) -> list[GoldenAnswerCase]:
    """Load and validate the golden answer eval set JSON file."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("golden_answer_eval_set_must_be_object")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("golden_answer_eval_set_requires_non_empty_cases")

    cases: list[GoldenAnswerCase] = []
    for index, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise ValueError(f"case_{index}_must_be_object")
        case_id = str(item.get("id") or "").strip()
        if not case_id:
            raise ValueError(f"case_{index}_missing_id")
        user_request = str(item.get("user_request") or "").strip()
        if not user_request:
            raise ValueError(f"{case_id}:missing_user_request")
        correct = item.get("correct_answer")
        if not isinstance(correct, dict):
            raise ValueError(f"{case_id}:missing_correct_answer")
        summary = str(correct.get("summary") or "").strip()
        if not summary:
            raise ValueError(f"{case_id}:missing_correct_answer_summary")
        key_facts = correct.get("key_facts")
        if not isinstance(key_facts, list) or not key_facts:
            raise ValueError(f"{case_id}:key_facts_must_be_non_empty_list")
        for fact_index, fact in enumerate(key_facts):
            if not str(fact or "").strip():
                raise ValueError(f"{case_id}:key_facts[{fact_index}]_empty")

        cases.append(
            GoldenAnswerCase(
                id=case_id,
                query_type=str(item.get("query_type") or "unknown"),
                difficulty=str(item.get("difficulty") or "unknown"),
                language=str(item.get("language") or "en"),
                user_request=user_request,
                correct_summary=summary,
                key_facts=[str(fact).strip() for fact in key_facts],
                source_wiki_pages=[
                    str(page).strip()
                    for page in (correct.get("source_wiki_pages") or [])
                    if str(page).strip()
                ],
                evaluation_notes=str(item.get("evaluation_notes") or "").strip() or None,
            )
        )

    GoldenAnswerEvalSet(metadata=dict(payload.get("metadata") or {}), cases=cases)
    return cases


def normalize_eval_text(text: str) -> str:
    """Normalize answer/fact text for deterministic matching."""
    normalized = str(text or "")
    normalized = normalized.replace("\u2013", "-").replace("\u2014", "-")
    normalized = normalized.replace("\u2018", "'").replace("\u2019", "'")
    normalized = normalized.replace("\u201c", '"').replace("\u201d", '"')
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized


def normalize_eval_text_english_lower(text: str) -> str:
    """Lowercase Latin letters while preserving Hebrew segments."""
    parts: list[str] = []
    for segment in re.split(r"([\u0590-\u05FF]+)", normalize_eval_text(text)):
        if not segment:
            continue
        if _HEBREW_RE.fullmatch(segment):
            parts.append(segment)
        else:
            parts.append(segment.lower())
    return "".join(parts)


def normalize_credit_value(value: str) -> str:
    text = value.strip()
    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]
    return text


def extract_course_codes(text: str) -> list[str]:
    return _COURSE_CODE_RE.findall(text)


def extract_track_slugs(text: str) -> list[str]:
    return _TRACK_SLUG_RE.findall(text)


def extract_faculty_slugs(text: str) -> list[str]:
    return _FACULTY_SLUG_RE.findall(text)


def _extract_numbers(text: str) -> list[str]:
    return [normalize_credit_value(match) for match in _CREDIT_NUMBER_RE.findall(text)]


def _find_evidence_excerpt(answer: str, needle: str, *, max_len: int = 160) -> str | None:
    haystack = normalize_eval_text_english_lower(answer)
    target = normalize_eval_text_english_lower(needle)
    if not target:
        return None
    index = haystack.find(target)
    if index < 0:
        return None
    start = max(0, index - 40)
    end = min(len(answer), index + len(needle) + 80)
    excerpt = normalize_eval_text(answer[start:end])
    if len(excerpt) > max_len:
        excerpt = excerpt[: max_len - 3] + "..."
    return excerpt


def _bilingual_name_match(fact: str, answer: str) -> FactStatus | None:
    hebrew_segments = _HEBREW_RE.findall(fact)
    if not hebrew_segments:
        return None
    answer_norm = normalize_eval_text(answer)
    present_hebrew = [segment for segment in hebrew_segments if segment in answer_norm]
    if not present_hebrew:
        return None
    latin_words = [
        word
        for word in re.findall(r"[a-zA-Z][a-zA-Z\s\-]{2,}", fact)
        if word.strip().lower() not in {"intro", "to", "for", "the", "and", "course", "required", "track"}
    ]
    if not latin_words:
        return "partial" if present_hebrew else None
    answer_lower = normalize_eval_text_english_lower(answer)
    english_hits = sum(1 for word in latin_words if word.strip().lower() in answer_lower)
    if english_hits >= max(1, len(latin_words) // 2) and present_hebrew:
        return "present"
    return "partial"


def _check_course_code_fact(fact: str, answer: str) -> FactStatus | None:
    fact_codes = extract_course_codes(fact)
    if not fact_codes:
        return None
    answer_codes = set(extract_course_codes(answer))
    if not answer_codes:
        return "missing"
    missing = [code for code in fact_codes if code not in answer_codes]
    if missing:
        wrong_codes = answer_codes - set(fact_codes)
        if wrong_codes and any(code[:6] == fact_codes[0][:6] for code in wrong_codes):
            return "contradicted"
        return "missing"
    return "present"


def _check_track_slug_fact(fact: str, answer: str) -> FactStatus | None:
    fact_slugs = extract_track_slugs(fact)
    if not fact_slugs:
        return None
    answer_slugs = set(extract_track_slugs(answer))
    if not answer_slugs:
        return "missing"
    return "present" if all(slug in answer_slugs for slug in fact_slugs) else "missing"


def _check_credit_fact(fact: str, answer: str) -> FactStatus | None:
    fact_lower = fact.lower()
    if "credit" not in fact_lower and "credits" not in fact_lower:
        return None
    fact_numbers = _extract_numbers(fact)
    if not fact_numbers:
        return None
    answer_numbers = set(_extract_numbers(answer))
    target = fact_numbers[0]
    if target in answer_numbers:
        return "present"
    for number in answer_numbers:
        if number != target and "." in number or "." in target:
            try:
                if abs(float(number) - float(target)) < 0.01:
                    return "present"
            except ValueError:
                continue
    contradicted_numbers = [number for number in answer_numbers if number != target]
    if contradicted_numbers and any(
        keyword in fact_lower
        for keyword in ("total credits", "required courses", "faculty electives", "technion-wide")
    ):
        return "contradicted"
    return "missing"


def _check_grade_fact(fact: str, answer: str) -> FactStatus | None:
    fact_lower = fact.lower()
    if "grade" not in fact_lower and "gpa" not in fact_lower and "threshold" not in fact_lower:
        return None
    fact_numbers = _extract_numbers(fact)
    if not fact_numbers:
        return None
    answer_numbers = _extract_numbers(answer)
    target = fact_numbers[0]
    if target in answer_numbers:
        return "present"
    if "final grade" in fact_lower or "not 72" in fact_lower:
        for number in answer_numbers:
            if number != target and number in {"72", "58"}:
                return "contradicted"
    if "below 65" in fact_lower and any(number in answer_numbers for number in ("72", "80")):
        return "contradicted"
    if "below 66" in fact_lower and any(number in answer_numbers for number in ("80", "90")):
        return "contradicted"
    return "missing"


def _check_total_tracks_fact(fact: str, answer: str) -> FactStatus | None:
    match = re.search(r"total(?:\s+tracks)?\s*(?:requiring|:)?\s*(\d+)", fact, re.IGNORECASE)
    if not match:
        match = re.search(r"total:\s*(\d+)\s+tracks", fact, re.IGNORECASE)
    if not match:
        return None
    expected = match.group(1)
    answer_totals = re.findall(
        r"(?:total|requiring|required in)\s*(?:this course in)?\s*(\d+)\s+tracks?",
        answer,
        re.IGNORECASE,
    )
    if expected in answer_totals or re.search(rf"\b{expected}\s+tracks?\b", answer, re.IGNORECASE):
        return "present"
    if answer_totals and expected not in answer_totals:
        return "contradicted"
    return "missing"


def _check_or_and_logic(fact: str, answer: str) -> FactStatus | None:
    fact_lower = fact.lower()
    answer_lower = answer.lower()
    if "or-condition" in fact_lower or "any single condition" in fact_lower:
        if _AND_LOGIC_RE.search(answer_lower) and not _OR_LOGIC_RE.search(answer_lower):
            return "contradicted"
        if _OR_LOGIC_RE.search(answer_lower) or "any one" in answer_lower or "one of" in answer_lower:
            return "present"
        return "partial"
    return None


def _check_condition_fact(fact: str, answer: str) -> FactStatus | None:
    condition_match = _CONDITION_NUMBER_RE.search(fact)
    if not condition_match:
        return None
    condition_number = condition_match.group(1)
    fact_tail = fact.split(":", 1)[-1].strip().lower()
    answer_lower = normalize_eval_text_english_lower(answer)
    if not fact_tail:
        return "missing"
    keywords = [word for word in re.findall(r"[a-z]{4,}", fact_tail) if word not in {"condition", "below", "above"}]
    if not keywords:
        return "missing"
    hits = sum(1 for word in keywords[:6] if word in answer_lower)
    if hits >= max(2, len(keywords[:6]) // 2):
        return "present"
    if f"condition {condition_number}" in answer_lower:
        return "partial"
    return "missing"


def _check_prerequisite_fact(fact: str, answer: str) -> FactStatus | None:
    prereq_match = _PREREQUISITE_RE.search(fact)
    if not prereq_match:
        return None
    code = prereq_match.group(1)
    answer_codes = set(extract_course_codes(answer))
    if code in answer_codes:
        return "present"
    return "missing"


def _check_prohibition_fact(fact: str, answer: str) -> FactStatus | None:
    if not fact.lower().startswith("must not"):
        return None
    answer_lower = normalize_eval_text_english_lower(answer)
    if "eligible" in fact.lower():
        if re.search(r"\byes\s*[—\-]\s*you appear eligible\b", answer_lower):
            return "contradicted"
        if re.search(r"\byou appear eligible\b", answer_lower) and not re.search(
            r"\bnot eligible\b|\bdo not appear eligible\b|\bcannot take\b",
            answer_lower,
        ):
            return "contradicted"
        return "present"
    return None


def _check_eligibility_status_fact(fact: str, answer: str) -> FactStatus | None:
    match = re.match(r"eligibility status:\s*(.+)", fact, re.IGNORECASE)
    if not match:
        return None
    expected = match.group(1).strip().lower()
    answer_lower = normalize_eval_text_english_lower(answer)
    if expected == "not eligible":
        if re.search(r"\byes\s*[—\-]\s*you appear eligible\b", answer_lower):
            return "contradicted"
        if any(
            phrase in answer_lower
            for phrase in ("not eligible", "do not appear eligible", "cannot take")
        ):
            return "present"
        return "missing"
    if expected in {"cannot confirm", "cannot confirm eligibility", "unknown"}:
        if "cannot confirm" in answer_lower or "unavailable" in answer_lower:
            return "present"
        return "missing"
    if expected == "eligible":
        if re.search(r"\byou appear eligible\b", answer_lower):
            return "present"
        return "missing"
    return None


def _check_substring_fact(fact: str, answer: str) -> FactStatus:
    answer_norm = normalize_eval_text_english_lower(answer)
    fact_norm = normalize_eval_text_english_lower(fact)
    if fact_norm in answer_norm:
        return "present"
    tokens = [token for token in re.findall(r"[a-z0-9][a-z0-9\-.]{2,}", fact_norm) if len(token) >= 4]
    if not tokens:
        return "missing"
    hits = sum(1 for token in tokens if token in answer_norm)
    ratio = hits / len(tokens)
    if ratio >= 0.75:
        return "present"
    if ratio >= 0.4:
        return "partial"
    return "missing"


def evaluate_fact_deterministic(fact: str, answer: str) -> FactCheckResult:
    """Classify one key fact against the final answer using deterministic rules."""
    checks = (
        _check_prohibition_fact,
        _check_eligibility_status_fact,
        _check_or_and_logic,
        _check_grade_fact,
        _check_credit_fact,
        _check_course_code_fact,
        _check_prerequisite_fact,
        _check_track_slug_fact,
        _check_total_tracks_fact,
        _check_condition_fact,
    )
    status: FactStatus | None = None
    notes: str | None = None
    for checker in checks:
        result = checker(fact, answer)
        if result is not None:
            status = result
            notes = checker.__name__
            break
    if status is None:
        bilingual = _bilingual_name_match(fact, answer)
        if bilingual is not None:
            status = bilingual
            notes = "bilingual_name_match"
    if status is None:
        faculty_slugs = extract_faculty_slugs(fact)
        if faculty_slugs:
            answer_slugs = set(extract_faculty_slugs(answer))
            status = "present" if all(slug in answer_slugs for slug in faculty_slugs) else "missing"
            notes = "faculty_slug_match"
    if status is None:
        status = _check_substring_fact(fact, answer)
        notes = "substring_match"

    evidence = _find_evidence_excerpt(answer, fact.split("—")[0].split("-")[0])
    return FactCheckResult(fact=fact, status=status, evidence_excerpt=evidence, notes=notes)


def compute_fact_coverage(fact_results: list[FactCheckResult]) -> float:
    if not fact_results:
        return 0.0
    score = 0.0
    for item in fact_results:
        if item.status == "present":
            score += 1.0
        elif item.status == "partial":
            score += 0.5
    return round(score / len(fact_results), 4)


def _critical_contradiction(fact_results: list[FactCheckResult], case: GoldenAnswerCase) -> bool:
    for item in fact_results:
        if item.status != "contradicted":
            continue
        fact_lower = item.fact.lower()
        if any(
            marker in fact_lower
            for marker in (
                "final grade",
                "total credits",
                "total tracks",
                "total:",
                "or-condition",
                "course code",
            )
        ):
            return True
    notes = (case.evaluation_notes or "").lower()
    if "hard failure" in notes and any(item.status == "contradicted" for item in fact_results):
        return True
    return False


def _hard_failure_from_notes(case: GoldenAnswerCase, fact_results: list[FactCheckResult]) -> list[str]:
    failures: list[str] = []
    notes = (case.evaluation_notes or "").lower()
    contradicted = [item.fact for item in fact_results if item.status == "contradicted"]
    missing = [item.fact for item in fact_results if item.status == "missing"]

    if case.id == "case_001":
        prereq_facts = [item for item in fact_results if "prerequisite" in item.fact.lower()]
        if any(item.status == "missing" for item in prereq_facts):
            failures.append("missing_prerequisite")
    if case.id == "case_002" and contradicted:
        failures.append("wrong_final_grade")
    if case.id == "case_003":
        total_fact = next((item for item in fact_results if "total credits required" in item.fact.lower()), None)
        if total_fact and total_fact.status in {"missing", "contradicted"}:
            failures.append("wrong_total_credits")
    if case.id == "case_004" and contradicted:
        failures.append("wrong_course_or_track_set")
    if case.id == "case_005":
        condition_facts = [item for item in fact_results if item.fact.lower().startswith("condition")]
        missing_conditions = [item for item in condition_facts if item.status == "missing"]
        if len(missing_conditions) >= 4:
            failures.append("incomplete_regulation_conditions")

    if "hard failure" in notes and (contradicted or len(missing) > len(fact_results) // 2):
        failures.append("evaluation_notes_hard_failure")
    return failures


def derive_source_warnings(
    *,
    answer: str,
    used_sources: list[str] | None,
    expected_pages: list[str],
) -> list[str]:
    warnings: list[str] = []
    haystacks = [normalize_eval_text_english_lower(answer)]
    haystacks.extend(normalize_eval_text_english_lower(source) for source in (used_sources or []))
    joined = " ".join(haystacks)
    for page in expected_pages:
        slug = Path(page).stem
        fragments = [fragment for fragment in re.split(r"[/\-]", page) if len(fragment) >= 6]
        if any(fragment.lower() in joined for fragment in fragments + [slug]):
            continue
        warnings.append(f"expected_source_not_evident:{page}")
    return warnings


def score_final_answer_case(
    case: GoldenAnswerCase,
    *,
    final_answer: str,
    fact_results: list[FactCheckResult],
    used_sources: list[str] | None = None,
    hallucination_warnings: list[str] | None = None,
) -> FinalAnswerCaseResult:
    present = sum(1 for item in fact_results if item.status == "present")
    partial = sum(1 for item in fact_results if item.status == "partial")
    missing = sum(1 for item in fact_results if item.status == "missing")
    contradicted = sum(1 for item in fact_results if item.status == "contradicted")
    coverage = compute_fact_coverage(fact_results)
    source_warnings = derive_source_warnings(
        answer=final_answer,
        used_sources=used_sources,
        expected_pages=case.source_wiki_pages,
    )
    hard_failures = _hard_failure_from_notes(case, fact_results)
    failures: list[str] = list(hard_failures)
    warnings = list(hallucination_warnings or []) + source_warnings

    if _critical_contradiction(fact_results, case):
        status: CaseStatus = "failed"
        if "critical_contradiction" not in failures:
            failures.append("critical_contradiction")
    elif coverage >= 0.90 and contradicted == 0 and not hard_failures:
        status = "passed"
    elif coverage >= 0.65 and contradicted == 0:
        status = "partial"
    else:
        status = "failed"
        if coverage < 0.65 and "low_fact_coverage" not in failures:
            failures.append("low_fact_coverage")

    return FinalAnswerCaseResult(
        case_id=case.id,
        status=status,
        query_type=case.query_type,
        difficulty=case.difficulty,
        user_request=case.user_request,
        final_answer=final_answer,
        fact_results=fact_results,
        required_fact_count=len(fact_results),
        facts_present=present,
        facts_partial=partial,
        facts_missing=missing,
        facts_contradicted=contradicted,
        fact_coverage=coverage,
        hallucination_warnings=list(hallucination_warnings or []),
        source_warnings=source_warnings,
        failures=failures,
        warnings=warnings,
    )


def aggregate_final_answer_summary(results: list[FinalAnswerCaseResult]) -> FinalAnswerEvalSummary:
    if not results:
        return FinalAnswerEvalSummary()
    return FinalAnswerEvalSummary(
        total_cases=len(results),
        passed_cases=sum(1 for item in results if item.status == "passed"),
        partial_cases=sum(1 for item in results if item.status == "partial"),
        failed_cases=sum(1 for item in results if item.status == "failed"),
        errored_cases=sum(1 for item in results if item.status == "errored"),
        average_fact_coverage=round(
            sum(item.fact_coverage for item in results if item.status != "errored") / max(1, len(results)),
            4,
        ),
        total_required_facts=sum(item.required_fact_count for item in results),
        total_facts_present=sum(item.facts_present for item in results),
        total_facts_partial=sum(item.facts_partial for item in results),
        total_facts_missing=sum(item.facts_missing for item in results),
        total_facts_contradicted=sum(item.facts_contradicted for item in results),
    )


def _truncate_answer(text: str, *, include_full: bool, limit: int = 480) -> str:
    if include_full or len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def build_final_answer_eval_report(
    results: list[FinalAnswerCaseResult],
    *,
    judge_mode: JudgeMode = "deterministic",
    allow_real_llm: bool = False,
    include_full_answers: bool = False,
    agent_mode: str = "full_live",
    timings: list[Any] | None = None,
    timing_summary: dict[str, Any] | None = None,
    threshold_result: dict[str, Any] | None = None,
    wiki_cache_stats: dict[str, int] | None = None,
) -> dict[str, Any]:
    summary = aggregate_final_answer_summary(results)
    timing_by_case = {item.case_id: item for item in (timings or []) if getattr(item, "case_id", None)}
    report = {
        "evalType": "final_answer_golden_set",
        "judgeMode": judge_mode,
        "allowRealLlm": allow_real_llm,
        "agentMode": agent_mode,
        "deterministic": judge_mode == "deterministic",
        "summary": summary.model_dump(),
        "timingSummary": timing_summary or {},
        "wikiCacheStats": wiki_cache_stats or {},
        "thresholdEvaluation": threshold_result or {},
        "caseResults": [
            {
                "caseId": item.case_id,
                "status": item.status,
                "queryType": item.query_type,
                "difficulty": item.difficulty,
                "userRequest": item.user_request,
                "factCoverage": item.fact_coverage,
                "factsPresent": item.facts_present,
                "factsPartial": item.facts_partial,
                "factsMissing": item.facts_missing,
                "factsContradicted": item.facts_contradicted,
                "missingFacts": [fact.fact for fact in item.fact_results if fact.status == "missing"],
                "contradictedFacts": [
                    fact.fact for fact in item.fact_results if fact.status == "contradicted"
                ],
                "partialFacts": [fact.fact for fact in item.fact_results if fact.status == "partial"],
                "hallucinationWarnings": item.hallucination_warnings[:20],
                "sourceWarnings": item.source_warnings[:20],
                "failures": item.failures[:20],
                "warnings": item.warnings[:20],
                "finalAnswer": _truncate_answer(item.final_answer, include_full=include_full_answers),
                "factResults": [fact.model_dump() for fact in item.fact_results],
                "timing": (
                    timing_by_case[item.case_id].to_report_dict()
                    if item.case_id in timing_by_case
                    else {}
                ),
                "llmCallCount": (
                    timing_by_case[item.case_id].llm_call_count if item.case_id in timing_by_case else 0
                ),
            }
            for item in results
        ],
    }
    sanitized = sanitize_eval_payload(report, strict=False)
    assert_no_forbidden_eval_payload(sanitized if isinstance(sanitized, dict) else report)
    return sanitized if isinstance(sanitized, dict) else report


def render_final_answer_markdown_report(
    report: dict[str, Any],
    *,
    include_full_answers: bool = False,
) -> str:
    summary = report.get("summary") or {}
    lines = [
        "# UniPilot Final Answer Evaluation",
        "",
        "## Summary",
        "",
        f"- Total cases: {summary.get('total_cases', 0)}",
        f"- Passed: {summary.get('passed_cases', 0)}",
        f"- Partial: {summary.get('partial_cases', 0)}",
        f"- Failed: {summary.get('failed_cases', 0)}",
        f"- Errored: {summary.get('errored_cases', 0)}",
        f"- Average fact coverage: {summary.get('average_fact_coverage', 0)}",
        f"- Missing facts: {summary.get('total_facts_missing', 0)}",
        f"- Contradictions: {summary.get('total_facts_contradicted', 0)}",
        "",
    ]
    timing_summary = report.get("timingSummary") or {}
    if timing_summary:
        lines.extend(
            [
                "## Timing Summary",
                "",
                f"- Total run ms: {timing_summary.get('totalRunMs', 0)}",
                f"- Average case ms: {timing_summary.get('averageCaseMs', 0)}",
                f"- P50 case ms: {timing_summary.get('p50CaseMs', 0)}",
                f"- P95 case ms: {timing_summary.get('p95CaseMs', 0)}",
                f"- Total LLM calls: {timing_summary.get('totalLlmCalls', 0)}",
                f"- Total LLM ms: {timing_summary.get('totalLlmMs', 0)}",
                "",
            ]
        )
        slowest = timing_summary.get("slowestCases") or []
        if slowest:
            lines.append("Slowest cases:")
            for item in slowest:
                lines.append(
                    f"- {item.get('caseId')}: {item.get('totalMs')} ms "
                    f"(llmCalls={item.get('llmCallCount')}, slowestPhase={item.get('slowestPhase')})"
                )
            lines.append("")
    lines.extend(
        [
        "## Case Results",
        "",
        ]
    )
    for item in report.get("caseResults") or []:
        lines.extend(
            [
                f"### {item.get('caseId')}",
                "",
                f"- Query type: `{item.get('queryType')}`",
                f"- Difficulty: `{item.get('difficulty')}`",
                f"- Status: **{item.get('status')}**",
                f"- Fact coverage: {item.get('factCoverage')}",
                f"- Present / partial / missing / contradicted: "
                f"{item.get('factsPresent')} / {item.get('factsPartial')} / "
                f"{item.get('factsMissing')} / {item.get('factsContradicted')}",
                f"- User request: {item.get('userRequest')}",
                "",
            ]
        )
        missing = item.get("missingFacts") or []
        if missing:
            lines.append("Missing facts:")
            for fact in missing[:12]:
                lines.append(f"- {fact}")
            lines.append("")
        contradicted = item.get("contradictedFacts") or []
        if contradicted:
            lines.append("Contradicted facts:")
            for fact in contradicted[:12]:
                lines.append(f"- {fact}")
            lines.append("")
        answer = str(item.get("finalAnswer") or "")
        if not include_full_answers and len(answer) > 480:
            answer = answer[:477] + "..."
        lines.extend(["Final answer excerpt:", "", answer, ""])
    return "\n".join(lines).strip() + "\n"
