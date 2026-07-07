"""Static safety checks for synthesis promotion modules (Phase 22)."""

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

_PROMOTION_FILES = (
    "promotion_schemas.py",
    "promotion_policy.py",
    "candidate_safety.py",
    "live_compare.py",
    "response_builder.py",
    "promotion_diagnostics.py",
    "promotion_safety.py",
)


def scan_synthesis_promotion_forbidden_patterns() -> list[str]:
    synthesis_dir = Path(__file__).resolve().parent
    violations: list[str] = []
    for name in _PROMOTION_FILES:
        if name == "promotion_safety.py":
            continue
        path = synthesis_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern in text:
                if pattern == "compile(" and "re.compile(" in text:
                    continue
                violations.append(f"{name}:{pattern}")
    return violations


def assert_synthesis_promotion_safe() -> None:
    violations = scan_synthesis_promotion_forbidden_patterns()
    if violations:
        raise RuntimeError(f"synthesis_promotion_safety_violations:{', '.join(violations)}")
