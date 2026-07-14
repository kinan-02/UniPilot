"""The fixed 5-role roster (docs/agent/AGENT_VISION.md §6, §6.2).

A plain dict literal at import time -- no per-request synthesis, matching
the non-generative-roster framing and the `build_default_*_registry()`
naming convention already used elsewhere in this codebase.
"""

from __future__ import annotations

from app.agent_core.planning.schemas import RoleName
from app.agent_core.roles.prompts import (
    CALCULATION_VALIDATION_AGENT_V1,
    COMPOSITION_AGENT_V1,
    INTERPRETATION_AGENT_V1,
    RETRIEVAL_AGENT_V1,
    SIMULATION_PLANNING_AGENT_V1,
)
from app.agent_core.roles.schemas import RoleDefinition, RoleReasoningDefaults


def build_default_role_roster() -> dict[RoleName, RoleDefinition]:
    return {
        "retrieval": RoleDefinition(
            name="retrieval",
            prompt_contract_name=RETRIEVAL_AGENT_V1,
            tool_grant_ceiling=(
                "get_entity",
                "search_knowledge",
                "traverse_relationship",
                # Higher-level tools (docs/agent/HIGHER_LEVEL_TOOLS.md) --
                # each bundles a multi-primitive chain (2-5 raw calls) into
                # one, collapsing what would be several LLM-decision rounds
                # into one. Built, tested, and registered since before this
                # role's ceiling was last touched, but never actually
                # granted here until now.
                "get_course_profile",
                "get_policy_answer",
                "get_track_requirements",
                # Pure, zero-cost utility (docs/agent/HIGHER_LEVEL_TOOLS.md)
                # -- the only source of "today's date" for any step that
                # needs the current/next academic semester or another
                # date-relative fact as its starting point.
                "get_current_date",
                # Bundles get_current_date with the academic calendar's own
                # date ranges (interpret_text) into one call -- no other
                # tool can compute "the current/next academic semester" at
                # all (apply_deterministic_rule has no date-range rule
                # type), which a live-eval run found causing a whole
                # nested sub-plan to fail its success-check and give up.
                "get_current_semester",
            ),
            default_reasoning_params=RoleReasoningDefaults(
                risk_level="low", min_iterations=1, max_iterations=3, temperature=0.1, timeout=60.0
            ),
            guardrails=("Return facts + source + confidence, never commentary.",),
            routing_capability=(
                "Fetches existing records and searches the knowledge base -- course/track/"
                "program/profile documents, policy pages as raw text, and the current/next "
                "academic semester. CANNOT derive or compute values (GPA, standing, credit "
                "totals) and CANNOT interpret the meaning of prose; hand those to "
                "calculation_validation and interpretation respectively."
            ),
        ),
        "interpretation": RoleDefinition(
            name="interpretation",
            prompt_contract_name=INTERPRETATION_AGENT_V1,
            tool_grant_ceiling=(
                "interpret_text",
                "get_entity",
                "search_knowledge",
                # search_knowledge -> interpret_text is interpretation's own
                # core job description; get_policy_answer already bundles
                # that exact chain (plus a built-in multi-candidate retry) in
                # one call.
                "get_policy_answer",
            ),
            default_reasoning_params=RoleReasoningDefaults(
                risk_level="medium", min_iterations=2, max_iterations=3, temperature=0.2, timeout=60.0
            ),
            guardrails=("Must cite the exact wiki page/section read.",),
            routing_capability=(
                "Reads and explains the MEANING of prose -- policy/regulation implications, "
                "and a course's or program's requirement-fulfillment status (mandatory/"
                "elective/which requirement it satisfies) that lives in requirement text. "
                "CANNOT compute numeric/boolean results; hand those to calculation_validation. "
                "Use it whenever a step needs interpretation of fetched text, not just the text."
            ),
        ),
        "calculation_validation": RoleDefinition(
            name="calculation_validation",
            prompt_contract_name=CALCULATION_VALIDATION_AGENT_V1,
            tool_grant_ceiling=("apply_deterministic_rule", "extract_temporal_pattern"),
            default_reasoning_params=RoleReasoningDefaults(
                risk_level="low", min_iterations=1, max_iterations=1, temperature=0.0, timeout=60.0
            ),
            guardrails=("Never assert a number without the tool call backing it.",),
            routing_capability=(
                "DERIVES numeric or boolean results by applying deterministic rules to "
                "already-fetched facts -- cumulative/semester GPA from raw grades, "
                "academic-standing/probation status, credit totals, threshold comparisons. "
                "CANNOT fetch records or read prose; it operates only on facts a prior "
                "retrieval step handed it, so it almost always depends on a retrieval sub-step."
            ),
        ),
        "simulation_planning": RoleDefinition(
            name="simulation_planning",
            prompt_contract_name=SIMULATION_PLANNING_AGENT_V1,
            tool_grant_ceiling=(
                "mutate_state",
                "search_over_state",
                # simulate_course_disruption is literally the fail-course-X
                # worked example (AGENT_VISION.md §10) this role exists
                # for, automated in one call instead of ~6 chained
                # mutate_state/traverse_relationship/extract_temporal_pattern/
                # search_over_state calls. The rest round out the same
                # "simulation/requirements" surface (docs/agent/
                # HIGHER_LEVEL_TOOLS.md).
                "simulate_course_disruption",
                "check_eligibility",
                "compare_plans",
                "audit_graduation_progress",
                "find_requirement_substitutes",
            ),
            default_reasoning_params=RoleReasoningDefaults(
                risk_level="medium", min_iterations=2, max_iterations=4, temperature=0.2, timeout=60.0
            ),
            guardrails=("Never present a simulated outcome as an official record.",),
            routing_capability=(
                "Runs what-if / eligibility / audit reasoning over the student's academic "
                "state via one-call composites -- fail-course-X impact, 'can I take X' "
                "prerequisite+corequisite+restriction eligibility, graduation-progress audit, "
                "plan comparison, requirement substitutes. A step that maps to one of these "
                "composites is atomic (this single specialist), not a multi-specialist pipeline."
            ),
        ),
        "composition": RoleDefinition(
            name="composition",
            prompt_contract_name=COMPOSITION_AGENT_V1,
            tool_grant_ceiling=(),
            default_reasoning_params=RoleReasoningDefaults(
                risk_level="low", min_iterations=1, max_iterations=2, temperature=0.4, timeout=60.0
            ),
            guardrails=("Zero tool access -- works only from what it's handed.",),
            routing_capability=(
                "Writes the user-facing answer from facts handed to it by earlier sub-steps. "
                "Zero tools -- it never fetches, computes, or interprets; it only phrases what "
                "it is given. Include it as the final sub-step only when a step must itself "
                "produce prose for the student rather than a fact for a later step to use."
            ),
        ),
    }


__all__ = ["build_default_role_roster"]
