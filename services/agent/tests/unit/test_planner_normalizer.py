"""Unit tests for the Phase 5 planner output normalizer."""

from __future__ import annotations

from app.agent.capabilities.registry import CapabilityRegistry
from app.agent.capabilities.schemas import CapabilityDescriptor
from app.agent.planner.normalizer import normalize_planner_output
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask


def _registry() -> CapabilityRegistry:
    registry = CapabilityRegistry()
    registry.register(CapabilityDescriptor(name="cap_a", type="workflow", description="a"))
    registry.register(CapabilityDescriptor(name="cap_b", type="workflow", description="b"))
    registry.register(
        CapabilityDescriptor(name="cap_disabled", type="specialist_agent", description="future", enabled=False)
    )
    return registry


def _subtask(**overrides: object) -> PlannerSubtask:
    defaults: dict[str, object] = dict(
        id="s1",
        title="Do a thing",
        kind="analyze",
        capability_name="cap_a",
        objective="Do the thing.",
        depends_on=[],
        required_context_sections=[],
        success_criteria=[],
        validation_requirements=[],
        requires_user_confirmation=False,
        risk_level="medium",
    )
    defaults.update(overrides)
    return PlannerSubtask(**defaults)


def _plan(**overrides: object) -> PlannerOutput:
    defaults: dict[str, object] = dict(
        status="completed",
        plan_id="plan-1",
        user_goal="test goal",
        execution_mode="single_capability",
        recommended_autonomy_level=3,
        primary_intent="course_question",
        subtasks=[_subtask()],
        decision_summary="test",
        confidence=0.8,
    )
    defaults.update(overrides)
    return PlannerOutput(**defaults)


def _normalize(plan: PlannerOutput, *, user_message: str = "What courses can I take?") -> PlannerOutput | None:
    return normalize_planner_output(
        plan,
        registry=_registry(),
        user_message=user_message,
        deterministic_intent="course_question",
    )


# ---------------------------------------------------------------------------
# 1. Duplicate subtask ids.
# ---------------------------------------------------------------------------


def test_duplicate_subtask_ids_are_dropped() -> None:
    plan = _plan(
        subtasks=[
            _subtask(id="dup", capability_name="cap_a"),
            _subtask(id="dup", capability_name="cap_b"),
        ]
    )
    normalized = _normalize(plan)
    assert normalized is not None
    assert [s.id for s in normalized.subtasks] == ["dup"]
    assert any("duplicate_or_missing_subtask_id_dropped" in w for w in normalized.warnings)


# ---------------------------------------------------------------------------
# 2. Unknown dependency.
# ---------------------------------------------------------------------------


def test_unknown_dependency_is_stripped_with_warning() -> None:
    plan = _plan(
        subtasks=[_subtask(id="s1", capability_name="cap_a", depends_on=["does_not_exist"])]
    )
    normalized = _normalize(plan)
    assert normalized is not None
    assert normalized.subtasks[0].depends_on == []
    assert any("invalid_dependency_dropped" in w for w in normalized.warnings)


def test_self_dependency_is_stripped() -> None:
    plan = _plan(subtasks=[_subtask(id="s1", capability_name="cap_a", depends_on=["s1"])])
    normalized = _normalize(plan)
    assert normalized is not None
    assert normalized.subtasks[0].depends_on == []


# ---------------------------------------------------------------------------
# 3. Cycle detection.
# ---------------------------------------------------------------------------


def test_dependency_cycle_causes_fallback() -> None:
    plan = _plan(
        subtasks=[
            _subtask(id="a", capability_name="cap_a", depends_on=["b"]),
            _subtask(id="b", capability_name="cap_b", depends_on=["a"]),
        ]
    )
    normalized = _normalize(plan)
    assert normalized is None


def test_valid_acyclic_dependency_chain_is_kept() -> None:
    plan = _plan(
        subtasks=[
            _subtask(id="a", capability_name="cap_a", depends_on=[]),
            _subtask(id="b", capability_name="cap_b", depends_on=["a"]),
        ]
    )
    normalized = _normalize(plan)
    assert normalized is not None
    assert len(normalized.subtasks) == 2


# ---------------------------------------------------------------------------
# 4. Invalid (hallucinated) capability.
# ---------------------------------------------------------------------------


def test_unknown_capability_subtask_is_dropped() -> None:
    plan = _plan(subtasks=[_subtask(id="s1", capability_name="capability_that_does_not_exist")])
    normalized = _normalize(plan)
    assert normalized is None  # the only subtask was invalid -> plan is unusable
    # (warnings live on the discarded candidate; verify via a mixed-subtask case below)


def test_one_invalid_capability_among_valid_ones_is_dropped_not_fatal() -> None:
    plan = _plan(
        subtasks=[
            _subtask(id="good", capability_name="cap_a"),
            _subtask(id="bad", capability_name="hallucinated_capability"),
        ]
    )
    normalized = _normalize(plan)
    assert normalized is not None
    assert [s.id for s in normalized.subtasks] == ["good"]
    assert any("unknown_capability_dropped" in w for w in normalized.warnings)


# ---------------------------------------------------------------------------
# 5. Hallucinated primary_intent falls back safely.
# ---------------------------------------------------------------------------


