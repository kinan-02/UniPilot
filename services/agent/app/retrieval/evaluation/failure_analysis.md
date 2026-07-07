# Retrieval failure analysis (Agent_RAG_tuning.md §21)

Baseline evaluation should record failures here after running:

```bash
cd services/api
python -m app.retrieval.evaluation.run_retrieval_eval
```

## Known baseline notes (MVP)

- Wiki benchmark cases require `CATALOG_VAULT_WIKI_PATH` or test fixtures.
- Structured offering Hit@1 is validated via integration tests, not wiki-only benchmark.
- Expand benchmark to 100+ cases before locking production parameters.
