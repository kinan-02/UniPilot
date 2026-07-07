"""Static safety scans + safety-helper unit tests for the Phase 13 bounded
specialist tool-request loop (`specialists/tools/tool_loop*.py`,
`tool_requests.py`).

Mirrors `test_specialist_observation_safety.py` (Phase 12)'s static-scan
pattern. The Phase 13 spec's own forbidden-token list includes bare
"confirm"/"reject" -- these files legitimately use "reject"/"rejected" as a
request-validation *outcome* word (`SpecialistToolRequestStatus = "rejected"`,
`rejected_observations`, `tool_request_*_rejected` warnings), a different
concept entirely from the write-action confirm/reject flow the rest of the
spec's token list guards against. This scan therefore checks for the
same *intent* using call/path-shaped tokens (`confirm_action(`, `reject_action(`,
`/confirm`, `/reject`) instead of the bare words -- exactly the style the
existing whole-`specialists`-package scan
(`test_specialist_agent_safety.py::test_static_scan_no_writes_proposals_confirm_reject_or_direct_llm_calls`)
already uses, and which still runs (recursively) over these same files.
"""

from __future__ import annotations

from pathlib import Path

from app.agent.specialists.tools.tool_loop_safety import (
    find_forbidden_argument_keys,
    has_too_many_argument_keys,
    is_requested_observation_safe,
)
from app.agent.specialists.tools.registry import ObservationDescriptor

_TOOL_LOOP_FILES: tuple[str, ...] = (
    "tool_loop.py",
    "tool_requests.py",
    "tool_loop_schemas.py",
    "tool_loop_safety.py",
    "tool_loop_diagnostics.py",
)

_FORBIDDEN_TOKENS: tuple[str, ...] = (
    ".insert_one(",
    ".update_one(",
    ".update_many(",
    ".delete_one(",
    ".delete_many(",
    "create_agent_action_proposal(",
    "confirm_action(",
    "reject_action(",
    "/confirm",
    "/reject",
    "internal_api_client",
    "chat.completions",
    "ChatOpenAI",
    "OpenAI(",
    "llm.invoke",
    "llm.ainvoke",
    "build_chat_llm(",
)

_REASONING_BLOCK_CALL_TOKENS: tuple[str, ...] = ("ReasoningBlock(", "import ReasoningBlock", "reasoning_block.run(")


def _tools_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists" / "tools"


# ---------------------------------------------------------------------------
# Static scan: no Mongo writes, no proposal creation, no confirm/reject
# action calls, no direct LLM calls anywhere in the Phase 13 tool-loop files.
# ---------------------------------------------------------------------------


def test_tool_loop_files_exist() -> None:
    tools_dir = _tools_dir()
    for filename in _TOOL_LOOP_FILES:
        assert (tools_dir / filename).is_file(), f"expected Phase 13 file missing: {filename}"


def test_tool_loop_files_contain_no_forbidden_patterns() -> None:
    tools_dir = _tools_dir()
    violations: dict[str, list[str]] = {}
    for filename in _TOOL_LOOP_FILES:
        text = (tools_dir / filename).read_text(encoding="utf-8")
        hits = [token for token in _FORBIDDEN_TOKENS if token in text]
        if hits:
            violations[filename] = hits

    assert not violations, f"Forbidden patterns found in Phase 13 tool-loop files: {violations}"


def test_tool_loop_files_never_call_reasoning_block_directly() -> None:
    """The tool loop only ever validates requests and builds observations --
    `specialists/base.py` (outside `tools/`) is the only place that re-runs
    `ReasoningBlock`."""
    tools_dir = _tools_dir()
    violations: dict[str, list[str]] = {}
    for filename in _TOOL_LOOP_FILES:
        text = (tools_dir / filename).read_text(encoding="utf-8")
        hits = [token for token in _REASONING_BLOCK_CALL_TOKENS if token in text]
        if hits:
            violations[filename] = hits

    assert not violations, f"Tool-loop files must never call ReasoningBlock directly: {violations}"


def test_tool_loop_files_never_import_llm_adapter() -> None:
    tools_dir = _tools_dir()
    for filename in _TOOL_LOOP_FILES:
        text = (tools_dir / filename).read_text(encoding="utf-8")
        assert "llm_adapter" not in text, f"{filename} must not import the LLM adapter"


def test_tool_loop_files_never_call_context_builder() -> None:
    """Core Phase 13 safety rule: the tool loop must never run the full
    context builder -- only the already-audited Phase 12 observation
    builder over already-available in-memory data."""
    tools_dir = _tools_dir()
    for filename in _TOOL_LOOP_FILES:
        text = (tools_dir / filename).read_text(encoding="utf-8")
        assert "context_builder" not in text, f"{filename} must not reference context_builder"


# ---------------------------------------------------------------------------
# `tool_loop_safety` helper unit tests.
# ---------------------------------------------------------------------------


def test_find_forbidden_argument_keys_top_level() -> None:
    assert find_forbidden_argument_keys({"raw_context": "x", "safe": 1}) == ["raw_context"]


def test_find_forbidden_argument_keys_nested() -> None:
    keys = find_forbidden_argument_keys({"outer": {"chain_of_thought": "x", "inner": {"full_catalog": []}}})
    assert "chain_of_thought" in keys
    assert "full_catalog" in keys


def test_find_forbidden_argument_keys_inside_list() -> None:
    keys = find_forbidden_argument_keys({"items": [{"transcript_rows": []}, {"safe": 1}]})
    assert keys == ["transcript_rows"]


def test_find_forbidden_argument_keys_returns_empty_for_clean_payload() -> None:
    assert find_forbidden_argument_keys({"observation_name": "profile_summary"}) == []


def test_find_forbidden_argument_keys_never_raises_on_malformed_input() -> None:
    assert find_forbidden_argument_keys(None) == []
    assert find_forbidden_argument_keys("not_a_dict") == []
    assert find_forbidden_argument_keys(12345) == []


def test_has_too_many_argument_keys() -> None:
    assert has_too_many_argument_keys({f"k{i}": i for i in range(25)}) is True
    assert has_too_many_argument_keys({"k": 1}) is False
    assert has_too_many_argument_keys("not_a_dict") is False


def test_is_requested_observation_safe_true_for_read_only_descriptor() -> None:
    descriptor = ObservationDescriptor(
        name="x", description="test", allowed_specialists=("graduation_progress_agent",), source="agent_context_pack"
    )
    assert is_requested_observation_safe(descriptor) is True


def test_is_requested_observation_safe_false_for_non_read_only_descriptor() -> None:
    descriptor = ObservationDescriptor(
        name="x",
        description="test",
        allowed_specialists=("graduation_progress_agent",),
        source="agent_context_pack",
        read_only=False,
    )
    assert is_requested_observation_safe(descriptor) is False
