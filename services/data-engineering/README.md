# Data Engineering Service (Phase 4 Foundation)

Internal-only Python service for academic data ingestion into **staging** MongoDB collections.

## Scope (Phase 4)

- Staging pipeline foundation (`staging_courses`, `staging_degree_requirements`, `staging_degree_programs`, `staging_catalog_rules`, `staging_ingestion_runs`)
- CLI commands for health checks and **synthetic sample** validation/import
- Normalizer/importer stubs for future Technion DDS sources

**Not in scope yet:** real Technion Faculty of Data and Decision Sciences (DDS) scraping, PDF/HTML parsing, or promotion into production `courses` / `degree_requirements` collections.

## Local source files (Phase 5)

Real Technion inputs (when present on disk):

| Path | Description |
|------|-------------|
| `data/raw/technion/courses_2025_200.json` | Winter semester offerings (200) |
| `data/raw/technion/courses_2025_201.json` | Spring semester offerings (201) |
| `data/raw/technion/courses_2025_202.json` | Summer semester offerings (202) |
| `data/raw/technion/09-מדעי-הנתונים-וההחלטות-תשפ״ו.pdf` | DDS catalog 2025/2026 |

Large raw JSON/PDF files are **gitignored**. See `data/raw/technion/manifest.json` and `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`.

Committed synthetic sample: `data/samples/technion_course_list_synthetic.json`

Manual curation template: `data/samples/dds_catalog_curated_template.json`

## DDS catalog markdown parser (Phase 6.5 / 7)

Preferred source when available: `data/raw/technion/technion_dds_catalog_from_docx_clean.md` (docx export — better structure than raw PDF).

```bash
python -m app.main parse-dds-catalog-md \
  --md-path data/raw/technion/technion_dds_catalog_from_docx_clean.md
```

Environment alternatives: `DDS_CATALOG_MD_PATH`, `--output` (defaults to `data/generated/technion/dds_catalog/dds_catalog_curated_draft.json`).

The parser:

- Splits the document by program code (`009216-1-000`, `009009-1-000`, `009118-1-000`)
- Normalizes course numbers (8-digit `0xxxxxxx`, OCR fixes for trailing zeros / junk prefixes)
- Applies Hebrew RTL cleanup on table cells
- Extracts credit buckets, semester-matrix courses, elective pools, and DS tracks
- Writes **draft** curated JSON matching `dds_catalog_curated_template.json` shape

Phase 6.5 / 7 does **not** write to MongoDB or staging collections. All output is flagged `manualReviewRequired`.

## DDS catalog assisted curation (Phase 7.5)

Enriches the parser draft using DDS markdown plus semester offering JSON (metadata reference only — **not** requirement inference).

```bash
python -m app.main curate-dds-catalog
```

Inputs (local):

- `data/generated/technion/dds_catalog/dds_catalog_curated_draft.json` (parser draft — not overwritten)
- `data/raw/technion/technion_dds_catalog_from_docx_clean.md`
- `data/raw/technion/courses_2025_200.json` (winter), `courses_2025_201.json` (spring), `courses_2025_202.json` (summer)

Outputs (committable):

- `data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json`
- `data/curated/technion/dds_catalog/dds_catalog_curated_review_report.md`

Phase 7.5 does **not** write to MongoDB, staging, or production. Reviewed JSON remains `draft-reviewed-needs-human-signoff` until Phase 7.6 signoff.

## DDS catalog signoff review (Phase 7.6)

Agent-assisted source verification of the Phase 7.5 reviewed catalog against DDS markdown and semester course JSON (metadata only).

```bash
python -m app.main signoff-dds-catalog
```

Inputs:

- `data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json`
- `data/raw/technion/technion_dds_catalog_from_docx_clean.md`
- `data/raw/technion/courses_2025_200.json`, `courses_2025_201.json`, `courses_2025_202.json`

Outputs (committable):

- Updated `data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json` (adds `signoffReview`, updates `curationStatus`)
- `data/curated/technion/dds_catalog/dds_catalog_signoff_review_report.md`
- `data/curated/technion/dds_catalog/dds_catalog_phase8_readiness_check.json`

Phase 7.6 does **not** write to MongoDB, staging, or production. This is not true human approval — staging import may proceed with review flags; production promotion requires human signoff.

## DDS catalog staging import (Phase 8)

Imports the Phase 7.6 reviewed curated catalog into MongoDB **staging collections only**.

