"""Golden-set eval trace logging (Phase 27.0)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.agent.evaluation.final_answer_eval import FinalAnswerCaseResult, GoldenAnswerCase
from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload, sanitize_eval_payload

TraceLevel = Literal["summary", "detailed"]

_FORBIDDEN_TRACE_KEYS: frozenset[str] = frozenset(
    {
        "prompt",
        "raw_prompt",
        "prompttext",
        "rawmodeloutput",
        "raw_model_output",
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
        "system_prompt",
        "developer_prompt",
        "raw_response",
        "full_response",
        "raw_text",
        "full_text",
        "api_key",
        "authorization",
        "password",
        "token",
        "secret",
    }
)

_DEFAULT_MAX_STRING = 500
_DETAILED_MAX_STRING = 1200
_MAX_LIST_ITEMS = 24


class EvalTraceEvent(BaseModel):
    timestamp: str
    case_id: str
    phase: str
    event_type: str
    name: str | None = None
    status: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class EvalCaseTrace(BaseModel):
    case_id: str
    user_request: str
    query_type: str | None = None
    difficulty: str | None = None
    expected_source_pages: list[str] = Field(default_factory=list)
    events: list[EvalTraceEvent] = Field(default_factory=list)
    final_answer: str | None = None
    eval_status: str | None = None
    fact_coverage: float | None = None
    missing_facts: list[str] = Field(default_factory=list)
    contradicted_facts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    failures: list[str] = Field(default_factory=list)
    main_suspected_failure: str | None = None


@dataclass
class TraceConfig:
    trace_dir: Path | None = None
    level: TraceLevel = "detailed"
    include_trace_events_in_report: bool = False
    unsafe_local_raw_llm_logs: bool = False
    raw_llm_log_max_chars: int = 200_000
    trace_on_failure: bool = False
    trace_failure_dir: Path | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_allowed_debug_root(path: Path) -> bool:
    resolved = path.resolve()
    candidates = [
        Path("/tmp").resolve(),
        Path("/private/tmp").resolve(),
        Path.cwd().resolve() / "tmp",
        Path(__file__).resolve().parents[2] / "tmp",
    ]
    for root in candidates:
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    if "tmp" in resolved.parts or "final_answer_eval_traces" in resolved.parts:
        return True
    return False


def validate_trace_dir(path: str | Path) -> Path:
    resolved = Path(path).expanduser()
    if not _is_allowed_debug_root(resolved):
        raise ValueError(
            "trace_dir_must_be_under_tmp_or_gitignored_debug_directory:"
            f"{resolved}"
        )
    return resolved


def validate_unsafe_raw_llm_mode(*, trace_dir: Path | None, enabled: bool) -> None:
    if not enabled:
        return
    if trace_dir is None:
        raise ValueError("unsafe_local_raw_llm_logs_requires_trace_dir")
    if not _is_allowed_debug_root(trace_dir):
        raise ValueError("unsafe_raw_llm_logs_require_tmp_or_gitignored_debug_directory")


def _cap_string(value: Any, *, max_len: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _key_is_forbidden(key: str) -> bool:
    normalized = str(key).lower().replace("-", "_")
    if normalized in _FORBIDDEN_TRACE_KEYS:
        return True
    return any(forbidden in normalized for forbidden in ("raw_prompt", "raw_model", "chain_of_thought"))


def sanitize_trace_data(
    payload: Any,
    *,
    level: TraceLevel = "detailed",
    max_string: int | None = None,
) -> Any:
    """Sanitize trace payloads for safe sharing."""
    cap = max_string or (_DETAILED_MAX_STRING if level == "detailed" else _DEFAULT_MAX_STRING)
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if _key_is_forbidden(str(key)):
                continue
            cleaned[str(key)] = sanitize_trace_data(value, level=level, max_string=cap)
        return cleaned
    if isinstance(payload, list):
        items = [
            sanitize_trace_data(item, level=level, max_string=cap)
            for item in payload[:_MAX_LIST_ITEMS]
        ]
        if len(payload) > _MAX_LIST_ITEMS:
            items.append(f"... truncated {len(payload) - _MAX_LIST_ITEMS} items")
        return items
    if isinstance(payload, (int, float, bool)) or payload is None:
        return payload
    return _cap_string(payload, max_len=cap)


def assert_safe_trace_payload(payload: dict[str, Any]) -> None:
    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for forbidden in ("prompttext", "rawmodeloutput", "chain_of_thought", "hidden_reasoning"):
        if forbidden in serialized.replace("_", ""):
            raise ValueError(f"unsafe_trace_payload_contains:{forbidden}")


class EvalTraceCollector:
    """Collects sanitized trace events for one golden-set case."""

    def __init__(
        self,
        *,
        case: GoldenAnswerCase,
        config: TraceConfig,
    ) -> None:
        self.case = case
        self.config = config
        self.events: list[EvalTraceEvent] = []

    def add_event(
        self,
        *,
        phase: str,
        event_type: str,
        name: str | None = None,
        status: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        sanitized = sanitize_trace_data(data or {}, level=self.config.level)
        self.events.append(
            EvalTraceEvent(
                timestamp=_utc_now_iso(),
                case_id=self.case.id,
                phase=phase,
                event_type=event_type,
                name=name,
                status=status,
                data=sanitized if isinstance(sanitized, dict) else {"value": sanitized},
            )
        )

    def build_case_trace(self, result: FinalAnswerCaseResult) -> EvalCaseTrace:
        missing = [item.fact for item in result.fact_results if item.status == "missing"]
        contradicted = [item.fact for item in result.fact_results if item.status == "contradicted"]
        trace = EvalCaseTrace(
            case_id=self.case.id,
            user_request=self.case.user_request,
            query_type=self.case.query_type,
            difficulty=self.case.difficulty,
            expected_source_pages=list(self.case.source_wiki_pages),
            events=self.events,
            final_answer=result.final_answer,
            eval_status=result.status,
            fact_coverage=result.fact_coverage,
            missing_facts=missing[:30],
            contradicted_facts=contradicted[:30],
            warnings=list(result.warnings)[:30],
            failures=list(result.failures)[:30],
            main_suspected_failure=guess_main_suspected_failure(self.events, result),
        )
        return trace


def compare_expected_sources(
    *,
    expected_pages: list[str],
    retrieved_pages: list[str],
    used_pages: list[str],
) -> dict[str, Any]:
    def _norm(page: str) -> str:
        return str(page or "").strip().lower().lstrip("/")

    expected = [_norm(page) for page in expected_pages if page]
    retrieved = {_norm(page) for page in retrieved_pages if page}
    used = {_norm(page) for page in used_pages if page}

    def _matched(page: str, haystack: set[str]) -> bool:
        if page in haystack:
            return True
        slug = Path(page).stem.lower()
        return any(page in item or slug in item for item in haystack)

    missing_expected = [page for page in expected if not _matched(page, retrieved | used)]
    return {
        "expectedSourcePages": expected_pages,
        "retrievedSourcePages": sorted(retrieved_pages)[:30],
        "usedSourcePages": sorted(used_pages)[:30],
        "missingExpectedSourcePages": missing_expected,
        "expectedRetrieved": [page for page in expected if _matched(page, retrieved)],
        "expectedUsed": [page for page in expected if _matched(page, used)],
    }


def _extract_wiki_pages_from_metadata(metadata: dict[str, Any]) -> list[str]:
    pages: list[str] = []
    for key in ("retrievedWikiContext", "wikiSnippets", "wikiContext"):
        items = metadata.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                for field_name in ("path", "sourcePath", "wikiPath", "pagePath", "id"):
                    value = item.get(field_name)
                    if value:
                        pages.append(str(value))
                title = item.get("title")
                if title:
                    pages.append(str(title))
    provenance = metadata.get("provenance") or metadata.get("usedSources")
    if isinstance(provenance, list):
        pages.extend(str(item) for item in provenance)
    return pages


def guess_main_suspected_failure(
    events: list[EvalTraceEvent],
    result: FinalAnswerCaseResult,
) -> str:
    if result.status == "errored":
        return "agent_run_errored"
    if result.facts_contradicted > 0:
        return "answer_contradicted_golden_facts"
    joined = " ".join(
        f"{event.phase}:{event.event_type}:{event.name}:{json.dumps(event.data, ensure_ascii=False)}"
        for event in events
    ).lower()
    if "unknown_or_unsupported" in joined or "could not classify" in (result.final_answer or "").lower():
        return "intent_classification_or_general_fallback"
    if "eligib" in (result.final_answer or "").lower() and "prerequisite" in result.user_request.lower():
        return "routed_to_eligibility_instead_of_course_info"
    if "course was not found" in (result.final_answer or "").lower():
        return "entity_resolution_treated_track_as_course"
    if result.source_warnings:
        return "expected_wiki_sources_not_used"
    if result.fact_coverage < 0.2:
        return "thin_or_incomplete_final_answer"
    return "needs_inspection"


def build_case_trace_document(trace: EvalCaseTrace) -> dict[str, Any]:
    doc = {
        "caseId": trace.case_id,
        "userRequest": trace.user_request,
        "queryType": trace.query_type,
        "difficulty": trace.difficulty,
        "expectedSourcePages": trace.expected_source_pages,
        "events": [event.model_dump() for event in trace.events],
        "finalAnswer": trace.final_answer,
        "eval": {
            "status": trace.eval_status,
            "factCoverage": trace.fact_coverage,
            "missingFacts": trace.missing_facts,
            "contradictedFacts": trace.contradicted_facts,
            "failures": trace.failures,
            "warnings": trace.warnings,
        },
        "mainSuspectedFailure": trace.main_suspected_failure,
    }
    sanitized = sanitize_eval_payload(doc, strict=False)
    assert_safe_trace_payload(sanitized if isinstance(sanitized, dict) else doc)
    assert_no_forbidden_eval_payload(sanitized if isinstance(sanitized, dict) else doc)
    return sanitized if isinstance(sanitized, dict) else doc


def render_case_trace_markdown(trace: EvalCaseTrace) -> str:
    lines = [
        f"# Trace: {trace.case_id}",
        "",
        "## User Request",
        "",
        trace.user_request,
        "",
        "## Expected Sources",
        "",
    ]
    for page in trace.expected_source_pages:
        lines.append(f"- {page}")
    lines.append("")

    sections = {
        "task_understanding": "## Task Understanding",
        "intent": "## Intent / Classification",
        "planner": "## Planner",
        "orchestrator": "## Orchestrator / Supervisor",
        "retrieval": "## Retrieval / Context",
        "workflow": "## Workflow / Specialist Outputs",
        "synthesis": "## Synthesis / Final Answer",
        "evaluation": "## Evaluation Result",
        "firewall": "## Safety / Firewall",
    }
    rendered: set[str] = set()
    for phase, heading in sections.items():
        phase_events = [event for event in trace.events if event.phase == phase]
        if not phase_events:
            continue
        rendered.add(phase)
        lines.extend([heading, ""])
        for event in phase_events:
            lines.append(f"- **{event.event_type}** `{event.name or ''}` status={event.status or 'n/a'}")
            for key, value in (event.data or {}).items():
                if isinstance(value, list):
                    preview = ", ".join(str(item) for item in value[:12])
                    lines.append(f"  - {key}: {preview}")
                else:
                    lines.append(f"  - {key}: {value}")
        lines.append("")

    if "evaluation" not in rendered:
        lines.extend(
            [
                "## Evaluation Result",
                "",
                f"- status: {trace.eval_status}",
                f"- fact coverage: {trace.fact_coverage}",
                f"- missing facts: {len(trace.missing_facts)}",
                f"- contradicted facts: {len(trace.contradicted_facts)}",
                f"- main suspected failure: {trace.main_suspected_failure}",
                "",
            ]
        )

    if trace.final_answer:
        excerpt = trace.final_answer if len(trace.final_answer) <= 1200 else trace.final_answer[:1197] + "..."
        lines.extend(["## Final Answer", "", excerpt, ""])
    return "\n".join(lines).strip() + "\n"


def write_case_trace_files(trace: EvalCaseTrace, *, trace_dir: Path) -> None:
    trace_dir.mkdir(parents=True, exist_ok=True)
    doc = build_case_trace_document(trace)
    (trace_dir / f"{trace.case_id}.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (trace_dir / f"{trace.case_id}.md").write_text(
        render_case_trace_markdown(trace),
        encoding="utf-8",
    )
    jsonl_path = trace_dir / f"{trace.case_id}.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as handle:
        for event in trace.events:
            handle.write(json.dumps(event.model_dump(), ensure_ascii=False) + "\n")


def write_trace_index(traces: list[EvalCaseTrace], *, trace_dir: Path) -> None:
    lines = [
        "# Final Answer Eval Trace Index",
        "",
        "| Case | Status | Coverage | Main Suspected Failure | Trace |",
        "|---|---:|---:|---|---|",
    ]
    for trace in traces:
        coverage = f"{(trace.fact_coverage or 0) * 100:.1f}%"
        failure = trace.main_suspected_failure or "needs_inspection"
        lines.append(
            f"| {trace.case_id} | {trace.eval_status} | {coverage} | {failure} | {trace.case_id}.md |"
        )
    (trace_dir / "index.md").write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def compact_trace_events_for_report(events: list[EvalTraceEvent], *, limit: int = 40) -> list[dict[str, Any]]:
    compact = []
    for event in events[:limit]:
        compact.append(
            {
                "phase": event.phase,
                "eventType": event.event_type,
                "name": event.name,
                "status": event.status,
            }
        )
    return compact
