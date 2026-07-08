"""Agent service configuration.

This service has its own direct MongoDB connection for read-only lookups on
shared academic/student collections (see `app/db/mongo.py`,
`app/repositories/`) and full read/write access to its own collections
(`agent_conversations`, `agent_messages`, `agent_runs`, `agent_steps`,
`agent_tool_calls`, `agent_action_proposals`). It never writes to
student-owned collections directly — those writes stay exclusively in `api`,
executed via the existing action confirm/reject flow.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_APP_ROOT = Path(__file__).resolve().parents[1]


def _resolve_repo_root() -> Path:
    config_path = Path(__file__).resolve()
    for parent in config_path.parents:
        if (parent / "docker-compose.yml").is_file():
            return parent
    return config_path.parents[1]


def _settings_env_files() -> tuple[str, ...]:
    repo_root = _resolve_repo_root()
    app_root = Path(__file__).resolve().parents[1]
    paths: list[str] = []
    for candidate in (repo_root / ".env", app_root / ".env", Path.cwd() / ".env"):
        if candidate.is_file():
            resolved = str(candidate.resolve())
            if resolved not in paths:
                paths.append(resolved)
    return tuple(paths) if paths else (".env",)


class Settings(BaseSettings):
    service_name: str = "agent"
    environment: str = "development"
    agent_service_port: int = 3003

    mongo_uri: str | None = None
    internal_service_token: str | None = None
    bcrypt_salt_rounds: int = 12

    api_service_url: str | None = None
    internal_api_timeout_seconds: int = 60

    agent_conversations_collection: str = "agent_conversations"
    agent_messages_collection: str = "agent_messages"
    agent_runs_collection: str = "agent_runs"
    agent_steps_collection: str = "agent_steps"
    agent_tool_calls_collection: str = "agent_tool_calls"
    agent_action_proposals_collection: str = "agent_action_proposals"
    agent_clarification_states_collection: str = "agent_clarification_states"

    courses_collection: str = "courses"
    course_offerings_collection: str = "course_offerings"
    degree_programs_collection: str = "degree_programs"
    degree_requirements_collection: str = "degree_requirements"
    catalog_rules_collection: str = "catalog_rules"
    catalog_path_options_collection: str = "catalog_path_options"
    catalog_faculties_collection: str = "catalog_faculties"
    completed_courses_collection: str = "completed_courses"
    semester_plans_collection: str = "semester_plans"

    agent_max_retrieval_attempts: int = 3
    agent_max_tool_calls_per_run: int = 12
    agent_max_workflow_steps: int = 20
    agent_agentic_retrieval_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_AGENTIC_RETRIEVAL_ENABLED",
    )
    agent_llm_validation_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_LLM_VALIDATION_ENABLED",
    )
    agent_reasoning_structured_output_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_REASONING_STRUCTURED_OUTPUT_ENABLED",
    )
    agent_reasoning_adaptive_iterations_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_REASONING_ADAPTIVE_ITERATIONS_ENABLED",
    )
    agent_reasoning_adaptive_confidence_threshold: float = Field(
        default=0.75,
        validation_alias="AGENT_REASONING_ADAPTIVE_CONFIDENCE_THRESHOLD",
    )
    agent_llm_explanation_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_EXPLANATION_ENABLED",
    )
    agent_llm_intent_fallback_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_INTENT_FALLBACK_ENABLED",
    )
    # Provider-specific "thinking"/chain-of-thought control (currently only
    # meaningful for DeepSeek's `thinking` extra_body field -- see
    # `llm_client.py::build_chat_llm`). Default matches the provider's own
    # default (thinking enabled) so behavior is unchanged unless an operator
    # opts out. When disabled, `temperature`/`top_p` etc. also start having
    # an effect again -- DeepSeek's own docs note these are silently ignored
    # while thinking mode is on.
    agent_llm_thinking_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_THINKING_ENABLED",
    )
    # Only meaningful when thinking is enabled; DeepSeek V4 only accepts
    # "high"/"max" today ("low"/"medium" are mapped to "high" server-side,
    # per DeepSeek's own docs) -- exposed as a passthrough string rather than
    # a validated enum so a future provider's own values aren't hard-coded here.
    agent_llm_reasoning_effort: str | None = Field(
        default=None,
        validation_alias="AGENT_LLM_REASONING_EFFORT",
    )
    agent_llm_preference_extraction_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_LLM_PREFERENCE_EXTRACTION_ENABLED",
    )
    agent_llm_entity_extraction_fallback_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_LLM_ENTITY_EXTRACTION_FALLBACK_ENABLED",
    )
    agent_task_understanding_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_TASK_UNDERSTANDING_ENABLED",
    )
    agent_task_understanding_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_TASK_UNDERSTANDING_DRY_RUN",
    )
    agent_planner_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_PLANNER_ENABLED",
    )
    agent_planner_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_PLANNER_DRY_RUN",
    )
    agent_supervisor_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SUPERVISOR_ENABLED",
    )
    agent_supervisor_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_SUPERVISOR_DRY_RUN",
    )
    agent_supervisor_real_handlers_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SUPERVISOR_REAL_HANDLERS_ENABLED",
    )
    agent_supervisor_shadow_compare_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SUPERVISOR_SHADOW_COMPARE_ENABLED",
    )
    agent_supervisor_post_context_compare_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SUPERVISOR_POST_CONTEXT_COMPARE_ENABLED",
    )
    agent_supervisor_validation_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SUPERVISOR_VALIDATION_ENABLED",
    )
    agent_supervisor_promotion_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SUPERVISOR_PROMOTION_ENABLED",
    )
    agent_supervisor_promotion_mode_raw: str = Field(
        default="off",
        validation_alias="AGENT_SUPERVISOR_PROMOTION_MODE",
    )
    agent_supervisor_promotion_workflows: str = Field(
        default="graduation_progress_workflow,course_question_workflow,requirement_explanation_workflow",
        validation_alias="AGENT_SUPERVISOR_PROMOTION_WORKFLOWS",
    )
    # Phase 2 (post-Phase-9) — lets the Planner's own plan, executed for real
    # via the Supervisor, stand in for `task_planner.py` + `workflow.run()`
    # entirely for a capability, instead of only ever being compared against
    # it. Deliberately more conservative than Phase 9 promotion: unlike
    # `agent_supervisor_promotion_*`, this never bypasses the runtime
    # readiness gate when it's disabled -- see
    # `app/agent/planner_first_live.py::is_capability_planner_first_live_eligible`.
    agent_planner_first_live_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_PLANNER_FIRST_LIVE_ENABLED",
    )
    agent_planner_first_live_workflows: str = Field(
        default="",
        validation_alias="AGENT_PLANNER_FIRST_LIVE_WORKFLOWS",
    )
    # Phase 3 (post-Phase-9) — a separate, independent master switch from
    # `agent_planner_first_live_*` above: lets Planner-first-live execution
    # also cover the two proposal-creating workflows (never a direct write).
    # Deliberately its own flag/allowlist rather than folded into the
    # read-only one above -- enabling read-only Planner-first-live must
    # never silently also opt a deployment into proposal-creating execution.
    # See `app/agent/planner_first_live.py::is_capability_planner_first_live_proposal_eligible`.
    agent_planner_first_live_proposal_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_PLANNER_FIRST_LIVE_PROPOSAL_ENABLED",
    )
    agent_planner_first_live_proposal_workflows: str = Field(
        default="",
        validation_alias="AGENT_PLANNER_FIRST_LIVE_PROPOSAL_WORKFLOWS",
    )
    # Phase 4 (post-Phase-9) — lets a Monitor-detected mid-turn divergence
    # for a Planner-first-live turn actually trigger a live repair-and-
    # re-dispatch, instead of only ever producing a diagnostic. Independent
    # of, and additive to, `AGENT_PLAN_REPAIR_ENABLED` (which still gates
    # whether repair diagnostics run at all) -- both must be on. See
    # `app/agent/planner_first_live.py::attempt_live_plan_repair`.
    agent_planner_first_live_repair_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_PLANNER_FIRST_LIVE_REPAIR_ENABLED",
    )
    # Layer 2 (Planner: genuine multi-subtask live dispatch) — lets
    # Planner-first-live dispatch more than one capability for real in a
    # single turn (previously: exactly one, matching task_planner.py's
    # legacy single-workflow pick). Independent of, and layered on top of,
    # agent_planner_first_live_enabled/_proposal_enabled above -- turning
    # this on only changes behavior for a turn where the Planner's own
    # subtask graph names 2+ *already independently eligible* capabilities;
    # a single-capability plan behaves identically whether this is on or off.
    # See `app/agent/planner_first_live.py::run_planner_first_live_turn`.
    agent_planner_first_live_multi_capability_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_PLANNER_FIRST_LIVE_MULTI_CAPABILITY_ENABLED",
    )
    # Layer 3 — lets Planner-first-live dispatch also admit `specialist_agent`
    # -type capabilities (not just `workflow`-type) as first-class candidates.
    # A wholly separate, independent master switch/allowlist from
    # `agent_planner_first_live_*` above -- enabling workflow dispatch never
    # implies specialist-agent dispatch. Only ever meaningful when
    # `agent_planner_first_live_multi_capability_enabled` is also on -- there
    # is no legacy notion of a specialist being "the" primary capability the
    # way a workflow is. See
    # `app/agent/planner_first_live.py::is_specialist_planner_first_live_eligible`.
    agent_planner_first_live_specialist_agents_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS_ENABLED",
    )
    agent_planner_first_live_specialist_agents: str = Field(
        default="graduation_progress_agent",
        validation_alias="AGENT_PLANNER_FIRST_LIVE_SPECIALIST_AGENTS",
    )
    agent_specialist_agents_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SPECIALIST_AGENTS_ENABLED",
    )
    agent_specialist_agents_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_SPECIALIST_AGENTS_DRY_RUN",
    )
    agent_specialist_validation_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SPECIALIST_VALIDATION_ENABLED",
    )
    agent_specialist_compare_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SPECIALIST_COMPARE_ENABLED",
    )
    agent_specialist_observations_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SPECIALIST_OBSERVATIONS_ENABLED",
    )
    agent_specialist_observation_max_count: int = Field(
        default=8,
        validation_alias="AGENT_SPECIALIST_OBSERVATION_MAX_COUNT",
    )
    agent_specialist_tool_loop_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SPECIALIST_TOOL_LOOP_ENABLED",
    )
    agent_specialist_tool_loop_max_rounds: int = Field(
        default=1,
        validation_alias="AGENT_SPECIALIST_TOOL_LOOP_MAX_ROUNDS",
    )
    agent_specialist_tool_loop_max_requests_per_round: int = Field(
        default=4,
        validation_alias="AGENT_SPECIALIST_TOOL_LOOP_MAX_REQUESTS_PER_ROUND",
    )
    agent_specialist_text_promotion_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SPECIALIST_TEXT_PROMOTION_ENABLED",
    )
    agent_specialist_text_promotion_mode_raw: str = Field(
        default="off",
        validation_alias="AGENT_SPECIALIST_TEXT_PROMOTION_MODE",
    )
    agent_specialist_text_promotion_agents: str = Field(
        default="graduation_progress_agent",
        validation_alias="AGENT_SPECIALIST_TEXT_PROMOTION_AGENTS",
    )
    agent_specialist_text_promotion_max_chars: int = Field(
        default=4000,
        validation_alias="AGENT_SPECIALIST_TEXT_PROMOTION_MAX_CHARS",
    )
    agent_dynamic_agents_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_DYNAMIC_AGENTS_ENABLED",
    )
    agent_dynamic_agents_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_DYNAMIC_AGENTS_DRY_RUN",
    )
    agent_monitor_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_MONITOR_ENABLED",
    )
    agent_monitor_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_MONITOR_DRY_RUN",
    )
    agent_clarification_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_CLARIFICATION_ENABLED",
    )
    agent_clarification_user_facing_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_CLARIFICATION_USER_FACING_ENABLED",
    )
    agent_clarification_max_questions: int = Field(
        default=3,
        validation_alias="AGENT_CLARIFICATION_MAX_QUESTIONS",
    )
    agent_clarification_batching_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_CLARIFICATION_BATCHING_ENABLED",
    )
    agent_clarification_max_questions_per_turn: int = Field(
        default=3,
        validation_alias="AGENT_CLARIFICATION_MAX_QUESTIONS_PER_TURN",
    )
    agent_clarification_max_pending_turns: int = Field(
        default=3,
        validation_alias="AGENT_CLARIFICATION_MAX_PENDING_TURNS",
    )
    agent_clarification_state_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_CLARIFICATION_STATE_ENABLED",
    )
    agent_plan_repair_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_PLAN_REPAIR_ENABLED",
    )
    agent_plan_repair_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_PLAN_REPAIR_DRY_RUN",
    )
    agent_plan_repair_use_llm: bool = Field(
        default=False,
        validation_alias="AGENT_PLAN_REPAIR_USE_LLM",
    )
    agent_replan_max_repairs_per_goal: int = Field(
        default=2,
        validation_alias="AGENT_REPLAN_MAX_REPAIRS_PER_GOAL",
    )
    agent_replan_max_regenerations_per_goal: int = Field(
        default=1,
        validation_alias="AGENT_REPLAN_MAX_REGENERATIONS_PER_GOAL",
    )
    agent_clarification_effective_context_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_CLARIFICATION_EFFECTIVE_CONTEXT_ENABLED",
    )
    agent_planner_dynamic_specs_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_PLANNER_DYNAMIC_SPECS_ENABLED",
    )
    agent_planner_dynamic_specs_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_PLANNER_DYNAMIC_SPECS_DRY_RUN",
    )
    agent_planner_dynamic_specs_max_per_plan: int = Field(
        default=3,
        validation_alias="AGENT_PLANNER_DYNAMIC_SPECS_MAX_PER_PLAN",
    )
    agent_planner_dynamic_specs_allowed_patterns: str = Field(
        default="single_pass,tool_observation_loop,compare_and_synthesize",
        validation_alias="AGENT_PLANNER_DYNAMIC_SPECS_ALLOWED_PATTERNS",
    )
    agent_planner_dynamic_specs_allowed_risk_levels: str = Field(
        default="low,medium",
        validation_alias="AGENT_PLANNER_DYNAMIC_SPECS_ALLOWED_RISK_LEVELS",
    )
    agent_synthesis_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SYNTHESIS_ENABLED",
    )
    agent_synthesis_dry_run: bool = Field(
        default=True,
        validation_alias="AGENT_SYNTHESIS_DRY_RUN",
    )
    agent_synthesis_use_llm: bool = Field(
        default=False,
        validation_alias="AGENT_SYNTHESIS_USE_LLM",
    )
    agent_synthesis_max_evidence_items: int = Field(
        default=12,
        validation_alias="AGENT_SYNTHESIS_MAX_EVIDENCE_ITEMS",
    )
    agent_synthesis_max_conflicts: int = Field(
        default=6,
        validation_alias="AGENT_SYNTHESIS_MAX_CONFLICTS",
    )
    agent_synthesis_max_candidate_chars: int = Field(
        default=5000,
        validation_alias="AGENT_SYNTHESIS_MAX_CANDIDATE_CHARS",
    )
    agent_synthesis_text_promotion_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_SYNTHESIS_TEXT_PROMOTION_ENABLED",
    )
    agent_synthesis_text_promotion_mode_raw: str = Field(
        default="off",
        validation_alias="AGENT_SYNTHESIS_TEXT_PROMOTION_MODE",
    )
    agent_synthesis_text_promotion_workflows: str = Field(
        default="graduation_progress_workflow,course_question_workflow,requirement_explanation_workflow",
        validation_alias="AGENT_SYNTHESIS_TEXT_PROMOTION_WORKFLOWS",
    )
    agent_synthesis_text_promotion_min_confidence: float = Field(
        default=0.85,
        validation_alias="AGENT_SYNTHESIS_TEXT_PROMOTION_MIN_CONFIDENCE",
    )
    agent_synthesis_text_promotion_max_chars: int = Field(
        default=5000,
        validation_alias="AGENT_SYNTHESIS_TEXT_PROMOTION_MAX_CHARS",
    )
    agent_synthesis_text_promotion_require_blocks: bool = Field(
        default=True,
        validation_alias="AGENT_SYNTHESIS_TEXT_PROMOTION_REQUIRE_BLOCKS",
    )
    agent_runtime_readiness_gate_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_RUNTIME_READINESS_GATE_ENABLED",
    )
    agent_runtime_readiness_manifest_path: str | None = Field(
        default=None,
        validation_alias="AGENT_RUNTIME_READINESS_MANIFEST_PATH",
    )
    agent_runtime_readiness_require_human_review: bool = Field(
        default=True,
        validation_alias="AGENT_RUNTIME_READINESS_REQUIRE_HUMAN_REVIEW",
    )
    agent_runtime_readiness_min_level_raw: str = Field(
        default="ready_for_limited_promotion",
        validation_alias="AGENT_RUNTIME_READINESS_MIN_LEVEL",
    )
    agent_runtime_readiness_max_age_days: int = Field(
        default=30,
        validation_alias="AGENT_RUNTIME_READINESS_MAX_AGE_DAYS",
    )
    agent_runtime_readiness_fail_closed: bool = Field(
        default=True,
        validation_alias="AGENT_RUNTIME_READINESS_FAIL_CLOSED",
    )
    agent_eval_full_llm_shadow_enabled: bool = Field(
        default=False,
        validation_alias="AGENT_EVAL_FULL_LLM_SHADOW_ENABLED",
    )
    agent_eval_full_llm_require_explicit_allow: bool = Field(
        default=True,
        validation_alias="AGENT_EVAL_FULL_LLM_REQUIRE_EXPLICIT_ALLOW",
    )
    agent_eval_full_llm_max_cases: int = Field(
        default=20,
        validation_alias="AGENT_EVAL_FULL_LLM_MAX_CASES",
    )
    agent_eval_full_llm_max_reasoning_calls_per_case: int = Field(
        default=20,
        validation_alias="AGENT_EVAL_FULL_LLM_MAX_REASONING_CALLS_PER_CASE",
    )
    agent_eval_full_llm_max_total_reasoning_calls: int = Field(
        default=200,
        validation_alias="AGENT_EVAL_FULL_LLM_MAX_TOTAL_REASONING_CALLS",
    )
    agent_eval_side_effect_firewall_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_EVAL_SIDE_EFFECT_FIREWALL_ENABLED",
    )
    agent_eval_report_contract_calls: bool = Field(
        default=True,
        validation_alias="AGENT_EVAL_REPORT_CONTRACT_CALLS",
    )
    agent_wiki_retrieval_limit: int = 5

    technion_raw_dir: str | None = None
    catalog_vault_wiki_path: str | None = None
    academic_default_semester_file: str | None = Field(
        default="courses_2025_201.json",
        validation_alias="ACADEMIC_DEFAULT_SEMESTER_FILE",
    )
    agent_graph_retrieval_enabled: bool = Field(
        default=True,
        validation_alias="AGENT_GRAPH_RETRIEVAL_ENABLED",
    )

    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_base_url: str | None = Field(default=None, validation_alias="OPENAI_BASE_URL")
    openai_chat_model: str | None = Field(default=None, validation_alias="OPENAI_CHAT_MODEL")
    embedding_api_key: str | None = Field(default=None, validation_alias="EMBEDDING_API_KEY")
    embedding_base_url: str | None = Field(default=None, validation_alias="EMBEDDING_BASE_URL")
    embedding_model: str | None = Field(default=None, validation_alias="EMBEDDING_MODEL")
    embedding_enabled: bool = Field(default=True, validation_alias="EMBEDDING_ENABLED")
    embedding_index_enabled: bool = Field(default=True, validation_alias="EMBEDDING_INDEX_ENABLED")
    embedding_index_cache_path: str | None = Field(
        default=None,
        validation_alias="EMBEDDING_INDEX_CACHE_PATH",
    )
    embedding_index_batch_size: int = Field(default=64, validation_alias="EMBEDDING_INDEX_BATCH_SIZE")
    embedding_index_cache_backup_count: int = Field(
        default=3,
        validation_alias="EMBEDDING_INDEX_CACHE_BACKUP_COUNT",
    )

    model_config = SettingsConfigDict(
        env_file=_settings_env_files(),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def resolved_internal_service_token(self) -> str:
        return (self.internal_service_token or "").strip()

    def resolved_api_service_url(self) -> str:
        configured = (self.api_service_url or "").strip()
        if configured:
            return configured.rstrip("/")
        return "http://api:8000"

    def resolved_bcrypt_salt_rounds(self) -> int:
        rounds = int(self.bcrypt_salt_rounds)
        return max(10, min(rounds, 15))

    def is_agentic_retrieval_enabled(self) -> bool:
        return bool(self.agent_agentic_retrieval_enabled)

    def is_agent_llm_validation_enabled(self) -> bool:
        return bool(self.agent_llm_validation_enabled)

    def is_agent_llm_thinking_enabled(self) -> bool:
        return bool(self.agent_llm_thinking_enabled)

    def resolved_agent_llm_reasoning_effort(self) -> str | None:
        value = (self.agent_llm_reasoning_effort or "").strip()
        return value or None

    def is_agent_reasoning_structured_output_enabled(self) -> bool:
        return bool(self.agent_reasoning_structured_output_enabled)

    def is_agent_reasoning_adaptive_iterations_enabled(self) -> bool:
        return bool(self.agent_reasoning_adaptive_iterations_enabled)

    def resolved_agent_reasoning_adaptive_confidence_threshold(self) -> float:
        value = float(self.agent_reasoning_adaptive_confidence_threshold)
        return max(0.0, min(1.0, value))

    def is_agent_llm_explanation_enabled(self) -> bool:
        if not (self.openai_api_key or "").strip():
            return False
        return bool(self.agent_llm_explanation_enabled)

    def is_agent_llm_intent_fallback_enabled(self) -> bool:
        if not (self.openai_api_key or "").strip():
            return False
        return bool(self.agent_llm_intent_fallback_enabled)

    def is_agent_llm_preference_extraction_enabled(self) -> bool:
        if not (self.openai_api_key or "").strip():
            return False
        return bool(self.agent_llm_preference_extraction_enabled)

    def is_agent_llm_entity_extraction_fallback_enabled(self) -> bool:
        if not (self.openai_api_key or "").strip():
            return False
        return bool(self.agent_llm_entity_extraction_fallback_enabled)

    def is_agent_task_understanding_enabled(self) -> bool:
        return bool(self.agent_task_understanding_enabled)

    def is_agent_task_understanding_dry_run(self) -> bool:
        return bool(self.agent_task_understanding_dry_run)

    def is_agent_planner_enabled(self) -> bool:
        return bool(self.agent_planner_enabled)

    def is_agent_planner_dry_run(self) -> bool:
        return bool(self.agent_planner_dry_run)

    def is_agent_supervisor_enabled(self) -> bool:
        return bool(self.agent_supervisor_enabled)

    def is_agent_supervisor_dry_run(self) -> bool:
        return bool(self.agent_supervisor_dry_run)

    def is_agent_supervisor_real_handlers_enabled(self) -> bool:
        return bool(self.agent_supervisor_real_handlers_enabled)

    def is_agent_supervisor_shadow_compare_enabled(self) -> bool:
        # Added in Phase 7 as a placeholder; superseded by
        # `is_agent_supervisor_post_context_compare_enabled` below, which is
        # the flag `supervisor.post_context_runner` actually reads for the
        # Phase 8 live-vs-shadow comparison hook. Left in place (unused by
        # Phase 8) in case a future phase wants a separate toggle for the
        # comparison step alone.
        return bool(self.agent_supervisor_shadow_compare_enabled)

    def is_agent_supervisor_post_context_compare_enabled(self) -> bool:
        # Phase 8: gates `supervisor.post_context_runner.run_post_context_shadow_compare`.
        # Off by default — when off, the orchestrator's post-workflow call
        # returns `None` immediately with zero extra DB/workflow/LLM calls,
        # so live turn behavior/latency is unchanged.
        return bool(self.agent_supervisor_post_context_compare_enabled)

    def is_agent_supervisor_validation_enabled(self) -> bool:
        # Phase 8: when off, `supervisor.validation.validate_shadow_run`
        # still returns a result (so a comparison can still be attached to
        # diagnostics), but with `status="skipped"` and no validators run —
        # the comparison stays minimal/deterministic either way.
        return bool(self.agent_supervisor_validation_enabled)

    def is_agent_supervisor_promotion_enabled(self) -> bool:
        # Phase 9: master on/off switch for `supervisor.promotion`. Off by
        # default; even when `True`, `agent_supervisor_promotion_mode()`
        # must also be `"promote_validated"` for anything to actually be
        # promoted (see that method and `supervisor/promotion.py`).
        return bool(self.agent_supervisor_promotion_enabled)

    def agent_supervisor_promotion_mode(self) -> str:
        # Phase 9: falls back to the safest value ("off") for any
        # unrecognized configuration instead of raising or guessing.
        mode = (self.agent_supervisor_promotion_mode_raw or "off").strip().lower()
        return mode if mode in {"off", "shadow_only", "promote_validated"} else "off"

    def is_agent_planner_first_live_enabled(self) -> bool:
        # Master on/off switch for `planner_first_live.run_planner_first_live_turn`.
        # Off by default; see `app/agent/planner_first_live.py` for every
        # additional gate this alone does not bypass (per-workflow allowlist,
        # runtime readiness gate -- which, unlike Phase 9 promotion, is never
        # bypassed here when disabled).
        return bool(self.agent_planner_first_live_enabled)

    def agent_planner_first_live_configured_workflows(self) -> frozenset[str]:
        raw = (self.agent_planner_first_live_workflows or "").strip()
        if not raw:
            return frozenset()
        return frozenset(name.strip() for name in raw.split(",") if name.strip())

    def is_agent_planner_first_live_proposal_enabled(self) -> bool:
        # Master on/off switch for proposal-capable Planner-first-live
        # execution -- independent of `is_agent_planner_first_live_enabled`
        # above. Off by default.
        return bool(self.agent_planner_first_live_proposal_enabled)

    def agent_planner_first_live_proposal_configured_workflows(self) -> frozenset[str]:
        raw = (self.agent_planner_first_live_proposal_workflows or "").strip()
        if not raw:
            return frozenset()
        return frozenset(name.strip() for name in raw.split(",") if name.strip())

    def is_agent_planner_first_live_repair_enabled(self) -> bool:
        # Master on/off switch for live repair-and-redispatch (Phase 4,
        # post-Phase-9). Off by default; `attempt_live_plan_repair` also
        # requires `is_agent_plan_repair_enabled()` (checked internally by
        # `run_plan_repair_diagnostics`) to be on.
        return bool(self.agent_planner_first_live_repair_enabled)

    def is_agent_planner_first_live_multi_capability_enabled(self) -> bool:
        # Layer 2: off by default -- when off, `run_planner_first_live_turn`
        # collapses eligibility to at most the single primary workflow name,
        # byte-for-byte pre-Layer-2 behavior.
        return bool(self.agent_planner_first_live_multi_capability_enabled)

    def is_agent_planner_first_live_specialist_agents_enabled(self) -> bool:
        # Layer 3: off by default -- master switch for treating a
        # `specialist_agent`-type capability as a Planner-first-live
        # candidate at all.
        return bool(self.agent_planner_first_live_specialist_agents_enabled)

    def agent_planner_first_live_configured_specialist_agents(self) -> frozenset[str]:
        raw = (self.agent_planner_first_live_specialist_agents or "").strip()
        if not raw:
            return frozenset()
        return frozenset(name.strip() for name in raw.split(",") if name.strip())

    def is_agent_specialist_agents_enabled(self) -> bool:
        # Phase 10: master on/off switch for `specialists.supervisor_handler.SpecialistAgentHandler`.
        # Off by default — when off, the handler returns a safe `"skipped"`
        # result without ever calling `ReasoningBlock` (no LLM/network call,
        # no `OPENAI_API_KEY` required).
        return bool(self.agent_specialist_agents_enabled)

    def is_agent_specialist_agents_dry_run(self) -> bool:
        # Phase 10 never executes anything beyond a `ReasoningBlock` call
        # regardless of this flag — there is no real execution engine for
        # specialist agents yet. A misconfigured `false` only adds a warning
        # (see `specialists.base.run_specialist_reasoning`) instead of being
        # silently ignored.
        return bool(self.agent_specialist_agents_dry_run)

    def is_agent_specialist_validation_enabled(self) -> bool:
        # Phase 11: master switch for `specialists.validation.validate_specialist_output`
        # actually running its validators. Off by default; when off, a
        # validation result is still returned (so a comparison can still be
        # attached to diagnostics) with `status="skipped"`. Purely
        # deterministic — never requires `OPENAI_API_KEY`.
        return bool(self.agent_specialist_validation_enabled)

    def is_agent_specialist_compare_enabled(self) -> bool:
        # Phase 11: master switch for `specialists.compare.compare_workflow_and_specialist`
        # actually running. Off by default. Purely deterministic — never
        # requires `OPENAI_API_KEY`.
        return bool(self.agent_specialist_compare_enabled)

    def is_agent_specialist_observations_enabled(self) -> bool:
        # Phase 12: master switch for `specialists.supervisor_handler.SpecialistAgentHandler`
        # building deterministic tool observations
        # (`specialists.tools.observation_builder.build_specialist_observations`)
        # before calling a specialist. Off by default — when off, behavior is
        # byte-for-byte Phase 10/11 (`deterministic_observations` stays `[]`).
        # Purely deterministic — never calls an LLM, never requires
        # `OPENAI_API_KEY`, even when enabled.
        return bool(self.agent_specialist_observations_enabled)

    def resolved_agent_specialist_observation_max_count(self) -> int:
        # Phase 12: fail-closed bound on how many observations one
        # specialist call may receive — never negative, regardless of
        # misconfiguration.
        return max(0, int(self.agent_specialist_observation_max_count or 0))

    def is_agent_specialist_tool_loop_enabled(self) -> bool:
        # Phase 13: master switch for the bounded specialist tool-request
        # loop (`specialists.base.run_specialist_reasoning` /
        # `specialists.tools.tool_loop`). Off by default — when off, a
        # `needs_tool` `ReasoningBlockOutput` degrades to the existing
        # Phase 10 fallback exactly as before Phase 13 existed. The loop
        # itself only ever calls the existing Phase 12 observation builder,
        # never an LLM directly — only the specialist's own `ReasoningBlock`
        # re-run does (same `OPENAI_API_KEY` dependency as Phase 10).
        return bool(self.agent_specialist_tool_loop_enabled)

    def resolved_agent_specialist_tool_loop_max_rounds(self) -> int:
        # Phase 13: fail-closed bound on how many tool-request rounds one
        # specialist call may use. Configured default is 1; even a
        # misconfigured/hostile value can never exceed the hard ceiling of
        # 2, and never goes negative.
        return max(0, min(int(self.agent_specialist_tool_loop_max_rounds or 0), 2))

    def resolved_agent_specialist_tool_loop_max_requests_per_round(self) -> int:
        # Phase 13: fail-closed bound on how many observation "tools" a
        # specialist may request in a single round. Configured default is
        # 4; even a misconfigured/hostile value can never exceed the hard
        # ceiling of 8, and never goes negative.
        return max(0, min(int(self.agent_specialist_tool_loop_max_requests_per_round or 0), 8))

    def is_agent_specialist_text_promotion_enabled(self) -> bool:
        # Phase 14: master switch for `specialists.text_promotion.evaluate_specialist_text_promotion`.
        # Off by default — when off, `run_post_context_shadow_compare` never
        # even builds the specialist-output sink for text promotion, so this
        # changes zero behavior/work beyond Phase 13.
        return bool(self.agent_specialist_text_promotion_enabled)

    def agent_specialist_text_promotion_mode(self) -> str:
        # Phase 14: falls back to the safest value ("off") for any
        # unrecognized configuration instead of raising or guessing —
        # mirrors `agent_supervisor_promotion_mode`.
        mode = (self.agent_specialist_text_promotion_mode_raw or "off").strip().lower()
        return mode if mode in {"off", "shadow_only", "promote_validated"} else "off"

    def agent_specialist_text_promotion_configured_agents(self) -> frozenset[str]:
        # Phase 14: the *configured* allowlist only — `text_promotion.py`
        # always additionally intersects this with a hardcoded ceiling of
        # exactly `{"graduation_progress_agent"}`, so misconfiguring this
        # setting can only ever narrow eligibility, never widen it.
        raw = (self.agent_specialist_text_promotion_agents or "").strip()
        if not raw:
            return frozenset()
        return frozenset(name.strip() for name in raw.split(",") if name.strip())

    def resolved_agent_specialist_text_promotion_max_chars(self) -> int:
        # Phase 14: fail-closed bound on how long a promoted `answer_text`
        # may be — always at least 1, regardless of misconfiguration.
        return max(1, int(self.agent_specialist_text_promotion_max_chars or 0))

    def is_agent_dynamic_agents_enabled(self) -> bool:
        # Phase 15: master switch for `dynamic_agents.supervisor_handler.DynamicAgentHandler`.
        # Off by default — when off, the handler returns a safe `"skipped"`
        # result without ever calling `ReasoningBlock` (no LLM/network call,
        # no `OPENAI_API_KEY` required).
        return bool(self.agent_dynamic_agents_enabled)

    def is_agent_dynamic_agents_dry_run(self) -> bool:
        # Phase 15 always executes in shadow-only mode regardless of this
        # flag — a misconfigured `false` only adds a warning and still forces
        # dry-run behavior inside `DynamicAgentInstance.run`.
        return bool(self.agent_dynamic_agents_dry_run)

    def is_agent_monitor_enabled(self) -> bool:
        # Phase 16: master switch for deterministic plan monitoring diagnostics.
        # Off by default — when off, no monitor diagnostics are attached and
        # no replan/repair signal is computed.
        return bool(self.agent_monitor_enabled)

    def is_agent_monitor_dry_run(self) -> bool:
        # Phase 16 always remains diagnostic-only regardless of this flag —
        # a misconfigured `false` only adds a warning inside `monitor_plan_execution`.
        return bool(self.agent_monitor_dry_run)

    def is_agent_clarification_enabled(self) -> bool:
        # Phase 17: master switch for clarification capability diagnostics.
        # Off by default — when off, no clarification diagnostics are attached.
        return bool(self.agent_clarification_enabled)

    def is_agent_clarification_user_facing_enabled(self) -> bool:
        # Phase 17/18: when false (default), clarification never emits user-facing
        # questions — only diagnostics and assumed fallbacks.
        return bool(self.agent_clarification_user_facing_enabled)

    def is_agent_clarification_batching_enabled(self) -> bool:
        # Phase 28.2: when false (default), only one clarification question is
        # offered per turn — safer for user interruption cadence.
        return bool(self.agent_clarification_batching_enabled)

    def resolved_agent_clarification_max_questions_per_turn(self) -> int:
        return max(1, int(self.agent_clarification_max_questions_per_turn or 1))

    def is_agent_clarification_state_enabled(self) -> bool:
        # Phase 18: when false, user-facing questions may still be returned but
        # pending clarification state is not persisted across turns.
        return bool(self.agent_clarification_state_enabled)

    def is_agent_plan_repair_enabled(self) -> bool:
        # Phase 19: master switch for warm planner repair diagnostics.
        return bool(self.agent_plan_repair_enabled)

    def is_agent_plan_repair_dry_run(self) -> bool:
        # Phase 19 always remains diagnostic-only — misconfigured false forces dry-run.
        return bool(self.agent_plan_repair_dry_run)

    def is_agent_plan_repair_use_llm(self) -> bool:
        # Phase 19 optional ReasoningBlock repair path.
        return bool(self.agent_plan_repair_use_llm)

    def resolved_agent_replan_max_repairs_per_goal(self) -> int:
        return max(1, int(self.agent_replan_max_repairs_per_goal or 2))

    def resolved_agent_replan_max_regenerations_per_goal(self) -> int:
        return max(0, int(self.agent_replan_max_regenerations_per_goal or 1))

    def is_agent_clarification_effective_context_enabled(self) -> bool:
        # Phase 19: inject compact confirmed clarification into planning metadata.
        return bool(self.agent_clarification_effective_context_enabled)

    def is_agent_planner_dynamic_specs_enabled(self) -> bool:
        # Phase 20: Planner may emit dynamic AgentSpecs for shadow subtasks.
        return bool(self.agent_planner_dynamic_specs_enabled)

    def is_agent_planner_dynamic_specs_dry_run(self) -> bool:
        # Phase 20 always remains diagnostic-only — misconfigured false forces dry-run.
        return bool(self.agent_planner_dynamic_specs_dry_run)

    def planner_dynamic_specs_allowed_patterns_set(self) -> frozenset[str]:
        raw = (self.agent_planner_dynamic_specs_allowed_patterns or "").strip()
        if not raw:
            return frozenset()
        return frozenset(item.strip() for item in raw.split(",") if item.strip())

    def planner_dynamic_specs_allowed_risk_levels_set(self) -> frozenset[str]:
        raw = (self.agent_planner_dynamic_specs_allowed_risk_levels or "").strip()
        if not raw:
            return frozenset()
        return frozenset(item.strip() for item in raw.split(",") if item.strip())

    def is_agent_synthesis_enabled(self) -> bool:
        # Phase 21: master switch for synthesis / final answer composer diagnostics.
        return bool(self.agent_synthesis_enabled)

    def is_agent_synthesis_dry_run(self) -> bool:
        # Phase 21 always remains diagnostic-only — misconfigured false forces dry-run.
        return bool(self.agent_synthesis_dry_run)

    def is_agent_synthesis_use_llm(self) -> bool:
        # Phase 21 optional ReasoningBlock synthesis path.
        return bool(self.agent_synthesis_use_llm)

    def is_agent_synthesis_text_promotion_enabled(self) -> bool:
        # Phase 22: master switch for synthesis text promotion.
        return bool(self.agent_synthesis_text_promotion_enabled)

    def agent_synthesis_text_promotion_mode(self) -> str:
        mode = (self.agent_synthesis_text_promotion_mode_raw or "off").strip().lower()
        if mode not in {"off", "shadow_only", "promote_validated"}:
            return "off"
        return mode

    def synthesis_text_promotion_configured_workflows(self) -> frozenset[str]:
        raw = (self.agent_synthesis_text_promotion_workflows or "").strip()
        if not raw:
            return frozenset()
        return frozenset(item.strip() for item in raw.split(",") if item.strip())

    def resolved_agent_synthesis_text_promotion_max_chars(self) -> int:
        return max(1, int(self.agent_synthesis_text_promotion_max_chars or 5000))

    def is_agent_synthesis_text_promotion_require_blocks(self) -> bool:
        return bool(self.agent_synthesis_text_promotion_require_blocks)

    def is_agent_runtime_readiness_gate_enabled(self) -> bool:
        return bool(self.agent_runtime_readiness_gate_enabled)

    def resolved_agent_runtime_readiness_manifest_path(self) -> str | None:
        configured = (self.agent_runtime_readiness_manifest_path or "").strip()
        return configured or None

    def is_agent_runtime_readiness_require_human_review(self) -> bool:
        return bool(self.agent_runtime_readiness_require_human_review)

    def is_agent_runtime_readiness_fail_closed(self) -> bool:
        return bool(self.agent_runtime_readiness_fail_closed)

    def resolved_agent_runtime_readiness_max_age_days(self) -> int:
        return max(1, int(self.agent_runtime_readiness_max_age_days or 30))

    def agent_runtime_readiness_min_level(self) -> str:
        level = (self.agent_runtime_readiness_min_level_raw or "ready_for_limited_promotion").strip()
        if level not in {
            "not_ready",
            "ready_for_shadow",
            "ready_for_limited_promotion",
            "ready_for_broader_promotion",
        }:
            return "ready_for_limited_promotion"
        return level

    def is_agent_eval_full_llm_shadow_enabled(self) -> bool:
        return bool(self.agent_eval_full_llm_shadow_enabled)

    def is_agent_eval_full_llm_require_explicit_allow(self) -> bool:
        return bool(self.agent_eval_full_llm_require_explicit_allow)

    def resolved_agent_eval_full_llm_max_cases(self) -> int:
        return max(1, int(self.agent_eval_full_llm_max_cases or 20))

    def resolved_agent_eval_full_llm_max_reasoning_calls_per_case(self) -> int:
        return max(1, int(self.agent_eval_full_llm_max_reasoning_calls_per_case or 20))

    def resolved_agent_eval_full_llm_max_total_reasoning_calls(self) -> int:
        return max(1, int(self.agent_eval_full_llm_max_total_reasoning_calls or 200))

    def is_agent_eval_side_effect_firewall_enabled(self) -> bool:
        return bool(self.agent_eval_side_effect_firewall_enabled)

    def is_agent_eval_report_contract_calls(self) -> bool:
        return bool(self.agent_eval_report_contract_calls)

    def agent_supervisor_promotion_configured_workflows(self) -> frozenset[str]:
        # Phase 9: the *configured* allowlist only — `supervisor.promotion`
        # always additionally intersects this with a hardcoded ceiling
        # (`supervisor.promotion._HARD_ALLOWED_PROMOTION_WORKFLOWS`), so
        # misconfiguring this setting can only ever narrow eligibility,
        # never widen it.
        raw = (self.agent_supervisor_promotion_workflows or "").strip()
        if not raw:
            return frozenset()
        return frozenset(name.strip() for name in raw.split(",") if name.strip())

    def resolved_embedding_api_key(self) -> str:
        return (self.embedding_api_key or "").strip()

    def resolved_embedding_base_url(self) -> str:
        configured = (self.embedding_base_url or "").strip()
        if configured:
            return configured.rstrip("/")
        return "https://api.llmod.ai/v1"

    def resolved_embedding_model(self) -> str:
        configured = (self.embedding_model or "").strip()
        if configured:
            return configured
        return "MB5R2CF-azure/text-embedding-3-small"

    def embeddings_available(self) -> bool:
        return bool(self.embedding_enabled and self.resolved_embedding_api_key())

    def resolved_embedding_index_cache_path(self) -> str:
        configured = (self.embedding_index_cache_path or "").strip()
        local_default = str(_APP_ROOT / "data" / "cache" / "wiki_embedding_index.json")
        if configured:
            if configured.startswith("/app/") and self.environment != "production":
                return local_default
            return configured
        if self.environment == "production":
            return "/app/data/cache/wiki_embedding_index.json"
        return local_default

    def wiki_vector_index_enabled(self) -> bool:
        return bool(self.embedding_index_enabled and self.embeddings_available())

    def resolved_embedding_index_cache_backup_count(self) -> int:
        return max(0, int(self.embedding_index_cache_backup_count or 3))

    def resolved_academic_wiki_path(self) -> str:
        configured = (self.catalog_vault_wiki_path or "").strip()
        local = _APP_ROOT / "data" / "academic" / "wiki"
        docker_mount = Path("/app/data/academic/wiki")
        if configured:
            if configured.startswith("/app/") and self.environment != "production" and local.is_dir():
                return str(local)
            if not Path(configured).is_dir() and docker_mount.is_dir():
                # `configured` is typically a path relative to the repo root,
                # meant for local dev where CWD is services/agent (e.g.
                # "../data-engineering/data/catalog_valut/catalog_valut/wiki").
                # That relative path never resolves inside Docker (WORKDIR=/app),
                # even though the real wiki content is right there via the
                # docker-compose volume mount at this fixed path -- prefer it
                # over a `configured` value that doesn't actually exist,
                # rather than silently returning a dead path (see
                # docker-compose.yml's `agent`/`api` volume mounts).
                return str(docker_mount)
            return configured
        if self.environment == "production":
            return "/app/data/academic/wiki"
        return str(local) if local.is_dir() else ""

    def resolved_technion_raw_dir(self) -> str:
        configured = (self.technion_raw_dir or "").strip()
        local = _resolve_repo_root() / "services" / "data-engineering" / "data" / "raw" / "technion"
        if configured:
            if configured.startswith("/app/") and self.environment != "production" and local.is_dir():
                return str(local)
            return configured
        if self.environment == "production":
            return "/app/data/raw/technion"
        return str(local) if local.is_dir() else configured

    def resolved_default_semester_file(self) -> str | None:
        explicit = (self.academic_default_semester_file or "").strip()
        return explicit or None

    def is_graph_retrieval_configured(self) -> bool:
        if not self.agent_graph_retrieval_enabled:
            return False
        return bool(self.resolved_academic_wiki_path() and self.resolved_technion_raw_dir())

    def is_legacy_rag_enabled(self) -> bool:
        """Legacy BM25/embedding wiki RAG — kept for tests/reference, not the live path."""
        return False


@lru_cache
def get_settings() -> Settings:
    return Settings()
