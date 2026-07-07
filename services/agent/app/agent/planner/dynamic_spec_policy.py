"""Deterministic policy for Planner-emitted dynamic AgentSpecs (Phase 20).

Specs are configuration only — never generated code. All emitted specs must
pass Phase 15 `validate_agent_spec` before being attached to a subtask.
"""

from __future__ import annotations

import re
from typing import Any

from app.agent.dynamic_agents.block_library import build_default_block_library
from app.agent.dynamic_agents.prompt_contracts import DYNAMIC_AGENT_OUTPUT_SCHEMA_NAME
from app.agent.dynamic_agents.schemas import AgentSpec
from app.agent.dynamic_agents.spec_validation import validate_agent_spec
from app.agent.planner.schemas import PlannerOutput, PlannerSubtask
from app.agent.specialists.tools.registry import build_default_observation_registry
from app.config import Settings

_CODE_LIKE_FIELD_NAMES: frozenset[str] = frozenset(
    {
        "python_code",
        "source_code",
        "generated_code",
        "executable_code",
        "script",
        "code",
        "lambda",
    }
)
_CODE_LIKE_VALUE_PATTERN = re.compile(r"\b(def |class |import |exec\(|eval\(|__import__)\b", re.IGNORECASE)

_ALLOWED_OUTPUT_SCHEMAS: frozenset[str] = frozenset({DYNAMIC_AGENT_OUTPUT_SCHEMA_NAME, "dynamic_agent_output"})

_EXPLICIT_WRITE_PATTERN = re.compile(
    r"\b(save|commit|apply|confirm|persist|store|import|update)\b", re.IGNORECASE
)


def _looks_like_write_subtask(subtask: dict[str, Any]) -> bool:
    if str(subtask.get("kind") or "") == "propose_action":
        return True
    text = f"{subtask.get('title', '')} {subtask.get('objective', '')}"
    return bool(_EXPLICIT_WRITE_PATTERN.search(text))


def _generated_code_violations(payload: dict[str, Any]) -> list[str]:
    violations: list[str] = []
    for key, value in payload.items():
        if key in _CODE_LIKE_FIELD_NAMES:
            violations.append(f"generated_code_field:{key}")
        if isinstance(value, str) and _CODE_LIKE_VALUE_PATTERN.search(value):
            violations.append(f"generated_code_value:{key}")
        if isinstance(value, dict):
            violations.extend(_generated_code_violations(value))
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    violations.extend(_generated_code_violations(item))
    return violations


def should_allow_dynamic_spec_for_subtask(
    *,
    subtask: dict[str, Any],
    settings: Settings,
) -> bool:
    """Return whether this subtask may carry a planner-emitted dynamic spec."""
    if not settings.is_agent_planner_dynamic_specs_enabled():
        return False
    if _looks_like_write_subtask(subtask):
        return False
    if bool(subtask.get("requires_user_confirmation", False)):
        return False
    kind = str(subtask.get("kind") or "")
    if kind in {"propose_action", "compose"}:
        return False
    return True


def validate_planner_emitted_agent_spec(
    *,
    spec_payload: dict[str, Any],
    settings: Settings,
) -> tuple[AgentSpec | None, list[str]]:
    """Validate a planner-emitted spec. Never raises."""
    try:
        if not isinstance(spec_payload, dict) or not spec_payload:
            return None, ["empty_spec"]

        errors = list(_generated_code_violations(spec_payload))
        if errors:
            return None, errors

        if spec_payload.get("shadow_only") is False:
            errors.append("shadow_only_must_be_true")

        normalized = dict(spec_payload)
        normalized["shadow_only"] = True

        policy = normalized.get("validation_policy")
        if isinstance(policy, dict):
            if policy.get("allow_writes"):
                errors.append("validation_policy_allow_writes_forbidden")
            if policy.get("allow_proposed_actions"):
                errors.append("validation_policy_allow_proposed_actions_forbidden")
            policy = {**policy, "allow_writes": False, "allow_proposed_actions": False}
            normalized["validation_policy"] = policy

        pattern = str(normalized.get("reasoning_pattern") or "")
        if pattern not in settings.planner_dynamic_specs_allowed_patterns_set():
            errors.append(f"reasoning_pattern_not_allowed:{pattern}")

        risk = str(normalized.get("risk_level") or "medium")
        if risk not in settings.planner_dynamic_specs_allowed_risk_levels_set():
            errors.append(f"risk_level_not_allowed:{risk}")

        schema_name = str(normalized.get("expected_output_schema_name") or "")
        if schema_name not in _ALLOWED_OUTPUT_SCHEMAS:
            errors.append(f"unknown_output_schema:{schema_name}")

        phase15_errors = validate_agent_spec(
            normalized,
            block_library=build_default_block_library(),
            known_observation_names=set(build_default_observation_registry().list_names()),
        )
        errors.extend(phase15_errors)
        if errors:
            return None, errors

        return AgentSpec.model_validate(normalized), []
    except Exception:  # noqa: BLE001
        return None, ["spec_validation_failed"]


