# UniPilot RAG Fine-Tuning

Primary specification: [`Agent_RAG_tuning.md`](../../Agent_RAG_tuning.md) at the repository root.

## Locked configuration

Retrieval profiles are defined in:

- `services/api/app/retrieval/profile_config.json`
- `services/api/app/retrieval/profiles.py`

The Context Builder selects profiles per intent and applies profile-specific limits for:

- hybrid wiki top-K and weights
- rerank candidate limits
- wiki chunk count and token budget
- retrieval attempt limits and latency budgets

## Evaluation

Benchmark cases:

- `services/api/app/retrieval/evaluation/benchmark_cases.jsonl`

Run evaluation (from `services/api`; loads repo-root `.env` automatically — do **not** `source .env`):

```bash
cd services/api
# Start Mongo for offering cases (from repo root):
docker compose up -d mongo

python -m app.retrieval.evaluation.run_rag_fine_tuning
python -m app.retrieval.evaluation.run_retrieval_eval --profiles-only
```

Offering benchmark cases read from **Mongo `course_offerings`** (imported catalog) with optional
**`TECHNION_RAW_DIR` JSON fallback** in `offerings_retriever.py`.
Use `--no-mongo` to skip offering cases; `--require-mongo` to fail fast if Mongo is down.
Use `--seed-benchmark-offerings` only for local CI when catalog data is not imported (not production eval).

Full baseline uses **one** in-place `tqdm` progress bar (`--no-progress` to disable).

Regression tests:

```bash
cd services/api
python -m pytest tests/retrieval/ -q
```

## Design rules

1. Exact structured retrieval first.
2. Hybrid wiki retrieval second.
3. LLM explanation last.
4. No single global RAG profile.
5. User MongoDB data is never embedded in the shared wiki index.

## Phase 7 agentic retrieval (Context Builder)

When `AGENT_AGENTIC_RETRIEVAL_ENABLED=true` (default):

1. **Query decomposition** — `app/agent/query_decomposer.py` splits compound questions into ≤4 wiki sub-queries.
2. **Multi-step retrieval** — each sub-query runs hybrid wiki search; results merge in `wiki_context_merger.py`.
3. **Bounded refinement** — up to `maxRetrievalAttempts` per profile (strict → relaxed → fallback wiki scope).
4. **Gap detection** — `retrieval_gaps.py` drives retry queries on attempt 2+.
5. **Explanation summary** — `wikiExplanationSummary` in `retrieval_metadata` for workflows/LLM.
6. **Optional LLM validation** — set `AGENT_LLM_VALIDATION_ENABLED=true` + `OPENAI_API_KEY` for a second-pass sufficiency check.

Disable agentic mode: `AGENT_AGENTIC_RETRIEVAL_ENABLED=false` (reverts to single wiki query per plan).

## Embedding service (LLMod)

Semantic scoring uses an OpenAI-compatible embedding endpoint (LLMod) when configured.

Environment variables (root `.env`):

```bash
EMBEDDING_API_KEY=...
EMBEDDING_BASE_URL=https://api.llmod.ai/v1
EMBEDDING_MODEL=MB5R2CF-azure/text-embedding-3-small
EMBEDDING_ENABLED=true
```

If `EMBEDDING_API_KEY` is unset, hybrid reranking uses token-overlap semantic scoring (zero embedding cost).

**Cost estimate before any paid run:** `docs/agent/RAG_EMBEDDING_COST_ESTIMATE.md`

Implementation:
- `services/api/app/retrieval/embedding_service.py`
- `services/api/app/retrieval/wiki_vector_index.py`
- `python -m app.retrieval.build_wiki_vector_index --estimate-cost`
