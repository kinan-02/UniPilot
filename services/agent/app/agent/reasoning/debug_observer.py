"""Optional eval-only debug observer for ReasoningBlock raw LLM IO."""

from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Protocol, runtime_checkable

RAW_DEBUG_WARNING = (
    "UNSAFE LOCAL DEBUG ARTIFACT.\n"
    "DO NOT COMMIT.\n"
    "DO NOT SHARE EXTERNALLY.\n"
    "May contain raw prompts, model outputs, source snippets, internal instructions, "
    "synthetic/private user data, or model/provider artifacts."
)

_eval_debug_context: ContextVar[tuple[ReasoningBlockDebugObserver | None, str, str] | None] = ContextVar(
    "eval_debug_context",
    default=None,
)


@contextmanager
def eval_debug_observer_context(
    observer: ReasoningBlockDebugObserver | None,
    *,
    case_id: str,
    phase: str,
) -> Iterator[None]:
    token = _eval_debug_context.set((observer, case_id, phase))
    try:
        yield
    finally:
        _eval_debug_context.reset(token)


def current_eval_debug_context() -> tuple[ReasoningBlockDebugObserver | None, str, str] | None:
    return _eval_debug_context.get()


_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)(api[_-]?key|authorization|bearer)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(password|secret|token)\s*[:=]\s*\S+"),
    re.compile(r"sk-[A-Za-z0-9]{10,}"),
)


@runtime_checkable
class ReasoningBlockDebugObserver(Protocol):
    """Receives raw LLM IO during eval-only debug runs."""

    def on_llm_call(
        self,
        *,
        case_id: str,
        phase: str,
        contract_name: str,
        contract_version: str,
        prompt_text: str,
        raw_model_output: str,
        parsed_json_preview: dict[str, Any] | None,
        schema_valid: bool,
        status: str,
        repair_attempted: bool,
        repair_succeeded: bool,
        fallback_used: bool,
        warnings: list[str],
        duration_ms: float | None = None,
    ) -> None:
        ...


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def redact_secrets(text: str) -> str:
    redacted = str(text or "")
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub("[REDACTED]", redacted)
    return redacted


def truncate_debug_text(text: str, *, max_chars: int) -> tuple[str, bool, int]:
    original_len = len(text or "")
    if original_len <= max_chars:
        return text or "", False, original_len
    return (text or "")[: max_chars - 3] + "...", True, original_len


@dataclass
class EvalRawLlmDebugSink:
    """Writes unsafe raw LLM debug files under trace_dir/raw_llm/<case_id>/."""

    trace_dir: Path
    case_id: str
    max_chars: int = 200_000
    files_written: list[str] = field(default_factory=list)

    def on_llm_call(
        self,
        *,
        case_id: str,
        phase: str,
        contract_name: str,
        contract_version: str,
        prompt_text: str,
        raw_model_output: str,
        parsed_json_preview: dict[str, Any] | None,
        schema_valid: bool,
        status: str,
        repair_attempted: bool,
        repair_succeeded: bool,
        fallback_used: bool,
        warnings: list[str],
        duration_ms: float | None = None,
    ) -> None:
        _ = duration_ms
        safe_prompt, prompt_truncated, prompt_len = truncate_debug_text(
            redact_secrets(prompt_text),
            max_chars=self.max_chars,
        )
        safe_raw, raw_truncated, raw_len = truncate_debug_text(
            redact_secrets(raw_model_output),
            max_chars=self.max_chars,
        )
        payload = {
            "warning": RAW_DEBUG_WARNING,
            "caseId": case_id,
            "phase": phase,
            "contractName": contract_name,
            "contractVersion": contract_version,
            "timestamp": _utc_now_iso(),
            "promptText": safe_prompt,
            "rawModelOutput": safe_raw,
            "parsedJsonPreview": parsed_json_preview or {},
            "schemaValid": schema_valid,
            "status": status,
            "repairAttempted": repair_attempted,
            "repairSucceeded": repair_succeeded,
            "fallbackUsed": fallback_used,
            "warnings": warnings[:20],
            "truncated": prompt_truncated or raw_truncated,
            "originalCharCount": {
                "promptText": prompt_len,
                "rawModelOutput": raw_len,
            },
        }
        out_dir = self.trace_dir / "raw_llm" / case_id
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{contract_name}.json"
        out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        self.files_written.append(str(out_path))
