"""Static safety checks for synthesis package (Phase 21)."""

from __future__ import annotations

from pathlib import Path

_FORBIDDEN_PATTERNS = (
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
    "exec(",
    "eval(",
    "compile(",
)

_SYNTHESIS_DIR = Path(__file__).resolve().parent
_LLM_ALLOWED_FILE = "synthesis_agent.py"
_EXCLUDED_FILES = frozenset({"safety.py", "promotion_safety.py"})


def scan_synthesis_package_forbidden_patterns() -> list[str]:
    violations: list[str] = []
    for path in sorted(_SYNTHESIS_DIR.glob("*.py")):
        if path.name in _EXCLUDED_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in text:
                if path.name == _LLM_ALLOWED_FILE and pattern in {"llm.invoke", "llm.ainvoke", "ChatOpenAI", "OpenAI("}:
                    continue
                if pattern == "compile(" and "re.compile(" in text:
                    continue
                violations.append(f"{path.name}:{pattern}")
        if path.name != _LLM_ALLOWED_FILE and "ReasoningBlock" in text:
            violations.append(f"{path.name}:ReasoningBlock")
    return violations


def assert_synthesis_package_safe() -> None:
    violations = scan_synthesis_package_forbidden_patterns()
    if violations:
        joined = ", ".join(violations)
        raise RuntimeError(f"synthesis_safety_violations:{joined}")
