"""`prompt_builder` (docs/agent/AGENT_VISION.md §7, §7.1).

A pure rendering function, not a second LLM decision -- the orchestrator's
step-prep pass produces `StepInstructionFields` once; this deterministically
renders those same fields into prose. If the LLM instead separately "wrote a
prompt" and separately "filled in context," the two could quietly drift
apart, defeating the anchor property §7.1 relies on.
"""

from __future__ import annotations

from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.subagents.schemas import StepInstructionFields


def render_subagent_prompt(fields: StepInstructionFields, role: RoleDefinition) -> str:
    lines = [f"Role: {role.name}", f"Goal: {fields.goal}", "", fields.description]
    if fields.specific_instructions:
        lines.append("")
        lines.append("Specific instructions:")
        lines.extend(f"- {instruction}" for instruction in fields.specific_instructions)
    if fields.tone_language_notes:
        lines.append("")
        lines.append(f"Tone/language: {fields.tone_language_notes}")
    return "\n".join(lines)


__all__ = ["render_subagent_prompt"]
