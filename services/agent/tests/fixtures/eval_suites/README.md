# Eval Suite Manifests (Phase 24)

Named evaluation suites group sanitized offline cases for promotion-readiness scoring.

Each suite manifest references case IDs from `tests/fixtures/eval_cases/`.

Run readiness:

```bash
cd services/agent
.venv/bin/python scripts/run_agent_promotion_readiness.py \
  --cases tests/fixtures/eval_cases \
  --suites tests/fixtures/eval_suites \
  --mode gates_only
```
