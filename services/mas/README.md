# MAS Service

Internal **multi-agent orchestration** runtime for UniPilot. Independent from `services/ai` (single advisor).

## Ground truth

- **Institutional facts:** catalog wiki markdown + Technion semester offering JSON (same mounts as `ai`)
- **User-specific data:** MongoDB (`student_profiles`, `completed_courses`, `agent_sessions`)

## Runtime

- **HTTP:** `GET /health` on port `3003` (internal Docker network only)
- **Worker:** background Redis consumer (`MAS_QUEUE_NAME`, default `mas_agent_jobs`)
- **LLM:** MAS-owned client; uses `MAS_OPENAI_*` when set, otherwise falls back to shared `OPENAI_*` from `.env` (e.g. `OPENAI_CHAT_MODEL=deepseek-v4-pro` for all LLM layers)
- **Orchestration:** typed `Blackboard` artifacts + plugin agents driven by `run_negotiation()` (Goal Analyst → Planner → critics → Arbiter → Explainer)

## Agent plugins (MAS-1.5)

| Agent | Module | Role |
|---|---|---|
| Goal Analyst | `app/agents/goal_analyst.py` | NL goal → `GoalSpec` (L0 rules + L1 LLM JSON) |
| Planner | `app/agents/planner.py` | propose / revise; graph tool loop; repair layer; multi-candidate variants |
| Catalog Scout | `app/agents/catalog_scout.py` | hard feasibility veto (`FeasibilityReport`, typed violations) |
| Risk Sentinel | `app/agents/risk_sentinel.py` | credit overload hard veto; probation pressure signal |
| Progress Scout | `app/agents/progress_scout.py` | soft degree-progress critiques **per variant** |
| Student Advocate | `app/agents/student_advocate.py` | soft preference critiques + trade-offs **per variant** |
| Arbiter | `app/agents/arbiter.py` | multi-candidate utility arbitration using per-variant reports |
| Explainer | `app/agents/explainer.py` | post-commit `studentSummary` (read-only LLM narration) |

**MAS-2 P0:** `plan_hard_constraints.py` (unified hard gate), `variant_evaluation.py` (per-variant soft scores), artifact-aware utility in `orchestrator/utility.py`.

Register additional critics via `AgentRegistry` (see `app/agents/registry.py`).

## API integration

Clients use the public API (not this service directly):

- `POST /agent/sessions` → `202` + `sessionId`
- `GET /agent/sessions/:id` → status, transcript, `finalDecision`, `utilityBreakdown`

Web UI: `/agents` (`AgentSessionsPage`) — start sessions, poll status, view transcript.

## Local tests

```bash
cd services/mas
pip install -r requirements.txt -r requirements-dev.txt
pytest
```

### Docker E2E (agent sessions)

With `docker compose up --build` running from the repo root:

```bash
RUN_DOCKER_E2E=1 python3 scripts/test_mas_agent_session_e2e.py
# Planner LLM graph tool loop (OPENAI_* in root .env is enough for MAS):
RUN_DOCKER_E2E=1 E2E_LLM_GOAL=1 python3 scripts/test_mas_agent_session_e2e.py
```

Polls `POST /agent/sessions` → `GET /agent/sessions/:id` until completed; asserts transcript roles, `finalDecision.schedule`, and courses.

Apply flow (API): `POST /agent/sessions/:id/approve` then `POST /agent/sessions/:id/apply` → creates a draft semester plan with optimized lesson selections.

### Extensive E2E suite (19 cases)

```bash
RUN_DOCKER_E2E=1 python3 scripts/test_mas_extensive_e2e.py
```

Covers auth, validation, deterministic + LLM sessions, constraints, schedule shape, approve/override/apply lifecycle, and cross-user isolation. Set `E2E_LLM_CASES=0` to skip the slow LLM case.
