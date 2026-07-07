# Offline Agent Eval Cases (Phase 23)

Sanitized synthetic fixtures for the offline replay + evaluation harness.

## Rules

- No real student data, transcript rows, catalog dumps, or raw prompts/responses.
- Cases define **structured expected behavior** (intent, workflow, gates, oracles).
- Default evaluation mode is `gates_only` (no LLM, no DB, no orchestrator).

## Run

```bash
cd services/agent
.venv/bin/python scripts/run_agent_replay_eval.py \
  --cases tests/fixtures/eval_cases \
  --mode gates_only \
  --output /tmp/unipilot-agent-eval-report.json \
  --markdown /tmp/unipilot-agent-eval-report.md
```

## Case kinds

Each JSON file is one `EvalCase`. See `app/agent/evaluation/replay_schemas.py`.
