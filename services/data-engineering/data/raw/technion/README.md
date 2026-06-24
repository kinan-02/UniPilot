# Technion raw sources (local only)

This directory holds **semester offering JSON** used by the semester planner.

## Expected files

Any `courses_YYYY_{200,201,202}.json` file in this directory is imported and exposed to the semester planner (e.g. `courses_2024_201.json` → plan code `2024-2`).

| Pattern | Semester | Description |
|---------|----------|-------------|
| `courses_*_200.json` | Winter (200) | University-wide course offerings |
| `courses_*_201.json` | Spring (201) | University-wide course offerings |
| `courses_*_202.json` | Summer (202) | University-wide summer offerings |

Currently maintained locally: 2023 spring, 2024 all terms, 2025 all terms (see `manifest.json`).

## Catalog data (not in this folder)

Degree programs, requirements, course metadata, and regulations live in the **catalog wiki vault**:

`services/data-engineering/data/catalog_valut/`

See `manifest.json`, `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`, and `docs/planning/CATALOG_VAULT_INTEGRATION_PLAN.md`.

## Git policy

Large JSON files are **gitignored**. Copy them locally after clone.
