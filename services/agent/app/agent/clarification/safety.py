"""Static and runtime safety checks for clarification (Phase 17)."""

from __future__ import annotations

from pathlib import Path

from app.agent.clarification.schemas import ClarificationQuestion


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


def scan_clarification_package_for_forbidden_tokens(*, package_root: Path | None = None) -> list[str]:
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


def validate_question_safety(question: ClarificationQuestion) -> list[str]:
    """Runtime checks for a generated clarification question."""
    issues: list[str] = []
    lowered = question.prompt.lower()
    for marker in ("chain_of_thought", "hidden_reasoning", "private_reasoning", "scratchpad", "thoughts"):
        if marker in lowered:
            issues.append(f"forbidden_marker:{marker}")
    if question.need_id and question.need_id in question.prompt:
        issues.append("internal_need_id_exposed")
    if question.id and question.id in question.prompt:
        issues.append("internal_question_id_exposed")
    return issues