```bash
# Dry run (no MongoDB writes)
python -m app.main import-dds-catalog-staging \
  --catalog-path data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json \
  --readiness-path data/curated/technion/dds_catalog/dds_catalog_phase8_readiness_check.json \
  --dry-run

# Real staging import (requires MongoDB)
python -m app.main import-dds-catalog-staging \
  --catalog-path data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json \
  --readiness-path data/curated/technion/dds_catalog/dds_catalog_phase8_readiness_check.json
```

Docker:

```bash
docker compose run --rm data-engineering python -m app.main import-dds-catalog-staging \
  --catalog-path data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json \
  --readiness-path data/curated/technion/dds_catalog/dds_catalog_phase8_readiness_check.json \
  --dry-run
```

**Staging collections written:**

| Collection | Content |
|---|---|
| `staging_degree_programs` | 3 DDS degree programs with full catalog context |
| `staging_degree_requirements` | 41 requirement groups (course refs + review flags) |
| `staging_catalog_rules` | 22 non-executable rule groups (chains, matrices, tracks) |
| `staging_ingestion_runs` | Audit record per import |

**Stable staging keys:** `technion-dds:catalog:2025-2026:program:<code>`, `...:requirement:<groupId>`, `...:rule:<groupId>`.

**Inspect staging (mongosh example):**

```javascript
db.staging_degree_programs.countDocuments({ sourceName: "technion-dds-catalog" })
db.staging_degree_requirements.find({ productionEligible: false }).limit(3)
db.staging_catalog_rules.find({ ruleIsExecutable: false }).limit(3)
```

**Production safety:** importer refuses non-`staging_` collection names and never writes to `degrees`, `degree_requirements`, `courses`, or `catalog`. All documents have `productionEligible: false`.

Phase 8 does **not** expose catalog data via the main API and does **not** implement production promotion.

## Technion course JSON staging import (Phase 9)

Imports local semester offering JSON into MongoDB **staging only**. Course JSON is metadata/offering evidence — **not** used for degree requirement inference.

```bash
# Dry run
python -m app.main import-technion-courses-staging \
  --course-json data/raw/technion/courses_2025_200.json \
  --course-json data/raw/technion/courses_2025_201.json \
  --course-json data/raw/technion/courses_2025_202.json \
  --dry-run

# All courses
python -m app.main import-technion-courses-staging \
  --course-json data/raw/technion/courses_2025_200.json \
  --course-json data/raw/technion/courses_2025_201.json \
  --course-json data/raw/technion/courses_2025_202.json

# DDS faculty only (פקולטה למדעי הנתונים וההחלטות)
python -m app.main import-technion-courses-staging \
  --course-json data/raw/technion/courses_2025_200.json \
  --course-json data/raw/technion/courses_2025_201.json \
  --course-json data/raw/technion/courses_2025_202.json \
  --dds-only
```

**Semester codes:** `200` = winter, `201` = spring, `202` = summer (from filename `courses_2025_<semester>.json`).

**Staging collections:**

| Collection | Content |
|---|---|
| `staging_courses` | Merged course metadata (`technion:course:<courseNumber>`) |
| `staging_course_offerings` | Per-semester schedule/exam evidence |
| `staging_ingestion_runs` | Audit record per import |

Docker mounts `services/data-engineering/data/raw` read-only into the container.

## Staging quality review (Phase 10)

Validates staged DDS catalog data against staged Technion course data. **Report-only** — no automatic corrections.

```bash
python -m app.main validate-dds-staging-quality \
  --output-json data/reports/technion/dds_staging_quality_report.json \
  --output-md data/reports/technion/dds_staging_quality_report.md
```

Optional staging audit snapshot:

```bash
python -m app.main validate-dds-staging-quality --write-staging-audit
```

**Reads:** `staging_degree_programs`, `staging_degree_requirements`, `staging_catalog_rules`, `staging_courses`, `staging_course_offerings`, `staging_ingestion_runs`

**Writes:** local report files; optional `staging_data_quality_reports` only

**Finding severities:** `info`, `warning`, `staging-blocker`, `production-blocker`, `api-migration-blocker`

Production promotion remains blocked until human signoff.

## Staging blocker cleanup (Phase 10.5)

Investigates Phase 10 blockers, applies **source-backed** fixes to curated JSON, then re-imports staging catalog and re-runs quality validation.

```bash
python -m app.main cleanup-dds-staging-blockers --dry-run
python -m app.main cleanup-dds-staging-blockers
python -m app.main import-dds-catalog-staging \
  --catalog-path data/curated/technion/dds_catalog/dds_catalog_curated_reviewed.json \
  --readiness-path data/curated/technion/dds_catalog/dds_catalog_phase8_readiness_check.json
python -m app.main validate-dds-staging-quality
```

