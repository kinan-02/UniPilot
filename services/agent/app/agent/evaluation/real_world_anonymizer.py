"""Conservative private-identifier scanner for real-world eval imports (Phase 26)."""

from __future__ import annotations

import re
from typing import Any

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+972|0)[\s-]?(?:5\d|[23489])[\s-]?\d{3}[\s-]?\d{4}")
_ISRAELI_ID_RE = re.compile(r"\b\d{9}\b")
_LONG_NUMERIC_ID_RE = re.compile(r"\b\d{8,12}\b")
_RAW_PDF_MARKER_RE = re.compile(r"\.pdf\b|pdf_bytes|raw_pdf", re.IGNORECASE)
_TRANSCRIPT_MARKER_RE = re.compile(
    r"transcript_rows|full_transcript|raw_transcript|grade_row|semester_row",
    re.IGNORECASE,
)
_CONVERSATION_MARKER_RE = re.compile(
    r"conversation_history|raw_conversation|chat_log|message_log",
    re.IGNORECASE,
)
_FILE_PATH_RE = re.compile(r"(?:/|\\)[\w.-]+\.(?:pdf|csv|xlsx|docx)\b", re.IGNORECASE)

_EXPLICIT_NAME_KEYS = frozenset(
    {
        "full_name",
        "student_name",
        "first_name",
        "last_name",
        "name",
        "student_full_name",
    }
)


def _scan_string(value: str, *, path: str) -> list[str]:
    findings: list[str] = []
    if _EMAIL_RE.search(value):
        findings.append(f"{path}:email_pattern")
    if _PHONE_RE.search(value):
        findings.append(f"{path}:phone_pattern")
    if _ISRAELI_ID_RE.search(value):
        findings.append(f"{path}:israeli_id_pattern")
    if _LONG_NUMERIC_ID_RE.search(value):
        findings.append(f"{path}:long_numeric_id_pattern")
    if _RAW_PDF_MARKER_RE.search(value):
        findings.append(f"{path}:raw_pdf_marker")
    if _TRANSCRIPT_MARKER_RE.search(value):
        findings.append(f"{path}:transcript_marker")
    if _CONVERSATION_MARKER_RE.search(value):
        findings.append(f"{path}:conversation_marker")
    if _FILE_PATH_RE.search(value):
        findings.append(f"{path}:file_path_marker")
    return findings


def detect_possible_private_identifiers(payload: dict[str, Any]) -> list[str]:
    """Detect obvious private identifiers in an import payload. Conservative, not perfect."""
    findings: list[str] = []

    def _walk(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_str = str(key)
                lowered = key_str.lower()
                if lowered in _EXPLICIT_NAME_KEYS or key_str in _EXPLICIT_NAME_KEYS:
                    findings.append(f"{path}.{key_str}:explicit_name_key")
                _walk(nested, f"{path}.{key_str}" if path else key_str)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                _walk(item, f"{path}[{index}]")
        elif isinstance(value, str):
            findings.extend(_scan_string(value, path=path or "value"))

    _walk(payload, "")
    return sorted(set(findings))