def test_hallucinated_primary_intent_falls_back_to_deterministic_intent() -> None:
    plan = _plan(primary_intent="not_a_real_intent")
    normalized = _normalize(plan)
    assert normalized is not None
    assert normalized.primary_intent == "course_question"
    assert any("unsupported_primary_intent_replaced" in w for w in normalized.warnings)


def test_hallucinated_primary_intent_without_deterministic_intent_falls_back_to_unknown() -> None:
    plan = _plan(primary_intent="not_a_real_intent")
    normalized = normalize_planner_output(
        plan, registry=_registry(), user_message="hello", deterministic_intent=None
    )
    assert normalized is not None
    assert normalized.primary_intent == "unknown_or_unsupported"


# ---------------------------------------------------------------------------
# 6. Invalid context sections are removed/warned.
# ---------------------------------------------------------------------------


def test_invalid_context_section_is_removed_with_warning() -> None:
    plan = _plan(
        subtasks=[
            _subtask(
                id="s1",
                capability_name="cap_a",
                required_context_sections=["user_message", "full_catalog", "not_a_real_section"],
            )
        ]
    )
    normalized = _normalize(plan)
    assert normalized is not None
    assert normalized.subtasks[0].required_context_sections == ["user_message"]
    assert any("unknown_context_section_dropped" in w for w in normalized.warnings)


# ---------------------------------------------------------------------------
# 7. Write-risk / confirmation reconciliation.
# ---------------------------------------------------------------------------


def test_propose_action_subtask_forces_confirmation_and_upgrades_write_risk() -> None:
    plan = _plan(
        subtasks=[
            _subtask(
                id="s1",
                capability_name="cap_a",
                kind="propose_action",
                requires_user_confirmation=False,
                risk_level="low",
            )
        ],
        requires_user_confirmation=False,
        write_risk="none",
    )
    normalized = _normalize(plan, user_message="just checking, nothing explicit here")
    assert normalized is not None
    assert normalized.subtasks[0].requires_user_confirmation is True
    assert normalized.subtasks[0].risk_level == "medium"
    assert normalized.requires_user_confirmation is True
    assert normalized.write_risk == "possible"


def test_explicit_write_verb_in_user_message_forces_explicit_write_risk() -> None:
    plan = _plan(requires_user_confirmation=False, write_risk="none")
    normalized = _normalize(plan, user_message="please save my semester plan now")
    assert normalized is not None
    assert normalized.requires_user_confirmation is True
    assert normalized.write_risk == "explicit"


def test_read_only_plan_keeps_no_confirmation_and_none_write_risk() -> None:
    plan = _plan(requires_user_confirmation=False, write_risk="none")
    normalized = _normalize(plan, user_message="what am I missing to graduate?")
    assert normalized is not None
    assert normalized.requires_user_confirmation is False
    assert normalized.write_risk == "none"


def test_invalid_write_risk_value_defaults_to_none_before_reconciliation() -> None:
    # `write_risk` is enum-constrained by both the Pydantic model and
    # PLANNER_OUTPUT_SCHEMA, so an invalid value can never reach the
    # normalizer through the real `ReasoningBlock` -> `_candidate_from_result`
    # path. `model_copy` bypasses validation to exercise the normalizer's
    # defense-in-depth handling directly, in case that ever changes.
    plan = _plan().model_copy(update={"write_risk": "totally_invalid"})
    normalized = _normalize(plan, user_message="what am I missing to graduate?")
    assert normalized is not None
    assert normalized.write_risk == "none"


# ---------------------------------------------------------------------------
# 8. Disabled capability policy.
# ---------------------------------------------------------------------------


def test_disabled_capability_subtask_is_dropped_deterministically() -> None:
    plan = _plan(subtasks=[_subtask(id="s1", capability_name="cap_disabled")])

    first = _normalize(plan)
    second = _normalize(plan)

    assert first is None
    assert second is None


def test_disabled_capability_among_valid_ones_is_dropped_not_fatal() -> None:
    plan = _plan(
        subtasks=[
            _subtask(id="good", capability_name="cap_a"),
            _subtask(id="future", capability_name="cap_disabled"),
        ]
    )
    normalized = _normalize(plan)
    assert normalized is not None
    assert [s.id for s in normalized.subtasks] == ["good"]
    assert any("disabled_capability_dropped" in w for w in normalized.warnings)


# ---------------------------------------------------------------------------
# Misc defensive reconciliation.
# ---------------------------------------------------------------------------


def test_invalid_execution_mode_defaults_to_unsupported() -> None:
    # Same defense-in-depth note as above: `execution_mode` is enum-constrained
    # upstream, so this bypasses validation via `model_copy` to exercise the
    # normalizer's own guard directly.
    plan = _plan().model_copy(update={"execution_mode": "not_a_real_mode"})
    normalized = _normalize(plan)
    assert normalized is not None
    assert normalized.execution_mode == "unsupported"
    assert any("invalid_execution_mode_defaulted" in w for w in normalized.warnings)


def test_invalid_autonomy_level_clamped_to_two() -> None:
    plan = _plan().model_copy(update={"recommended_autonomy_level": 99})
    normalized = _normalize(plan)
    assert normalized is not None
    assert normalized.recommended_autonomy_level == 2


def test_empty_subtasks_is_not_treated_as_a_failure() -> None:
    plan = _plan(subtasks=[], execution_mode="clarification")
    normalized = _normalize(plan)
    assert normalized is not None
    assert normalized.subtasks == []
