# Data Engineering Service

Internal Python service for Technion academic data ingestion, staging validation, and guarded production promotion into MongoDB.

See also: `docs/DATA_INGESTION_ARCHITECTURE.md`, `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`, `docs/planning/CATALOG_VAULT_INTEGRATION_PLAN.md`, root `README.md`.

## Data sources (authoritative)

| Source | Path | Used for |
|--------|------|----------|
| Semester course JSON | `data/raw/technion/courses_2025_{200,201,202}.json` | Semester planner — offerings, groups, schedules |
| Catalog wiki vault | `data/catalog_valut/wiki/` | Programs, tracks, requirements, course metadata, regulations, future RAG |

Large semester JSON files are **gitignored**. Catalog PDFs and parsed sources live under `catalog_valut/raw/` (immutable provenance).

Wiki schema and ingest rules: `data/catalog_valut/CLAUDE.md`

## Semester offerings import

```bash
cd services/data-engineering

python -m app.main import-technion-courses-staging --dry-run
python -m app.main import-technion-courses-staging
python -m app.main import-technion-courses-staging --dds-only
```

Defaults read all three semester JSON files from `data/raw/technion/`. Use `--course-json` to override paths.

## Catalog vault → MongoDB

The legacy PDF/markdown parser pipeline has been **removed**. Catalog data is curated in the Obsidian wiki vault and exported to JSON for staging import.

**Flow:**

```bash
python -m app.main export-vault-catalog --faculty dds

# Existing staging + promotion (vault sign-off is embedded in export output)
python -m app.main import-dds-catalog-staging --dry-run
python -m app.main validate-dds-staging-quality
python -m app.main plan-dds-production-promotion
python -m app.main promote-dds-to-production --i-confirm-dangerous-production-write
```

Export output: `data/generated/technion/catalog/catalog_reviewed.json` (+ `catalog_phase8_readiness_check.json`)

Phase A (DDS export) and Phase B (vault wiki sign-off) are implemented. Multi-faculty export and RAG indexing are deferred.

**Docker pipeline** (requires `mongo` running):

```bash
docker compose up -d mongo
docker compose run --rm --build data-engineering python -m app.main export-vault-catalog --faculty dds
docker compose run --rm data-engineering python -m app.main import-dds-catalog-staging
docker compose run --rm data-engineering python -m app.main import-technion-courses-staging
docker compose run --rm data-engineering python -m app.main validate-dds-staging-quality
docker compose run --rm data-engineering python -m app.main plan-dds-production-promotion --allow-warnings
docker compose run --rm data-engineering python -m app.main promote-dds-to-production \
  --i-confirm-dangerous-production-write --allow-warnings
```

Vault sign-off is embedded automatically in `export-vault-catalog` output.

## Staging & production commands (catalog)

These commands expect vault-exported JSON (or `--catalog-path` / `--readiness-path` overrides):

| Command | Purpose |
|---------|---------|
| `export-vault-catalog` | Export wiki vault → JSON (includes vault sign-off) |
| `import-dds-catalog-staging` | Upsert programs, requirements, rules into staging |
| `import-technion-courses-staging` | Upsert courses and offerings from semester JSON |
| `validate-dds-staging-quality` | Staging quality report |
| `plan-dds-production-promotion` | Dry-run promotion gate |
| `promote-dds-to-production` | Write staging → production (requires confirmation flag) |
| `rollback-dds-production-promotion` | Roll back a promotion run |

## Health & samples

```bash
python -m app.main health
python -m app.main validate-sample
python -m app.main import-sample
```

## Tests

From repo root (Docker) or locally inside `services/data-engineering`:

```bash
pytest
```

Integration tests for catalog staging use fixtures under `tests/fixtures/` (not live wiki pages).

CI vault export tests use a minimal wiki subset at `tests/fixtures/catalog_vault/` (Phase E.3) so
`pytest` does not depend on the full `data/catalog_valut/` tree.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGO_URI` / `mongo_uri` | `mongodb://localhost:27017/unipilot_python` | MongoDB connection |
| `CATALOG_VAULT_PATH` | `data/catalog_valut` | Wiki vault root |
| `CATALOG_EXPORT_DIR` | `data/generated/technion/catalog` | Wiki export output |

See `.env.example` at repo root.

## Retired (removed)

- `parse-dds-catalog-md`, `curate-dds-catalog`, `signoff-dds-catalog`
- `extract-dds-catalog`, `inspect-dds-catalog`
- `data/raw/technion/technion_dds_catalog_from_docx_clean.md`
- `data/curated/technion/dds_catalog/` reviewed JSON from markdown parser
