# Generated catalog exports

Reviewed catalog JSON for staging import is produced from the **catalog wiki vault** (`data/catalog_valut/wiki/`).

**Planned output location:**

```
data/generated/technion/catalog/
├── catalog_reviewed.json
└── catalog_phase8_readiness_check.json
```

Generate with the planned `export-vault-catalog` CLI (see `docs/planning/CATALOG_VAULT_INTEGRATION_PLAN.md`).

Until export is implemented, staging import tests use fixtures under `tests/fixtures/`.
