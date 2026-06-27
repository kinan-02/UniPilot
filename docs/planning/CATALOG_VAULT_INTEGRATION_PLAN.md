# Catalog Vault Wiki — Integration Plan

Last updated: 2026-06-26  
Status: **Phase A + B implemented for DDS** — vault export with automatic wiki sign-off; **Phase D implemented** (generic faculty exporter + registry; CS reference faculty); **D.6 RAG deferred**.

Related: `services/data-engineering/data/catalog_valut/CLAUDE.md`, `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md`, `docs/DATA_INGESTION_ARCHITECTURE.md`

## 1) Decision summary

UniPilot now uses **two authoritative Technion source families**:

| Concern | Source | Path |
|---------|--------|------|
| Semester offerings (planner) | Technion semester JSON exports | `data/raw/technion/courses_2025_{200,201,202}.json` |
| Catalog knowledge (programs, requirements, courses, regulations, RAG) | Obsidian wiki vault | `data/catalog_valut/wiki/` |

**Retired:** PDF extraction, docx markdown export, and the markdown → curated JSON parser pipeline (`parse-dds-catalog-md`, `curate-dds-catalog`, `signoff-dds-catalog`). Raw catalog PDFs live under `catalog_valut/raw/` for provenance only.

## 2) Vault structure (input contract)

```
catalog_valut/
├── CLAUDE.md           # Wiki schema and ingest rules (human + LLM)
├── raw/                # Immutable source PDFs (read-only)
└── wiki/
    ├── index.md        # Content catalog
    ├── log.md          # Append-only ingest log
    ├── overview.md     # Cross-faculty synthesis
    ├── sources/        # One page per raw source
    ├── entities/       # faculties, tracks, programs, people
    ├── concepts/       # regulations, policies, eligibility
    └── courses/        # One page per course (<code>-<slug>.md)
```

Each wiki page (except `index.md` / `log.md`) carries YAML frontmatter: `title`, `title_he`, `aliases`, `type`, `tags`, optional `faculty`, `course_code`, `credits`, dates.

## 3) Target pipeline

```text
catalog_valut/wiki/          export-vault-catalog CLI
        │                              │
        ▼                              ▼
   (human/LLM curation)     data/generated/technion/catalog/
                            ├── catalog_reviewed.json
                            └── catalog_phase8_readiness_check.json
                                        │
                                        ▼
                            import-dds-catalog-staging  (existing)
                                        │
                                        ▼
                            staging_* collections
                                        │
                                        ▼
                            promote-dds-to-production   (existing)
                                        │
                                        ▼
                            production collections → FastAPI /catalog/*
```

Semester JSON follows the **existing** path unchanged:

```text
courses_2025_*.json → import-technion-courses-staging → staging_courses / staging_course_offerings
```

## 4) Implementation phases

### Phase A — Vault export (wiki → JSON)

**Goal:** Replace the retired markdown parser with a deterministic wiki reader.

| Task | Details |
|------|---------|
| A.1 Wiki page loader | Walk `wiki/entities/`, `wiki/courses/`, `wiki/concepts/`; parse YAML frontmatter + markdown body |
| A.2 Entity resolver | Map `[[wikilink]]` to slugs; build alias index from frontmatter |
| A.3 Track → program mapper | Read `track-*.md` semester tables; emit `degree_programs` + `degree_requirements` + `catalog_rules` matching existing `ReviewedCuratedCatalogDocument` schema |
| A.4 Course mapper | Read `wiki/courses/*.md`; emit course records with prerequisites, track placement, credits |
| A.5 Concept → advisory rules | Map `wiki/concepts/*.md` to `catalog_rules` with `advisoryOnly: true` where appropriate |
| A.6 JSON enricher | Cross-reference semester JSON for `titleHint`, `creditsHint`, `semestersOffered`, prerequisites text (metadata only — requirements stay wiki-sourced) |
| A.7 CLI | `python -m app.main export-vault-catalog [--vault-path] [--faculty dds] [--output]` |
| A.8 Unit tests | Fixtures: 2–3 wiki pages → expected JSON fragments; golden test against DDS track page |

**Acceptance:** `export-vault-catalog` produces `catalog_reviewed.json` that passes existing `import-dds-catalog-staging --dry-run` for DDS.

### Phase B — Readiness & vault sign-off (implemented for DDS)

**Goal:** Replace manual Phase 7.6 human sign-off with vault-backed checks.

| Task | Status |
|------|--------|
| B.1 Readiness generator | Done — export validates program codes, credits, course numbers |
| B.2 Source provenance | Done — `wikiSourceRefs` on programs and requirement groups |
| B.3 Vault sign-off | Done — applied automatically in `export-vault-catalog` (no `record-dds-human-signoff` step) |
| B.4 Blocker cleanup refresh | Done — title enrichment from wiki course pages |

