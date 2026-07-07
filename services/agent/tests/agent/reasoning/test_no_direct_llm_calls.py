"""Guard test: no agent module bypasses the shared `ReasoningBlock` runtime.

After Phase 2, the only file under `app/agent/` allowed to make a direct LLM
completion call is `app/agent/reasoning/llm_adapter.py`. Low-level utility
modules it depends on (`llm_client.py`, `llm_json.py`) are also allowlisted
since they contain the client construction / JSON parsing helpers the
adapter reuses, not agent-facing call sites.

This is a lightweight text scan, not a full AST/call-graph analysis — it is
meant to catch accidental regressions (someone pasting a direct
`build_chat_llm(...)` + `.ainvoke(...)` block into a workflow again), not to
be a bulletproof static analyzer.
"""

from __future__ import annotations

from pathlib import Path

_AGENT_ROOT = Path(__file__).resolve().parents[3] / "app" / "agent"
_RETRIEVAL_ROOT = Path(__file__).resolve().parents[3] / "app" / "retrieval"

_ALLOWED_RELATIVE_PATHS: frozenset[str] = frozenset(
    {
        "reasoning/llm_adapter.py",
        "llm_client.py",
        "llm_json.py",
        # Phase 21 static self-scan — contains forbidden-token literals only, no calls.
        "synthesis/safety.py",
        # Phase 22 static self-scan — contains forbidden-token literals only, no calls.
        "synthesis/promotion_safety.py",
        # Phase 23 static self-scan — contains forbidden-token literals only, no calls.
        "evaluation/safety.py",
        # Phase 24 static self-scan — contains forbidden-token literals only, no calls.
        "evaluation/readiness_safety.py",
        # Phase 25 static self-scan — contains forbidden-token literals only, no calls.
        "readiness/safety.py",
    }
)

_FORBIDDEN_TOKENS: tuple[str, ...] = (
    "build_chat_llm(",
    "agent_llm_available(",
    "ChatOpenAI",
    "OpenAI(",
    "llm.invoke",
    "llm.ainvoke",
    "llm.astream",
    "chat.completions",
)


def _iter_python_files(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and path.is_file()
    )


def _scan_for_violations(files: list[Path], *, root: Path) -> dict[str, list[str]]:
    violations: dict[str, list[str]] = {}
    for path in files:
        relative = path.relative_to(root).as_posix()
        if relative in _ALLOWED_RELATIVE_PATHS:
            continue
        text = path.read_text(encoding="utf-8")
        hits = [token for token in _FORBIDDEN_TOKENS if token in text]
        if hits:
            violations[relative] = hits
    return violations


def test_no_direct_llm_calls_under_agent_package():
    files = _iter_python_files(_AGENT_ROOT)
    assert files, "expected to find agent module files to scan"

    violations = _scan_for_violations(files, root=_AGENT_ROOT)

    assert not violations, (
        "Direct LLM call sites found outside app/agent/reasoning/llm_adapter.py. "
        "Route new LLM usage through ReasoningBlock instead:\n"
        + "\n".join(f"  {path}: {tokens}" for path, tokens in sorted(violations.items()))
    )


def test_no_direct_llm_calls_under_retrieval_package():
    files = _iter_python_files(_RETRIEVAL_ROOT)
    violations = _scan_for_violations(files, root=_RETRIEVAL_ROOT)

    assert not violations, (
        "Direct LLM call sites found under app/retrieval/. Route LLM usage "
        "through ReasoningBlock instead:\n"
        + "\n".join(f"  {path}: {tokens}" for path, tokens in sorted(violations.items()))
    )


def test_allowlisted_files_still_exist():
    """Guards against the allowlist silently going stale (renamed/removed files)."""
    for relative in _ALLOWED_RELATIVE_PATHS:
        assert (_AGENT_ROOT / relative).is_file(), f"allowlisted file missing: {relative}"


def test_allowlisted_llm_adapter_still_contains_the_real_completion_call():
    """Guards against the allowlist masking a real regression: the adapter
    itself must still be the one place doing the actual LLM call/JSON parse."""
    adapter_text = (_AGENT_ROOT / "reasoning" / "llm_adapter.py").read_text(encoding="utf-8")
    assert "build_chat_llm(" in adapter_text
    assert "llm.ainvoke" in adapter_text
