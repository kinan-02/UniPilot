"""Deterministic, LLM-free reducers that keep compiled context compact (Phase 4).

Every reducer here is a pure function: same input always produces the same
output, no I/O, no randomness. This module must never import
`app.agent.reasoning` or call any LLM adapter.
"""

from __future__ import annotations

from typing import Any

_MAX_STRING_LENGTH = 4000
_MAX_LIST_LENGTH = 50
_MAX_DICT_KEYS = 60
_MAX_SANITIZE_DEPTH = 6

# Keys that look like raw driver/blob payloads rather than already-summarized
# data — dropped wherever they appear during sanitization, regardless of
# capability permissions (mirrors `context_sections.FORBIDDEN_BY_DEFAULT_CONTEXT_KEYS`
# but at the individual-field level, for values nested inside otherwise-allowed
# sections such as `agent_context_pack_summary`).
_BLOB_LIKE_KEYS = frozenset({"raw_pdf_bytes", "attachment_contents", "raw_mongo_document"})

# A small, deliberately narrow whitelist of top-level keys worth keeping from
# a full `AgentContextPack`-shaped summary — everything else (full wiki
# snippet bodies, full academic_context blobs, etc.) is dropped by default.
_AGENT_CONTEXT_PACK_SUMMARY_KEYS = (
    "intent",
    "entities",
    "validationStatus",
    "validationWarnings",
    "missingData",
    "warnings",
    "provenanceCount",
    "retrievalProfile",
)

_PROFILE_SUMMARY_KEYS = (
    "degreeProgram",
    "degreeId",
    "track",
    "catalogYear",
    "facultyId",
    "currentSemesterCode",
    "preferences",
)


def sanitize_context_value(value: Any, *, _depth: int = 0) -> Any:
    """Recursively strip binary/blob fields and cap oversized strings/collections.

    Deterministic and side-effect free. Used as the last step for every
    section the compiler includes, regardless of the section's own reducer.
    """
    if _depth >= _MAX_SANITIZE_DEPTH:
        return "<omitted: max nesting depth exceeded>"

    if isinstance(value, bytes | bytearray):
        return "<omitted: binary data>"

    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            return value[:_MAX_STRING_LENGTH] + "…<truncated>"
        return value

    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= _MAX_DICT_KEYS:
                sanitized["__truncated__"] = True
                break
            if str(key) in _BLOB_LIKE_KEYS:
                sanitized[str(key)] = "<omitted: forbidden field>"
                continue
            sanitized[str(key)] = sanitize_context_value(item, _depth=_depth + 1)
        return sanitized

    if isinstance(value, list | tuple | set):
        items = list(value)[:_MAX_LIST_LENGTH]
        sanitized_list = [sanitize_context_value(item, _depth=_depth + 1) for item in items]
        if len(value) > _MAX_LIST_LENGTH:
            sanitized_list.append(f"…<{len(value) - _MAX_LIST_LENGTH} more item(s) omitted>")
        return sanitized_list

    # Primitives (int/float/bool/None) and anything else JSON-simple pass through.
    return value


def reduce_recent_messages(
    messages: list[dict[str, Any]], max_messages: int
) -> list[dict[str, Any]]:
    """Keep only the most recent `max_messages`, sanitized."""
    capped = max(0, max_messages)
    trimmed = messages[-capped:] if capped else []
    return [sanitize_context_value(message) for message in trimmed]


def reduce_wiki_snippets(snippets: list[dict[str, Any]], max_snippets: int) -> list[dict[str, Any]]:
    """Keep only the top `max_snippets` (assumed pre-ranked by the caller)."""
    capped = max(0, max_snippets)
    return [sanitize_context_value(snippet) for snippet in snippets[:capped]]


def reduce_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Keep only the small set of profile fields workflows actually use."""
    reduced = {key: profile[key] for key in _PROFILE_SUMMARY_KEYS if key in profile}
    return sanitize_context_value(reduced)


def reduce_agent_context_pack_summary(context_pack: dict[str, Any]) -> dict[str, Any]:
    """Keep only a narrow whitelist of `AgentContextPack` summary fields."""
    reduced = {key: context_pack[key] for key in _AGENT_CONTEXT_PACK_SUMMARY_KEYS if key in context_pack}
    return sanitize_context_value(reduced)


def reduce_attachment_metadata(metadata: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only `type`/`filename`/`contentType` — never attachment contents."""
    reduced = []
    for item in metadata:
        if not isinstance(item, dict):
            continue
        reduced.append(
            {
                "type": item.get("type"),
                "filename": item.get("filename"),
                "contentType": item.get("contentType"),
            }
        )
    return reduced
