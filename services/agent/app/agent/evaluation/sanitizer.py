"""Strict sanitizer for offline eval fixtures (Phase 23)."""

from __future__ import annotations

from typing import Any

_FORBIDDEN_KEYS: frozenset[str] = frozenset(
    {
        "raw_context",
        "compiled_context_raw",
        "raw_prompt",
        "system_prompt",
        "developer_prompt",
        "raw_response",
        "full_response",
        "raw_text",
        "full_text",
        "raw_blocks",
        "full_blocks",
        "proposed_action_payload",
        "transcript_rows",
        "full_transcript_rows",
        "full_catalog",
        "catalog_dump",
        "raw_pdf_bytes",
        "chain_of_thought",
        "hidden_reasoning",
        "private_reasoning",
        "scratchpad",
        "thoughts",
    }
)


def _walk(payload: Any, *, path: str = "") -> list[str]:
    violations: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_lower = str(key).lower()
            if key_lower in _FORBIDDEN_KEYS or str(key) in _FORBIDDEN_KEYS:
                violations.append(f"{path}.{key}" if path else str(key))
            violations.extend(_walk(value, path=f"{path}.{key}" if path else str(key)))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            violations.extend(_walk(item, path=f"{path}[{index}]"))
    return violations


def _strip_forbidden(payload: Any) -> tuple[Any, list[str]]:
    warnings: list[str] = []
    if isinstance(payload, dict):
        cleaned: dict[str, Any] = {}
        for key, value in payload.items():
            if str(key) in _FORBIDDEN_KEYS or str(key).lower() in _FORBIDDEN_KEYS:
                warnings.append(f"stripped:{key}")
                continue
            new_value, nested = _strip_forbidden(value)
            cleaned[key] = new_value
            warnings.extend(nested)
        return cleaned, warnings
    if isinstance(payload, list):
        items: list[Any] = []
        for item in payload:
            new_item, nested = _strip_forbidden(item)
            items.append(new_item)
            warnings.extend(nested)
        return items, warnings
    return payload, warnings


def assert_no_forbidden_eval_payload(payload: dict[str, Any]) -> None:
    violations = _walk(payload)
    if violations:
        joined = ", ".join(violations[:20])
        raise ValueError(f"forbidden_eval_payload:{joined}")


def sanitize_eval_payload(payload: dict[str, Any], *, strict: bool = True) -> dict[str, Any]:
    """Sanitize eval fixture payload. strict=True raises; strict=False strips."""
    if strict:
        assert_no_forbidden_eval_payload(payload)
        return payload
    cleaned, _warnings = _strip_forbidden(payload)
    return cleaned if isinstance(cleaned, dict) else payload