def normalize_planner_dynamic_specs(
    *,
    planner_output: PlannerOutput,
    settings: Settings,
) -> tuple[PlannerOutput, dict[str, Any]]:
    """Strip or validate planner dynamic specs. Returns updated plan + compact diagnostics."""
    diagnostics: dict[str, Any] = {
        "status": "skipped",
        "specsGenerated": 0,
        "specsValidated": 0,
        "specsRejected": 0,
        "specsExecuted": 0,
        "rejectionReasons": [],
        "agents": [],
        "warnings": [],
    }

    if not settings.is_agent_planner_dynamic_specs_enabled():
        stripped_subtasks: list[PlannerSubtask] = []
        for subtask in planner_output.subtasks:
            if subtask.dynamic_agent_spec is None:
                stripped_subtasks.append(subtask)
                continue
            stripped_subtasks.append(
                subtask.model_copy(
                    update={"dynamic_agent_spec": None, "dynamic_agent_spec_status": "not_requested"}
                )
            )
        if any(st.dynamic_agent_spec is not None for st in planner_output.subtasks):
            diagnostics["warnings"].append("dynamic_specs_stripped_flag_off")
        return planner_output.model_copy(update={"subtasks": stripped_subtasks}), diagnostics

    dry_run = settings.is_agent_planner_dynamic_specs_dry_run()
    if not settings.agent_planner_dynamic_specs_dry_run:
        dry_run = True
        diagnostics["warnings"].append("planner_dynamic_specs_forced_dry_run")

    max_specs = max(0, int(settings.agent_planner_dynamic_specs_max_per_plan))
    rejection_reasons: list[str] = []
    agent_summaries: list[dict[str, Any]] = []
    updated_subtasks: list[PlannerSubtask] = []
    validated_count = 0
    generated_count = 0
    rejected_count = 0

    for subtask in planner_output.subtasks:
        raw_spec = subtask.dynamic_agent_spec
        if raw_spec is None:
            updated_subtasks.append(subtask)
            continue

        generated_count += 1
        subtask_dict = subtask.model_dump()

        if not should_allow_dynamic_spec_for_subtask(subtask=subtask_dict, settings=settings):
            rejected_count += 1
            rejection_reasons.append("write_or_proposal_subtask")
            updated_subtasks.append(
                subtask.model_copy(
                    update={"dynamic_agent_spec": None, "dynamic_agent_spec_status": "rejected"}
                )
            )
            continue

        if validated_count >= max_specs:
            rejected_count += 1
            rejection_reasons.append("max_specs_per_plan_exceeded")
            updated_subtasks.append(
                subtask.model_copy(
                    update={"dynamic_agent_spec": None, "dynamic_agent_spec_status": "rejected"}
                )
            )
            continue

        spec, errors = validate_planner_emitted_agent_spec(
            spec_payload=raw_spec if isinstance(raw_spec, dict) else {},
            settings=settings,
        )
        if spec is None or errors:
            rejected_count += 1
            for error in errors[:3]:
                code = error.split(":", 1)[0]
                if code not in rejection_reasons:
                    rejection_reasons.append(code)
            updated_subtasks.append(
                subtask.model_copy(
                    update={"dynamic_agent_spec": None, "dynamic_agent_spec_status": "rejected"}
                )
            )
            continue

        validated_count += 1
        capability_name = subtask.capability_name
        if capability_name != "dynamic_agent":
            capability_name = "dynamic_agent"

        updated_subtasks.append(
            subtask.model_copy(
                update={
                    "capability_name": capability_name,
                    "dynamic_agent_spec": spec.model_dump(),
                    "dynamic_agent_spec_status": "validated",
                }
            )
        )
        agent_summaries.append(
            {
                "specId": spec.spec_id,
                "agentName": spec.agent_name,
                "reasoningPattern": spec.reasoning_pattern,
                "riskLevel": spec.risk_level,
                "status": "validated",
            }
        )

    if generated_count == 0:
        status = "skipped"
    elif validated_count == 0:
        status = "rejected"
    elif rejected_count:
        status = "completed_with_warnings"
    else:
        status = "completed"

    diagnostics.update(
        {
            "status": status,
            "specsGenerated": generated_count,
            "specsValidated": validated_count,
            "specsRejected": rejected_count,
            "rejectionReasons": rejection_reasons[:8],
            "agents": agent_summaries[:8],
            "dryRun": dry_run,
        }
    )

    warnings = list(planner_output.warnings)
    if rejected_count:
        warnings.append(f"planner_dynamic_specs_rejected:{rejected_count}")
    if validated_count:
        warnings.append(f"planner_dynamic_specs_validated:{validated_count}")

    return planner_output.model_copy(update={"subtasks": updated_subtasks, "warnings": warnings}), diagnostics
