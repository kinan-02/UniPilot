# Technion raw sources (local only)

This directory holds **semester offering JSON** used by the semester planner.

## Expected files

| File | Semester | Description |
|------|----------|-------------|
| `courses_2025_200.json` | Winter (200) | University-wide course offerings |
| `courses_2025_201.json` | Spring (201) | University-wide course offerings |
| `courses_2025_202.json` | Summer (202) | University-wide summer offerings |

## Catalog data (not in this folder)

Degree programs, requirements, course metadata, and regulations live in the **catalog wiki vault**:

`services/data-engineering/data/catalog_valut/`

See `manifest.json`, `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`, and `docs/planning/CATALOG_VAULT_INTEGRATION_PLAN.md`.

## Git policy

Large JSON files are **gitignored**. Copy them locally after clone.
