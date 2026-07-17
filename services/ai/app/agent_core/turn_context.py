"""The collaborators one turn shares, as one object instead of six parameters.

`run_task_handler` took 13 parameters and `_dispatch_single_specialist` took 12.
Six of them -- `llm_adapter`, `tool_registry`, `role_roster`, `reasoning_config`,
`tool_call_cache`, `unresolvable_registry`, `replan_ledger`, `streaming_queue` --
were the same values threaded unchanged from `turn.py` down four levels, present
in every signature on the path purely so the bottom of the stack could reach
them. Adding one more turn-scoped collaborator meant editing six signatures
across three files, which is the kind of friction that gets paid by not adding
the collaborator.

Scope: this is the ORCHESTRATION SPINE's context -- `turn.py` -> `loop.py` ->
`task_handler.py`. It deliberately stops at the dispatch boundary: a subagent
block keeps its own narrow signature (a retrieval block takes the cache and the
registry it actually uses, not the `roles` and `replans` it has no business
seeing), and `_dispatch_single_specialist` unpacks the context into those.
Pushing this object into the leaves would trade a plumbing problem for an
encapsulation one.

The three registries default to a fresh instance per context rather than being
caller-supplied. `turn.py` already constructed them exactly that way, for a
reason it wrote down: one cache per turn, "never a module-level global or
caller-supplied value -- created fresh here so concurrent turns/requests can
never see each other's cached tool results." That was an invariant maintained by
a comment and a convention; here it is the default, so a caller has to opt out on
purpose (which tests do, to assert on a shared instance) rather than remember to
opt in.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Mapping

from app.agent_core.orchestrator.replan_ledger import ReplanLedger
from app.agent_core.planning.schemas import RoleName
from app.agent_core.reasoning.llm_adapter import LLMAdapter
from app.agent_core.reasoning_effort import TurnReasoningConfig
from app.agent_core.roles.schemas import RoleDefinition
from app.agent_core.tools.call_cache import ToolCallCache
from app.agent_core.tools.registry import ToolRegistry
from app.agent_core.tools.unresolvable_registry import UnresolvableEntityRegistry


@dataclass(frozen=True)
class TurnContext:
    """Everything one turn's components need from each other, minus the request.

    Frozen: the context itself is fixed for the life of the turn. The registries
    it holds are mutable by design -- they accumulate across the turn, which is
    their whole job -- and `frozen` only prevents the context being re-pointed at
    a different one halfway down the stack.

    What is NOT here: `user_goal`, `sub_asks`, `constraints`, `open_questions`,
    `implies_action_request`. Those are the request, not the wiring; they stay
    explicit parameters on `run_plan_to_completion`, where a reader can still see
    what the turn was actually asked to do.
    """

    plan_id: str
    user_id: str
    original_user_message: str
    llm: LLMAdapter
    tools: ToolRegistry
    roles: Mapping[RoleName, RoleDefinition]
    reasoning: TurnReasoningConfig | None = None
    cache: ToolCallCache = field(default_factory=ToolCallCache)
    unresolvable: UnresolvableEntityRegistry = field(default_factory=UnresolvableEntityRegistry)
    replans: ReplanLedger = field(default_factory=ReplanLedger)
    stream: asyncio.Queue[str] | None = None

    def block_id(self, *parts: str) -> str:
        """`f"{plan_id}-planner-1"` and friends, built in one place.

        Every component on the spine assembled these by hand from an f-string
        over `plan_id`, so the id scheme lived in a dozen literals across three
        files.
        """
        return "-".join((self.plan_id, *parts))


__all__ = ["TurnContext"]
