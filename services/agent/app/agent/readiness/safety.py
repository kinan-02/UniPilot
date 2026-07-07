"""Static safety checks for runtime readiness package (Phase 25)."""

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

_READINESS_FILES = (
    "schemas.py",
    "manifest_loader.py",
    "runtime_gate.py",
    "diagnostics.py",
    "safety.py",
)


def scan_runtime_readiness_forbidden_patterns() -> list[str]:
    package_dir = Path(__file__).resolve().parent
    violations: list[str] = []
    for name in _READINESS_FILES:
        if name == "safety.py":
            continue
        path = package_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern not in text:
                continue
            if pattern == "compile(" and "re.compile(" in text:
                continue
            if pattern == "eval(" and "evaluate_" in text:
                continue
            violations.append(f"{name}:{pattern}")
    return violations


def assert_runtime_readiness_safe() -> None:
    violations = scan_runtime_readiness_forbidden_patterns()
    if violations:
        raise RuntimeError(f"runtime_readiness_safety_violations:{', '.join(violations)}")
