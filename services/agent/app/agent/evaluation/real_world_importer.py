"""Convert anonymized real-world cases into sanitized EvalCases (Phase 26)."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.agent.evaluation.real_world_anonymizer import detect_possible_private_identifiers
from app.agent.evaluation.real_world_schemas import RealWorldCaseInput, assert_no_forbidden_import_keys
from app.agent.evaluation.replay_schemas import EvalCase, EvalCaseKind, EvalExpectedOutcome
from app.agent.evaluation.sanitizer import assert_no_forbidden_eval_payload, sanitize_eval_payload

_KIND_FROM_TAG: dict[str, EvalCaseKind] = {
    "graduation": "graduation_progress",
    "graduation_progress": "graduation_progress",
    "course": "course_question",
    "course_question": "course_question",
    "requirement": "requirement_explanation",
    "requirement_explanation": "requirement_explanation",
    "semester_planning": "semester_planning",
    "transcript_import": "transcript_import",
    "profile_update": "profile_update",
    "clarification": "ambiguous_preference",
    "plan_repair": "plan_repair",
    "synthesis": "synthesis_promotion",
    "dynamic_agent": "dynamic_agent_planning",
    "unsafe_write": "unsafe_write_attempt",
    "unsupported": "unsupported_request",
}

_WORKFLOW_TO_KIND: dict[str, EvalCaseKind] = {
    "graduation_progress_workflow": "graduation_progress",
    "course_question_workflow": "course_question",
    "requirement_explanation_workflow": "requirement_explanation",
    "semester_planning_workflow": "semester_planning",
    "transcript_import_workflow": "transcript_import",
    "profile_update_workflow": "profile_update",
}


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return cleaned or "case"


def _infer_kind(case: RealWorldCaseInput) -> EvalCaseKind:
    for tag in case.tags:
        normalized = _slug(tag)
        if normalized in _KIND_FROM_TAG:
            return _KIND_FROM_TAG[normalized]
    workflow = str(case.reviewer_expected_outcome.get("expected_workflow") or case.anonymized_context.get("workflow") or "")
    if workflow in _WORKFLOW_TO_KIND:
        return _WORKFLOW_TO_KIND[workflow]
    return "unsupported_request"


def _deterministic_case_id(*, prefix: str, case: RealWorldCaseInput, index: int) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "message": case.anonymized_user_message,
                "tags": case.tags,
                "outcome": case.reviewer_expected_outcome,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:10]
    return f"{prefix}_{index:03d}_{digest}"


def convert_real_world_case_to_eval_case(
    case: RealWorldCaseInput,
    *,
    case_id: str,
) -> EvalCase:
    """Convert an anonymized real-world input into a sanitized EvalCase."""
    tags = list(case.tags)
    if "real_world_like" not in tags:
        tags.append("real_world_like")
    if case.reviewer_expected_outcome and "human_reviewed" not in tags:
        tags.append("human_reviewed")

    expected_payload = dict(case.reviewer_expected_outcome)
    expected = EvalExpectedOutcome.model_validate(expected_payload)

    compact_context = dict(case.anonymized_context)
    if case.source:
        compact_context.setdefault("source", case.source)

    eval_case = EvalCase(
        id=case_id,
        name=case_id,
        kind=_infer_kind(case),
        description=(case.expected_behavior_notes or "").strip(),
        user_message=case.anonymized_user_message.strip(),
        locale=case.original_language,
        compact_context=compact_context,
        expected=expected,
        tags=tags,
    )
    payload = eval_case.model_dump()
    sanitized = sanitize_eval_payload(payload, strict=True)
    assert_no_forbidden_eval_payload(sanitized)
    return EvalCase.model_validate(sanitized)


def load_real_world_case_inputs(path: str | Path) -> list[RealWorldCaseInput]:
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"real_world_input_not_found:{root}")

    raw_items: list[dict[str, Any]] = []
    if root.is_file():
        if root.suffix == ".jsonl":
            for line in root.read_text(encoding="utf-8").splitlines():
                stripped = line.strip()
                if stripped and not stripped.startswith("#"):
                    parsed = json.loads(stripped)
                    if isinstance(parsed, dict):
                        raw_items.append(parsed)
        else:
            data = json.loads(root.read_text(encoding="utf-8"))
            if isinstance(data, list):
                raw_items.extend(item for item in data if isinstance(item, dict))
            elif isinstance(data, dict):
                raw_items.append(data)
    elif root.is_dir():
        for file_path in sorted(root.glob("*.json")) + sorted(root.glob("*.jsonl")):
            raw_items.extend(load_real_world_case_inputs(file_path))

    cases: list[RealWorldCaseInput] = []
    for item in raw_items:
        assert_no_forbidden_import_keys(item)
        cases.append(RealWorldCaseInput.model_validate(item))
    return cases


def import_real_world_cases(
    inputs: list[RealWorldCaseInput],
    *,
    prefix: str = "real_world",
    strict: bool = True,
) -> tuple[list[EvalCase], list[str]]:
    """Convert and validate real-world inputs. Returns (cases, warnings)."""
    warnings: list[str] = []
    cases: list[EvalCase] = []
    for index, item in enumerate(inputs):
        payload = item.model_dump()
        findings = detect_possible_private_identifiers(payload)
        if findings:
            message = f"case_index_{index}:" + ",".join(findings[:10])
            if strict:
                raise ValueError(f"unsafe_identifiers:{message}")
            warnings.append(message)
        case_id = _deterministic_case_id(prefix=prefix, case=item, index=index + 1)
        cases.append(convert_real_world_case_to_eval_case(item, case_id=case_id))
    return cases, warnings


def write_eval_case_files(cases: list[EvalCase], output_dir: str | Path) -> list[Path]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for case in sorted(cases, key=lambda item: item.id):
        path = out / f"{case.id}.json"
        payload = sanitize_eval_payload(case.model_dump(), strict=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written
