"""User-facing clarification text formatting (Phase 18)."""

from __future__ import annotations

from app.agent.clarification.schemas import ClarificationQuestion


def format_user_facing_clarification_text(questions: list[ClarificationQuestion]) -> str:
    if not questions:
        return "Before I continue, I need a bit more information from you."

    if len(questions) == 1:
        question = questions[0]
        if question.options:
            lines = ["Before I continue, I need one preference from you:", ""]
            prompt = question.prompt.strip()
            if prompt:
                lines.append(prompt if prompt.endswith("?") else f"{prompt}?")
            lines.append("")
            lines.append("Should I prioritize:")
            for index, option in enumerate(question.options[:3], start=1):
                lines.append(f"{index}. {option.strip()}")
            return "\n".join(lines)
        return question.prompt.strip()

    lines = ["Before I continue, I need a few clarifications:", ""]
    for index, question in enumerate(questions[:3], start=1):
        lines.append(f"{index}. {question.prompt.strip()}")
        for option_index, option in enumerate(question.options[:3], start=1):
            lines.append(f"   {option_index}. {option.strip()}")
        lines.append("")
    return "\n".join(lines).strip()
