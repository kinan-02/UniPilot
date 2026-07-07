"""Unit tests for `app.agent.specialists.tools.safety` (Phase 12).

Includes the dedicated static source scan for the `specialists/tools/`
package (no Mongo writes, no proposal creation, no confirm/reject calls, no
direct LLM calls) mirroring the equivalent Phase 10/11 specialist scans.
"""

from __future__ import annotations

from pathlib import Path

from app.agent.specialists.tools.safety import (
    FORBIDDEN_OBSERVATION_KEYS,
    sanitize_observation_payload,
)

# ---------------------------------------------------------------------------
# 1-6. Forbidden keys are omitted, including nested occurrences.
# ---------------------------------------------------------------------------


def test_forbidden_raw_context_key_is_omitted() -> None:
    sanitized, warnings = sanitize_observation_payload({"raw_context": {"secret": "x"}, "safe": 1})

    assert "raw_context" not in sanitized
    assert sanitized == {"safe": 1}
    assert "forbidden_observation_payload_omitted:raw_context" in warnings


def test_forbidden_full_catalog_key_is_omitted() -> None:
    sanitized, warnings = sanitize_observation_payload({"full_catalog": [1, 2, 3]})

    assert "full_catalog" not in sanitized
    assert "forbidden_observation_payload_omitted:full_catalog" in warnings


def test_forbidden_transcript_rows_key_is_omitted() -> None:
    sanitized, warnings = sanitize_observation_payload({"transcript_rows": [{"course": "234123"}]})

    assert "transcript_rows" not in sanitized
    assert "forbidden_observation_payload_omitted:transcript_rows" in warnings


def test_forbidden_chain_of_thought_key_is_omitted() -> None:
    sanitized, warnings = sanitize_observation_payload({"chain_of_thought": "secret reasoning"})

    assert "chain_of_thought" not in sanitized
    assert "forbidden_observation_payload_omitted:chain_of_thought" in warnings


def test_forbidden_proposed_action_payload_is_omitted() -> None:
    sanitized, warnings = sanitize_observation_payload(
        {"proposed_action_payload": {"actionType": "save_semester_plan"}}
    )

    assert "proposed_action_payload" not in sanitized
    assert "forbidden_observation_payload_omitted:proposed_action_payload" in warnings


def test_nested_forbidden_keys_are_omitted() -> None:
    payload = {
        "outer": {
            "inner_list": [
                {"chain_of_thought": "secret"},
                {"safe_key": "value"},
            ],
            "raw_prompt": "system prompt text",
        }
    }

    sanitized, warnings = sanitize_observation_payload(payload)

    assert "chain_of_thought" not in sanitized["outer"]["inner_list"][0]
    assert sanitized["outer"]["inner_list"][1] == {"safe_key": "value"}
    assert "raw_prompt" not in sanitized["outer"]
    assert any(w.startswith("forbidden_observation_payload_omitted:chain_of_thought") for w in warnings)
    assert any(w.startswith("forbidden_observation_payload_omitted:raw_prompt") for w in warnings)


# ---------------------------------------------------------------------------
# 7. Warnings are produced for omissions (already covered above) plus a
# no-warnings-when-clean case.
# ---------------------------------------------------------------------------


def test_no_warnings_when_payload_is_already_clean() -> None:
    sanitized, warnings = sanitize_observation_payload({"degreeProgram": "BSc", "creditsRemaining": 40})

    assert sanitized == {"degreeProgram": "BSc", "creditsRemaining": 40}
    assert warnings == []


# ---------------------------------------------------------------------------
# 8. Sanitized observation contains no forbidden keys, exhaustively.
# ---------------------------------------------------------------------------


def test_sanitized_observation_contains_no_forbidden_keys_exhaustively() -> None:
    payload = {key: f"value-for-{key}" for key in FORBIDDEN_OBSERVATION_KEYS}
    payload["safe_key"] = "kept"

    sanitized, warnings = sanitize_observation_payload(payload)

    assert set(sanitized) == {"safe_key"}
    assert len(warnings) == len(FORBIDDEN_OBSERVATION_KEYS)


