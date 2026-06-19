# Data Engineering Service (Phase 4 Foundation)

Internal-only Python service for academic data ingestion into **staging** MongoDB collections.

## Scope (Phase 4)

- Staging pipeline foundation (`staging_courses`, `staging_degree_requirements`, `staging_ingestion_runs`)
- CLI commands for health checks and **synthetic sample** validation/import
- Normalizer/importer stubs for future Technion DDS sources

**Not in scope yet:** real Technion Faculty of Data and Decision Sciences (DDS) scraping, PDF/HTML parsing, or promotion into production `courses` / `degree_requirements` collections.

## CLI Commands

```bash
python -m app.main health
python -m app.main validate-sample
python -m app.main import-sample
```

## Docker

```bash
# One-off sample import into staging collections
docker compose run --rm data-engineering python -m app.main import-sample

# Health check
docker compose run --rm data-engineering python -m app.main health
```

The `data-engineering` service is internal-only (no host port). The API containers remain the only public backend endpoints.
