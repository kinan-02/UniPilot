"""Static safety checks for planner dynamic spec modules (Phase 20)."""

from __future__ import annotations

from pathlib import Path


def _forbidden_token(left: str, right: str = "") -> str:
    return f"{left}{right}"


_FORBIDDEN_TOKENS: tuple[str, ...] = (
    ".insert_one(",
    ".update_one(",
    ".delete_one(",
    "create_agent_action_proposal(",
    "confirm_action(",
    "reject_action(",
    "/confirm",
    "/reject",
    "exec(",
    "eval(",
    "compile(",
    _forbidden_token("chat.", "completions"),
    _forbidden_token("Chat", "OpenAI"),
    _forbidden_token("Open", "AI("),
    _forbidden_token("llm.", "invoke"),
    _forbidden_token("llm.", "ainvoke"),
)


def _contains_forbidden_token(text: str, token: str) -> bool:
    if token not in text:
        return False
    if token == "compile(":
        cleaned = text.replace("re.compile(", "")
        return "compile(" in cleaned
    return True


def scan_planner_dynamic_spec_package_for_forbidden_tokens(*, package_root: Path | None = None) -> list[str]:
    root = package_root or Path(__file__).resolve().parent
    files = (
        "dynamic_spec_policy.py",
        "dynamic_spec_diagnostics.py",
        "dynamic_spec_safety.py",
    )
    violations: list[str] = []
    for filename in files:
        path = root / filename
        if not path.exists() or path.name == "dynamic_spec_safety.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_TOKENS:
            if _contains_forbidden_token(text, token):
                violations.append(f"{path.relative_to(root)}:{token}")
    return violations
