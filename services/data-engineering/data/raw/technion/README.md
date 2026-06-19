# Technion raw sources (local only)

This directory holds **real Technion source files** used for DDS data-engineering intake.

## Expected files

| File | Semester | Description |
|------|----------|-------------|
| `courses_2025_201.json` | Spring (201) | University-wide course offerings for current spring semester |
| `courses_2025_202.json` | Summer (202) | University-wide course offerings for summer semester |
| `09-מדעי-הנתונים-וההחלטות-תשפ״ו.pdf` | Catalog 2025/2026 | DDS faculty degree catalog (programs, tracks, requirements) |

See `manifest.json` for inspection metadata. Field mapping and ingestion design: `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`.

## Git policy

Large JSON/PDF files in this folder are **gitignored** (see root `.gitignore`). Copy them locally after clone; do not commit raw exports unless licensing and course policy explicitly allow it.

## Phase boundary

Phase 5 is **source intake and mapping only**. No MongoDB import, no production promotion, no live scraping.