**Deferred (later):** Phase D.6 RAG indexing; per-faculty specialized elective-chain exporters beyond generic Pass-1.

### Phase D — Multi-faculty expansion (implemented; RAG deferred)

| Task | Status | Details |
|------|--------|---------|
| D.1 Faculty export registry | Done | `vault_export_registry.py` routes `export-vault-catalog --faculty <id>`; DDS + 15 generic faculties registered |
| D.2 Per-faculty elective chain contract | Done | `data/contracts/elective_chain_pools.json` (v2, `institutionId: technion`, `faculties.<id>.pools`); validated at export, staging quality, API/web regression |
| D.3 Ops verification | Done | `scripts/verify_elective_chains.py` (+ CI + `production_audit.py`); `--faculty dds` or `--faculty all` |
| D.4 Incremental faculty ingest | Done | `export_faculty_vault_catalog.py` (generic Pass-1); per-faculty output under `data/generated/technion/catalog/<faculty>/`; staging keys `technion-<faculty>:catalog:...` |
| D.5 API catalog scope | Done | `/catalog/degree-programs?facultyId=` filter; `track_registry` + web `academicPath` resolve `metadata.wikiPage` for any `track-*` slug |
| D.6 RAG index | Deferred | Chunk `wiki/` pages for future AI advisor; cite `[[source]]` links |
| D.7 Curriculum E2E verification | Done | `scripts/verify_promoted_faculty_curriculum.py` (17 faculties); `scripts/promote_and_verify_faculty.sh`; alias tracks via `curriculumWikiSlug` + API path-option resolution |

**Reference second faculty:** Computer Science (`--faculty computer-science`) — 7 BSc track programs exported (e.g. `023023-1-000`).

**Onboarding a new faculty:** (1) expand `catalog_valut/wiki/`, (2) register in `vault_export_registry.py` (or use generic exporter if track pages follow the schema), (3) add `faculties.<id>` contract block if chain pools exist, (4) `bash scripts/promote_and_verify_faculty.sh <faculty-id>` (or manual export → import → quality → promote).

**Multi-faculty promotion notes:**

- Run `import-technion-courses-staging` once (full Technion scope, not `--dds-only`) before promoting non-DDS faculties so matrix courses exist in staging/production.
- Faculty exports set `ingestibleCourseScope: technion-semester-json`; the promotion gate validates excluded-course lists against that scope.
- Duplicate cross-faculty programs (e.g. dual-degree tracks) export once from the canonical wiki page; alias path options carry `curriculumWikiSlug` for API onboarding.

### Phase C — Staging & production (complete)

End-to-end vault pipeline verified and promoted in Docker:

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

**Computer Science (second faculty) — same pipeline with explicit paths and `--faculty`:**

```bash
docker compose run --rm data-engineering python -m app.main export-vault-catalog --faculty computer-science
docker compose run --rm data-engineering python -m app.main import-dds-catalog-staging \
  --catalog-path data/generated/technion/computer-science/catalog_reviewed.json \
  --readiness-path data/generated/technion/computer-science/catalog_phase8_readiness_check.json
docker compose run --rm data-engineering python -m app.main validate-dds-staging-quality --faculty computer-science
docker compose run --rm data-engineering python -m app.main plan-dds-production-promotion --faculty computer-science --allow-warnings
docker compose run --rm data-engineering python -m app.main promote-dds-to-production \
  --faculty computer-science --i-confirm-dangerous-production-write --allow-warnings
```

**Production promotion run:** `dds-promotion-ece45363bbf2` (2026-06-21; supersedes `dds-promotion-8aeb5595517d`)

| Collection | Count |
|------------|-------|
| `degree_programs` | 3 |
| `degree_requirements` | 19 (executable) |
| `catalog_rules` | 35 (advisory; one `advisory_requirement_group` per group) |
| `courses` | 2,068 |
| `course_offerings` | 2,638 |

**Duplicate cleanup:** Earlier promotions wrote both `recordType: catalog_rule` and `recordType: advisory_requirement_group` for the same `requirementGroupId` (70 MongoDB documents, 35 unique groups). The promotion gate now skips redundant `catalog_rule` writes when the group is already planned as `advisory_requirement_group`, and `promote-dds-to-production` deletes superseded `catalog_rule` rows **before** validation so idempotent re-promotion succeeds. The API repository also dedupes by `requirementGroupId` on read as a safety net.

