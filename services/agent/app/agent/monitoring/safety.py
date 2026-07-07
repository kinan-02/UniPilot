"""Static safety checks for the monitoring package (Phase 16)."""

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
    _forbidden_token("ReasoningBlock.", "run("),
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


def scan_monitoring_package_for_forbidden_tokens(*, package_root: Path | None = None) -> list[str]:
    root = package_root or Path(__file__).resolve().parent
    violations: list[str] = []
    for path in sorted(root.rglob("*.py")):
        if path.name == "safety.py":
            continue
        text = path.read_text(encoding="utf-8")
        for token in _FORBIDDEN_TOKENS:
            if _contains_forbidden_token(text, token):
                violations.append(f"{path.relative_to(root)}:{token}")
    return violations
