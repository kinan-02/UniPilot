"""Static safety scan for the Phase 14 Controlled Specialist Text Promotion files.

Mirrors `test_specialist_tool_loop_safety.py` (Phase 13)'s scan style: the
Phase 14 spec's own forbidden-token list includes bare "confirm"/"reject",
but `SpecialistTextPromotionStatus`/reason codes legitimately use "reject"-
free vocabulary already (this phase's own status/reason codes never contain
either word) -- still, call/path-shaped tokens are used here (rather than
bare words) for consistency with the whole-package scan
(`test_specialist_agent_safety.py`) and to stay robust against future
additions to this phase's vocabulary.
"""

from __future__ import annotations

from pathlib import Path

_TEXT_PROMOTION_FILES: tuple[str, ...] = (
    "text_promotion.py",
    "text_promotion_schemas.py",
    "text_promotion_diagnostics.py",
    "answer_text_safety.py",
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


def _specialists_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "app" / "agent" / "specialists"


def test_text_promotion_files_exist() -> None:
    specialists_dir = _specialists_dir()
    for filename in _TEXT_PROMOTION_FILES:
        assert (specialists_dir / filename).is_file(), f"expected Phase 14 file missing: {filename}"


def test_text_promotion_files_contain_no_forbidden_patterns() -> None:
    specialists_dir = _specialists_dir()
    violations: dict[str, list[str]] = {}
    for filename in _TEXT_PROMOTION_FILES:
        text = (specialists_dir / filename).read_text(encoding="utf-8")
        hits = [token for token in _FORBIDDEN_TOKENS if token in text]
        if hits:
            violations[filename] = hits

    assert not violations, f"Forbidden patterns found in Phase 14 text-promotion files: {violations}"


def test_text_promotion_files_never_call_reasoning_block_directly() -> None:
    """`text_promotion.py`/`answer_text_safety.py` only ever consume
    already-computed compact summaries/decisions -- the specialist's own
    `ReasoningBlock` output is produced elsewhere (`specialists/base.py`),
    never re-invoked here."""
    specialists_dir = _specialists_dir()
    violations: dict[str, list[str]] = {}
    for filename in _TEXT_PROMOTION_FILES:
        text = (specialists_dir / filename).read_text(encoding="utf-8")
        hits = [token for token in _REASONING_BLOCK_CALL_TOKENS if token in text]
        if hits:
            violations[filename] = hits

    assert not violations, f"Text-promotion files must never call ReasoningBlock directly: {violations}"


def test_text_promotion_files_never_import_llm_adapter() -> None:
    specialists_dir = _specialists_dir()
    for filename in _TEXT_PROMOTION_FILES:
        text = (specialists_dir / filename).read_text(encoding="utf-8")
        assert "llm_adapter" not in text, f"{filename} must not import the LLM adapter"


def test_text_promotion_files_never_reference_context_builder() -> None:
    specialists_dir = _specialists_dir()
    for filename in _TEXT_PROMOTION_FILES:
        text = (specialists_dir / filename).read_text(encoding="utf-8")
        assert "context_builder" not in text, f"{filename} must not reference context_builder"