Vault sign-off (`vaultSignoff.signedOffBy=vault-wiki`) is stored on production programs under `sourceMetadata.curationReport`. 41 catalog-only course refs were skipped (not in 2025 semester JSON).

**API smoke test** (2026-06-21, full stack `docker compose up`):

| Check | Result |
|-------|--------|
| `GET /health` | ok (mongo + redis connected) |
| `GET /catalog/degree-programs` | 3 DDS programs |
| Hard requirements (all programs) | 19 total (7 + 6 + 6) |
| Advisory rules (all programs) | 35 total (unique groups; deduped in Mongo) |
| `GET /catalog/courses/00940345` | title + 4.0 credits |
| `GET /catalog/courses/00960226` | 404 (production-excluded) |
| `GET /catalog/courses` | 2,068 courses |
| `verify_and_benchmark.py` | 86 passed, 0 failed, 0 warnings |

### Phase E — Docker & ops (partial)

| Task | Status |
|------|--------|
| E.1 Mount vault in data-engineering container | Done — `catalog_valut/` and `data/generated/` mounted |
| E.2 README / `.env.example` | Done — export → import → promote flow documented |
| E.3 CI fixture | Done — minimal wiki subset under `tests/fixtures/catalog_vault/` |
| E.4 Elective chain contract CI gate | Done — `verify_elective_chains.py` in data-engineering job + `production_audit.py` |

## 5) Schema mapping (wiki → MongoDB)

### Track pages → `degree_programs`

From frontmatter + body:

- `program code` → `programCode` (e.g. `009216-1-000`)
- `title` / `title_he` → `name` / `nameHe`
- Credit breakdown table → requirement group seeds

### Track semester tables → `degree_requirements`

| Wiki table column | Staging field |
|-------------------|---------------|
| Code | `courseReferences[].courseNumber` |
| Credits | `courseReferences[].creditsHint` |
| Semester N section | `groupId: <program>:semester-N-matrix` |
| Notes / `*` markers | `catalog_rules` or `manualReviewRequired` flags |

### Course pages → `courses`

- Frontmatter `course_code`, `credits`
- Body sections: prerequisites, track placement, related courses
- Enrich from semester JSON when course appears in offerings

### Concept pages → `catalog_rules`

- Regulations, adaptations, specializations → advisory rules with `enforceInGraduationProgress: false`

## 6) What we keep vs remove

| Keep | Remove (done) |
|------|---------------|
| `catalog_valut/` wiki + raw | `technion_dds_catalog_from_docx_clean.md` |
| Semester JSON importers | `technion_dds_catalog_pdf.py`, markdown parser |
| Staging + promotion pipeline | `curate-dds-catalog`, `signoff-dds-catalog`, `parse-dds-catalog-md` |
| `dds_catalog_staging_importer.py` | `data/curated/technion/dds_catalog/*` |
| Test fixtures for staging | PDF/markdown extraction artifacts in `raw/technion/` |

## 7) Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Wiki tables parsed incorrectly | Golden tests per track; dry-run staging import before promotion |
| Vault and MongoDB drift | Re-export on vault `updated` date change; version `catalogVersion` in export metadata |
| Multi-faculty course code collisions | Course codes are Technion-unique; faculty tag on program records |
| LLM-edited wiki introduces errors | Human curates `raw/`; wiki export is deterministic (no LLM at import time) |

## 8) Immediate next step

DDS vault integration Phases A–C are **complete**, including production promotion, live API smoke tests, CI vault fixtures, and planner E2E. Optional follow-ups:

1. **Phase D** (deferred) — multi-faculty export and RAG indexing when needed
2. Re-run export → promote when wiki track pages change (`updated` date in frontmatter)

## 9) Success criteria

- [x] No dependency on retired markdown/PDF parser paths
- [x] `export-vault-catalog` produces import-ready JSON from current DDS wiki pages
- [x] Semester planner continues to use only `courses_2025_*.json`
- [x] Documentation reflects two-source model
- [x] Integration tests use wiki fixtures, not markdown fixtures
- [x] Vault sign-off replaces manual human sign-off for DDS
- [x] Production MongoDB promoted from vault export (`catalog_rules`: 35 advisory groups, 19 hard requirements)
- [x] Live `/catalog/*` API smoke tests pass against promoted data
- [x] CI vault fixture at `tests/fixtures/catalog_vault/` (Phase E.3)
- [x] API test fixtures seed 70 unique advisory group IDs for integration coverage (broader than live production)
- [x] Playwright planner E2E against live promoted catalog (`e2e/planner-catalog.spec.ts`)
- [x] Promotion dedupe: gate skip + pre-validation cleanup of superseded `catalog_rule` documents
