"""Static safety checks for readiness evaluation modules (Phase 24)."""

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
    "suite_schemas.py",
    "suite_loader.py",
    "readiness_schemas.py",
    "readiness_policy.py",
    "readiness_scorecard.py",
    "readiness_reporting.py",
    "policy_hardening.py",
    "readiness_safety.py",
)


def scan_readiness_forbidden_patterns() -> list[str]:
    eval_dir = Path(__file__).resolve().parent
    violations: list[str] = []
    for name in _READINESS_FILES:
        if name == "readiness_safety.py":
            continue
        path = eval_dir / name
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern not in text:
                continue
            if pattern == "compile(" and "re.compile(" in text:
                continue
            if pattern == "eval(" and ("evaluate_" in text or "readiness" in name):
                continue
            violations.append(f"{name}:{pattern}")
    return violations


def assert_readiness_eval_safe() -> None:
    violations = scan_readiness_forbidden_patterns()
    if violations:
        raise RuntimeError(f"readiness_eval_safety_violations:{', '.join(violations)}")
