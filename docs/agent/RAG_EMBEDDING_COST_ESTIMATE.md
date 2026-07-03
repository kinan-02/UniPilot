# RAG Embedding Cost Estimates

Last updated: 2026-07-03

## Service split

| Purpose | Env vars | Provider |
|---------|----------|----------|
| Chat / advisor / MAS LLM | `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_CHAT_MODEL` | DeepSeek (`deepseek-v4-pro`) |
| Wiki semantic retrieval | `EMBEDDING_API_KEY`, `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` | LLMod (`text-embedding-3-small`) |

Retrieval eval and vector-index builds **do not** call the DeepSeek chat API.

## Measured corpus size (local wiki vault)

| Scope | Markdown files | Indexed chunks | Est. embedding tokens |
|-------|---------------:|---------------:|----------------------:|
| DDS courses only | 197 | 718 | ~20,000 |
| Full Technion wiki | 2,753 | 10,315 | ~1,066,000 |

Benchmark cases (generated): **331** DDS-focused cases (`benchmark_cases.jsonl`).

## Cost scenarios (embedding only)

Assumptions:
- Model: `text-embedding-3-small` class pricing ≈ **$0.02 / 1M input tokens** (OpenAI list price; LLMod may add markup — confirm on [llmod.ai](https://api.llmod.ai) dashboard).
- Query embedding ≈ 12 tokens each when vector index is warm.
- Without index cache, each eval case may embed ~30–60 candidate chunks (~2,000+ tokens/case).

### A) One-time vector index build (recommended)

| Item | Tokens | Est. cost @ $0.02/1M |
|------|-------:|---------------------:|
| Full wiki index | ~1,066,000 | **~$0.02** |
| DDS-only index | ~20,000 | **<$0.001** |

### B) Benchmark eval with warm index (331 wiki cases)

| Item | Tokens | Est. cost @ $0.02/1M |
|------|-------:|---------------------:|
| Query embeddings only | ~4,000 | **<$0.001** |

### C) Benchmark eval **without** index (not recommended)

| Item | Tokens | Est. cost @ $0.02/1M |
|------|-------:|---------------------:|
| 331 cases × ~2,000 tokens | ~662,000 | **~$0.01–0.02** |

### D) Combined recommended first run

1. Build index once (~$0.02)
2. Run eval (~<$0.001)

**Total: roughly $0.02–0.03 USD** for the full wiki index + 331-case eval, assuming LLMod charges near OpenAI embedding rates.

## Expected runtime

| Step | Typical duration | Notes |
|------|-----------------|-------|
| Wiki vector index (first run, ~162 batches) | 3–10 min | LLMod latency + rate limits |
| Benchmark eval (331 cases, warm index) | 1–5 min | Mostly local wiki load + 1 query embed/case |
| **Full `run_rag_fine_tuning` pipeline** | **5–15 min** | Single tqdm progress bar |
| Re-run eval only (`--skip-index`) | 1–5 min | Index loaded from cache |

Worst case (slow API / throttling): up to ~30–45 minutes for a cold full run.

## Commands (safe: estimate only)

```bash
cd services/api
export CATALOG_VAULT_WIKI_PATH=../data-engineering/data/catalog_valut/catalog_valut/wiki
python -m app.retrieval.build_wiki_vector_index --estimate-cost
python -m app.retrieval.evaluation.run_retrieval_eval --estimate-cost
```

## Commands (paid: requires `EMBEDDING_API_KEY`)

```bash
cd services/api
python -m app.retrieval.evaluation.run_rag_fine_tuning --wiki-root "$CATALOG_VAULT_WIKI_PATH"
```

Set `EMBEDDING_ENABLED=false` to run eval with token-overlap only (zero embedding cost).
