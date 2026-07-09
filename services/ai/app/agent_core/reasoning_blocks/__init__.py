"""BaseReasoningBlock hierarchy (AGENT_VISION.md §6.2).

Distinct from `app.agent_core.reasoning`, which owns the single, fixed-shape
`ReasoningBlock` mechanism every current `agent_core` caller (Planner,
step-prep, subagents, Request Understanding) still uses unchanged. This
package holds the abstract base and its future concrete per-component
shapes (single decisive call, tool loop, self-reflection, multi-persona
debate, ...) -- it depends one-way on `reasoning`'s low-level pieces
(the LLM adapter, prompt registry, schema validator/normalizer), never the
reverse.
"""

from __future__ import annotations
