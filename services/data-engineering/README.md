# Data Engineering Service (Phase 4 Foundation)

Internal-only Python service for academic data ingestion into **staging** MongoDB collections.

## Scope (Phase 4)

- Staging pipeline foundation (`staging_courses`, `staging_degree_requirements`, `staging_ingestion_runs`)
- CLI commands for health checks and **synthetic sample** validation/import
- Normalizer/importer stubs for future Technion DDS sources

**Not in scope yet:** real Technion Faculty of Data and Decision Sciences (DDS) scraping, PDF/HTML parsing, or promotion into production `courses` / `degree_requirements` collections.

## Local source files (Phase 5)

Real Technion inputs (when present on disk):

| Path | Description |
|------|-------------|
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
```

## Docker

```bash
# One-off sample import into staging collections
docker compose run --rm data-engineering python -m app.main import-sample

# Health check
docker compose run --rm data-engineering python -m app.main health
```

The `data-engineering` service is internal-only (no host port). The API containers remain the only public backend endpoints.