Report: `data/reports/technion/dds_staging_blocker_cleanup_report.md`

**No production writes.** Uncertain OCR corrections are **not** applied automatically.

## Human sign-off policy (pre-promotion gate)

Records advisory-only non-executable rules and production-excluded course numbers on curated JSON + staged programs:

```bash
python -m app.main record-dds-human-signoff --signed-off-by "your-name"
python -m app.main import-dds-catalog-staging
python -m app.main validate-dds-staging-quality
```

## Production promotion gate (Phase 11 — dry-run only)

Builds a promotion plan from staging data + quality report + human signoff. **Does not write production collections.**

```bash
python -m app.main plan-dds-production-promotion \
  --output-json data/reports/technion/dds_promotion_plan.json \
  --output-md data/reports/technion/dds_promotion_plan.md \
  --allow-warnings
```

| Gate status | Meaning |
|-------------|---------|
| `pass` | All checks passed; `canPromote: true` for future Phase 12 |
| `pass-with-warnings` | Plan generated; review warnings (e.g. existing production data) |
| `fail` | Blockers present; fix staging/quality/signoff before Phase 12 |

The real promotion command is a **stub** in Phase 11:

```bash
python -m app.main promote-dds-to-production   # exits with refusal message; no writes
```

**Policies:** 22 non-executable rule groups → advisory-only (`catalog_rules`, not mandatory `degree_requirements`). 14 excluded course numbers → skipped from production `courses` with reason `production-excluded-by-human-signoff`.

Reports: `data/reports/technion/dds_promotion_plan.json`, `dds_promotion_plan.md`

## Actual production promotion (Phase 12 — guarded)

```bash
# Refuses (exit 2) — no writes
python -m app.main promote-dds-to-production

# Dry-run through promote command (no writes)
python -m app.main promote-dds-to-production --dry-run

# Real promotion — requires dangerous confirmation flag
python -m app.main promote-dds-to-production --i-confirm-dangerous-production-write
```

Rollback (deletes only documents with matching `promotionRunId`):

```bash
python -m app.main rollback-dds-production-promotion \
  --promotion-run-id dds-promotion-xxxxxxxxxxxx \
  --i-confirm-dangerous-production-write
```

Reports: `data/reports/technion/dds_production_promotion_report.json`, `.md`

**Catalog API migration is still a later phase** — production data is written here; Python catalog APIs read it in a future phase.

## DDS catalog PDF extraction (Phase 6)

Local extraction commands (require the gitignored raw PDF on disk):

```bash
python -m app.main inspect-dds-catalog --pdf-path data/raw/technion/09-מדעי-הנתונים-וההחלטות-תשפ״ו.pdf
python -m app.main extract-dds-catalog --pdf-path data/raw/technion/09-מדעי-הנתונים-וההחלטות-תשפ״ו.pdf
```

Environment alternatives: `DDS_CATALOG_PDF_PATH`, `DDS_CATALOG_OUTPUT_DIR` (see `.env.example`).

Generated artifacts (gitignored): `data/generated/technion/dds_catalog/`

- `extracted_pages.json` / `extracted_pages.txt`
- `extraction_report.json`
- `candidate_sections.json`
- `dds_catalog_curated_draft.json` (from markdown parser)

Phase 6 does **not** write to MongoDB or staging collections. Manual review is required before any requirement staging import.

## CLI Commands

```bash
python -m app.main health
python -m app.main validate-sample
python -m app.main import-sample
python -m app.main parse-dds-catalog-md --md-path data/raw/technion/technion_dds_catalog_from_docx_clean.md
python -m app.main curate-dds-catalog
python -m app.main signoff-dds-catalog
python -m app.main import-dds-catalog-staging --dry-run
python -m app.main import-technion-courses-staging --dry-run
python -m app.main validate-dds-staging-quality
python -m app.main plan-dds-production-promotion --allow-warnings
```

## Docker

```bash
# One-off sample import into staging collections
docker compose run --rm data-engineering python -m app.main import-sample

# Health check
docker compose run --rm data-engineering python -m app.main health

# Phase 11 promotion gate dry-run (requires staging data in MongoDB)
docker compose run --rm data-engineering python -m app.main plan-dds-production-promotion \
  --output-json data/reports/technion/dds_promotion_plan.json \
  --output-md data/reports/technion/dds_promotion_plan.md \
  --allow-warnings
```

The `data-engineering` service is internal-only (no host port). The API containers remain the only public backend endpoints.