def test_extra_forbidden_keys_are_also_omitted() -> None:
    sanitized, warnings = sanitize_observation_payload(
        {"content": "full wiki page body", "preview": "short"}, extra_forbidden_keys=frozenset({"content"})
    )

    assert "content" not in sanitized
    assert sanitized == {"preview": "short"}
    assert "forbidden_observation_payload_omitted:content" in warnings


def test_sanitize_never_raises_on_malformed_input() -> None:
    sanitized, warnings = sanitize_observation_payload(None)  # type: ignore[arg-type]
    assert sanitized == {}
    assert warnings == []

    sanitized_list, _ = sanitize_observation_payload(["not", "a", "dict"])  # type: ignore[arg-type]
    assert sanitized_list == {}


# ---------------------------------------------------------------------------
# Static safety scan: no Mongo writes, no proposal creation, no
# confirm/reject calls, no direct LLM calls anywhere in `specialists/tools/`.
# ---------------------------------------------------------------------------

_FORBIDDEN_TOKENS: tuple[str, ...] = (
    ".insert_one(",
    ".update_one(",
    ".delete_one(",
    "create_agent_action_proposal(",
    "confirm",
    "reject",
    "chat.completions",
    "ChatOpenAI",
    "OpenAI(",
    "llm.invoke",
    "llm.ainvoke",
)

# Phase 13's own tool-request validation files (`tool_loop.py`, `tool_requests.py`,
# `tool_loop_schemas.py`, `tool_loop_safety.py`, `tool_loop_diagnostics.py`) legitimately
# use "reject"/"rejected" as a request-validation *outcome* word (`SpecialistToolRequestStatus
# = "rejected"`, `rejected_observations`, etc.) -- a different concept from the write-action
# confirm/reject flow the bare-word tokens above guard against for the older Phase 12 files.
# These files are scanned with the same call/path-shaped tokens the whole-package scan in
# `test_specialist_agent_safety.py` already uses instead (`confirm_action(`/`reject_action(`/
# `/confirm`/`/reject`), which still catch a real write-action confirm/reject call site.
_PHASE_13_TOOL_LOOP_FILES: frozenset[str] = frozenset(
    {
        "tool_loop.py",
        "tool_requests.py",
        "tool_loop_schemas.py",
        "tool_loop_safety.py",
        "tool_loop_diagnostics.py",
    }
)
_PHASE_13_FORBIDDEN_TOKENS: tuple[str, ...] = (
    ".insert_one(",
    ".update_one(",
    ".delete_one(",
    "create_agent_action_proposal(",
    "confirm_action(",
    "reject_action(",
    "/confirm",
    "/reject",
    "chat.completions",
    "ChatOpenAI",
    "OpenAI(",
    "llm.invoke",
    "llm.ainvoke",
)


def test_static_scan_specialist_tools_package_has_no_forbidden_patterns() -> None:
    tools_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists" / "tools"
    assert tools_dir.is_dir()

    violations: dict[str, list[str]] = {}
    for path in tools_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        tokens = _PHASE_13_FORBIDDEN_TOKENS if path.name in _PHASE_13_TOOL_LOOP_FILES else _FORBIDDEN_TOKENS
        hits = [token for token in tokens if token in text]
        if hits:
            violations[path.name] = hits

    assert not violations, f"Forbidden patterns found in specialists/tools/: {violations}"


def test_specialist_tools_package_never_instantiates_or_calls_reasoning_block() -> None:
    """The observation layer must never call an LLM or `ReasoningBlock` --
    only the specialist agents themselves do, after receiving observations.
    (Docstrings are allowed to *mention* `ReasoningBlock` in prose explaining
    this constraint -- this checks for actual construction/call sites.)"""
    tools_dir = Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists" / "tools"
    forbidden_call_sites = ("ReasoningBlock(", "import ReasoningBlock", "reasoning_block.run(")
    for path in tools_dir.glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for token in forbidden_call_sites:
            assert token not in text, f"{path.name} must not contain {token!r}"
