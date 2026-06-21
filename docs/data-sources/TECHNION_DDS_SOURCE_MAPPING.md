# Technion DDS Source Mapping

Last updated: 2026-06-21

Maps Technion academic sources to UniPilot normalized models and MongoDB production collections. Consumed by `services/data-engineering` (import/promotion) and `services/api` (read APIs).

Related: `docs/planning/CATALOG_VAULT_INTEGRATION_PLAN.md`, `docs/planning/REAL_DATA_ALIGNMENT_PLAN.md`, `services/data-engineering/data/raw/technion/manifest.json`, `services/data-engineering/README.md`

## Authoritative sources (2026-06-21)

| Concern | Source | Path |
|---------|--------|------|
| Semester planner (offerings, groups, schedules) | Technion semester JSON exports | `data/raw/technion/courses_2025_{200,201,202}.json` |
| Catalog (programs, requirements, courses, regulations) | Obsidian wiki vault | `data/catalog_valut/wiki/` |

### Semester JSON

| File | Semester | Scope |
|------|----------|-------|
| `courses_2025_200.json` | Winter (200) | University-wide offerings |
| `courses_2025_201.json` | Spring (201) | University-wide offerings |
| `courses_2025_202.json` | Summer (202) | University-wide summer offerings |

**CLI:** `python -m app.main import-technion-courses-staging`

**Maps to:** `staging_courses`, `staging_course_offerings` → production `courses`, `course_offerings`

**Rules:**

- Offering snapshots only — not degree requirements.
- Merges duplicate courses across semester files.
- Enriches metadata (`title`, credits, prerequisites text, faculty) when numbers match.

### Catalog wiki vault

| Path | Description |
|------|-------------|
| `data/catalog_valut/CLAUDE.md` | Wiki schema, naming, ingest protocol |
| `data/catalog_valut/raw/` | Immutable source PDFs (provenance) |
| `data/catalog_valut/wiki/entities/` | Faculties, tracks, programs |
| `data/catalog_valut/wiki/courses/` | Course pages (`<code>-<slug>.md`) |
| `data/catalog_valut/wiki/concepts/` | Regulations, policies, specializations |
| `data/catalog_valut/wiki/index.md` | Content catalog |

**Planned CLI:** `export-vault-catalog` → `data/generated/technion/catalog/catalog_reviewed.json`

**Maps to:** `staging_degree_programs`, `staging_degree_requirements`, `staging_catalog_rules` → production equivalents

**Rules:**

- Wiki is source of truth for degree requirements and program structure.
- Semester JSON enriches course metadata only (same boundary as before).
- Export is deterministic (no LLM at import time).

See `docs/planning/CATALOG_VAULT_INTEGRATION_PLAN.md` for implementation phases.

## Active pipeline (staging → production)

| Command | Purpose |
|---------|---------|
| `import-technion-courses-staging` | Semester JSON → staging courses/offerings |
| `import-dds-catalog-staging` | Vault-export JSON → staging programs/requirements |
| `validate-dds-staging-quality` | Cross-link and quality reports |
| `export-vault-catalog` | Wiki vault → reviewed JSON (includes sign-off) |
| `plan-dds-production-promotion` | Promotion gate dry-run |
| `promote-dds-to-production` | Staging → production (guarded) |

## Retired sources (removed 2026-06-21)

| Removed | Replacement |
|---------|-------------|
| `technion_dds_catalog_from_docx_clean.md` | `catalog_valut/wiki/` |
| `09-מדעי-הנתונים-וההחלטות-תשפ״ו.pdf` in `raw/technion/` | `catalog_valut/raw/` |
| `parse-dds-catalog-md`, `curate-dds-catalog`, `signoff-dds-catalog` | `export-vault-catalog` (planned) |
| `data/curated/technion/dds_catalog/*.json` | `data/generated/technion/catalog/` (wiki export) |

---

## Historical phase notes (6–7.6 retired)

<details>
<summary>Phases 6–7.6 — markdown/PDF parser pipeline (superseded)</summary>

These phases implemented PDF extraction, markdown parsing, assisted curation, and agent signoff. Code and data were removed when the catalog wiki vault became authoritative. Phase 8+ staging/promotion commands remain active; input is transitioning to vault export JSON.

</details>

## Phase 8 update (DDS catalog staging import)
| Command | Purpose |
|---------|---------|
| `python -m app.main import-dds-catalog-staging --catalog-path … --readiness-path …` | Upsert reviewed catalog into staging collections |
| `… --dry-run` | Validate inputs and print counts without MongoDB writes |

| Staging collection | Records (Technion DDS 2025-2026) |
|---|---|
| `staging_degree_programs` | 3 programs |
| `staging_degree_requirements` | 51 requirement groups (16 hard + 35 advisory) |
| `staging_catalog_rules` | Legacy only — vault import no longer dual-writes here |
| `staging_ingestion_runs` | 1 audit record per import |

**Rules:**

- Requires vault-export JSON with `signoffReview` and `canImportToStaging: true` in readiness JSON.
- Rejects `production-ready` curation status and `canPromoteToProduction: true`.
- Every document: `isStaging: true`, `productionEligible: false`, `requiresHumanSignoff: true`.
- Idempotent re-import via stable `stagingKey` values.
- **No production collection writes.** Main API still does not expose catalog data.

## Phase 9 update (Technion course JSON staging import)

| Command | Purpose |
|---------|---------|
| `python -m app.main import-technion-courses-staging --course-json …` | Upsert semester JSON courses/offerings into staging |
| `… --dry-run` | Validate and count without MongoDB writes |
| `… --dds-only` | Import only DDS faculty courses |

| Staging collection | Content |
|---|---|
| `staging_courses` | Merged Technion course metadata per `courseNumber` |
| `staging_course_offerings` | Per-semester schedule/exam snapshots |
| `staging_ingestion_runs` | Audit record per import |

**Rules:**

- Semester codes: `200` winter, `201` spring, `202` summer (from filename).
- Course JSON is offering evidence only — never used to infer degree requirements.
- Duplicate `courseNumber` values merge across files; title/credit conflicts produce warnings.
- All documents: `isStaging: true`, `productionEligible: false`, `requiresHumanReview: true`.
- Raw JSON under `data/raw/technion/` stays gitignored; Docker mounts it read-only.

## Phase 10 update (staging quality review — report only)

| Command | Purpose |
|---------|---------|
| `python -m app.main validate-dds-staging-quality` | Cross-validate staged DDS catalog vs staged courses |
| `… --output-json data/reports/technion/dds_staging_quality_report.json` | Machine-readable report |
| `… --output-md data/reports/technion/dds_staging_quality_report.md` | Human-readable report |
| `… --write-staging-audit` | Optional snapshot in `staging_data_quality_reports` |

**Checks:** program/requirement counts, signoff metadata, course-reference coverage, OCR-suspect gaps, title/credit mismatches, non-executable rules, `productionEligible: false`, production collection counts (read-only).

**Severities:** `info`, `warning`, `staging-blocker`, `production-blocker`, `api-migration-blocker`

**No automatic fixes.** Production promotion remains blocked until Phase 12 after explicit approval.

## Phase 10.5 (retired)

Blocker cleanup and manual human sign-off CLIs were removed after the catalog wiki vault became authoritative. Use `export-vault-catalog` for sign-off and re-run staging import when catalog JSON changes.

## Phase 11 update (promotion gate — dry-run plan only)

| Command | Purpose |
|---------|---------|
| `python -m app.main plan-dds-production-promotion` | Build promotion gate verdict + dry-run plan (no production writes) |
| `… --output-json data/reports/technion/dds_promotion_plan.json` | Machine-readable plan |
| `… --output-md data/reports/technion/dds_promotion_plan.md` | Human-readable plan |
| `… --strict` | Fail gate when warnings are present |
| `… --allow-warnings` | Allow `pass-with-warnings` (default) |
| `python -m app.main promote-dds-to-production` | **Stub** — refuses; Phase 12 only |

**Policies enforced:**

- `nonExecutableRulesPolicy: advisory-only` — semester matrices, elective pools, DS tracks, IE/IS chains promoted as advisory metadata only (`enforceInGraduationProgress: false`).
- `productionExcludedCoursePolicy: omit-from-production-do-not-ingest` — 14 cross-link gap course numbers must not appear in planned production `courses` writes.

**Target production collections (defined, not populated in Phase 11):** `degree_programs`, `degree_requirements`, `catalog_rules`, `courses`, `course_offerings`.

**Gate checks:** staging structure (3 programs, 41 requirement groups, courses/offerings present), latest quality metrics (no production blockers, zero title/credit/chain/OCR issues), human signoff metadata, staging safety flags (`isStaging: true`, `productionEligible: false`), production collection counts unchanged.

## Phase 12 update (guarded production promotion)

| Command | Purpose |
|---------|---------|
| `python -m app.main promote-dds-to-production` | **Refuses** without dangerous confirmation flag |
| `… --dry-run` | Re-run gate + build production docs; no writes |
| `… --i-confirm-dangerous-production-write` | Promote staging → production after gate passes |
| `python -m app.main rollback-dds-production-promotion --promotion-run-id <id> --i-confirm-dangerous-production-write` | Delete only docs from that promotion run |

**Production collections written:** `degree_programs`, `degree_requirements`, `catalog_rules`, `courses`, `course_offerings`, plus audit `promotion_runs`.

**Stable keys (idempotent upsert):** `technion-dds:program:…`, `technion-dds:requirement:…`, `technion-dds:advisory-rule:…`, `technion:course:…`, `technion:course-offering:…`.

**Safety:** empty production collections required on first promotion; re-promotion allowed when all existing docs match planned keys. Foreign/conflicting production data aborts before writes. Excluded courses and advisory-only rules enforced as in Phase 11.

Reports: `data/reports/technion/dds_production_promotion_report.json`, `.md`

## Phase 13 update (Python read-only catalog API)

The Python API (`services/api`) exposes read-only catalog routes under `/catalog/*`, reading production collections promoted in Phase 12. Hard requirements (`degree_requirements`) and advisory rules (`catalog_rules`) are separate endpoints; advisory rules always expose `enforceInGraduationProgress: false`.

## Phase 6 update (PDF extraction — retired)

<details>
<summary>Historical — superseded by catalog vault</summary>

Phase 6 PDF extraction commands (`inspect-dds-catalog`, `extract-dds-catalog`) and related code were removed 2026-06-21. Catalog PDFs live under `catalog_valut/raw/`.

</details>

---

## 1) Purpose

Document the structure of **local Technion source files**, map fields to UniPilot normalized models, and list gaps/risks before staging or production import.

---

## 2) Source inventory

| File / path | Type | Scope |
|-------------|------|-------|
| `data/raw/technion/courses_2025_200.json` | JSON | Winter (200) semester offerings — university-wide |
| `data/raw/technion/courses_2025_201.json` | JSON | Spring (201) semester offerings — university-wide |
| `data/raw/technion/courses_2025_202.json` | JSON | Summer (202) semester offerings — university-wide |
| `data/catalog_valut/wiki/` | Markdown wiki | Catalog knowledge — programs, tracks, requirements, courses, regulations |
| `data/catalog_valut/raw/*.pdf` | PDF | Immutable catalog source documents (provenance) |

### Semester code convention

| File suffix | Meaning | Example `semesterCode` |
|-------------|---------|------------------------|
| `200` | Winter (חורף) | `2025-200` |
| `201` | Spring (אביב) | `2025-201` |
| `202` | Summer (קיץ) | `2025-202` |

### Cross-semester overlap (course numbers)

| Set | Count |
|-----|-------|
| Only in spring 201 | 1,214 |
| Only in summer 202 | 18 |
| In both | 75 |

**Implication:** JSON files are **term offerings**, not a canonical full catalog. A course may appear in one semester file, both, or neither.

### DDS subset in spring JSON

| Metric | Spring 201 |
|--------|------------|
| Courses where `פקולטה` = `הפקולטה למדעי הנתונים וההחלטות` | **108** |
| Courses with number prefix `0096` (DDS-heavy) | 39 (university-wide) |
| Distinct faculties in spring file | 23 |

---

## 3) Course JSON — top-level structure

Each file is a **JSON array**. Every element:

```json
{
  "general": { /* Hebrew-keyed course metadata */ },
  "schedule": [ /* 0..N meeting slots */ ]
}
```

Optional extension used only in committed samples: top-level `_metadata` (synthetic tests).

---

## 4) Course JSON — `general` fields

### 4.1 Field inventory

| Hebrew key | English meaning | Spring 201 | Summer 202 | Notes |
|------------|-----------------|------------|------------|-------|
| `מספר מקצוע` | Course number | 100% | 100% | 8-digit string, unique per file |
| `שם מקצוע` | Course title | 100% | 100% | Hebrew; rare Latin in title (5 in 201) |
| `סילבוס` | Syllabus / description | 100% | 100% | Max ~1,200 chars in sample; 22 empty in 201 |
| `פקולטה` | Faculty | 100% | 100% | Owning faculty name |
| `מסגרת לימודים` | Study framework | 100% | 100% | e.g. `לימודי הסמכה`, `מקצוע משותף`, `תארים מתקדמים` |
| `מקצועות קדם` | Prerequisites | 65% | 68% | **Free-text** Boolean expressions |
| `מקצועות ללא זיכוי נוסף` | No additional credit (overlap) | 37% | 46% | Space-separated course numbers |
| `מקצועות ללא זיכוי נוסף (מוכלים)` | Overlap (contained) | rare | present | Subset of overlap rules |
| `מקצועות ללא זיכוי נוסף (מכילים)` | Overlap (container) | rare | present | Subset of overlap rules |
| `מקצועות צמודים` | Adjacent / paired courses | 1% | — | **Spring 201 only** (13 records) |
| `נקודות` | Credit points | 100% | 100% | String decimal (`"3"`, `"3.5"`, `"0.5"`) |
| `אחראים` | Instructors in charge | 48% | 63% | Often empty |
| `הערות` | Notes | 41% | 31% | Free text; may duplicate adjacent-course hints |
| `מועד א` | Exam date A | 36% | 44% | `DD-MM-YYYY` |
| `מועד ב` | Exam date B | 36% | 44% | 52 summer courses lack exam A |
| `בוחן מועד א` | Midterm exam A | rare | — | **Spring 201 only** |

### 4.2 Course identifier

| Source | Format | Example | Normalization rule (proposed) |
|--------|--------|---------|-------------------------------|
| `מספר מקצוע` | 8-digit string | `00940139` | `subject` = first 4 digits (`0094`), `number` = last 4 (`0139`) |
| PDF inline numbers | Often 7 digits | `0960412` | Left-pad to 8 → `00960412` before split |

`institutionId`: `technion`  
Canonical catalog key (aligned with `NormalizedCourse.staging_key`):  
`technion:{subject}:{number}:{catalogVersion}`

### 4.3 Credits / points

- Always string in source; values observed: `0`, `0.5`, `1`, `1.5`, `2`, `2.5`, `3`, `3.5`, `4`, `4.5`, `5`, `5.5`, `6`, `8`
- Maps to `NormalizedCourse.credits` (float)

### 4.4 Faculty / department

- `פקולטה` is the primary faculty label (not a stable code)
- DDS faculty string: `הפקולטה למדעי הנתונים וההחלטות`
- Schedule rows may reference buildings such as `קופר- מדעי הנתונים`

### 4.5 Prerequisites / corequisites

**Prerequisites (`מקצועות קדם`):**

- Free-text Hebrew with `או` (OR), `ו-` / `ו` (AND), parentheses
- Contains **course numbers embedded in text**, not MongoDB ObjectIds
- Examples:
  - `01040044 או 01040022 או 01040004`
  - `(00940313 ו-00940411) או (00940313 ו-00940412)`
  - Max string length observed: **392** characters

**Not the same as `NormalizedCourse.prerequisiteCourseIds`**, which today expects 24-char ObjectId strings.

**Adjacent courses (`מקצועות צמודים`):** single course number string — treat as corequisite/pairing hint.

**No additional credit (`מקצועות ללא זיכוי נוסף`):** overlap / mutual-exclusion rules — not modeled in `NormalizedCourse` today.

### 4.6 Schedule / exam / groups — `schedule[]`

| Hebrew key | Meaning | Type notes |
|------------|---------|------------|
| `קבוצה` | Group / section | int |
| `סוג` | Session type | `הרצאה`, `תרגול`, `מעבדה`, `פרויקט`, `סמינר`, plus sports entries |
| `יום` | Day | Hebrew weekday |
| `שעה` | Time range | e.g. `14:30 - 16:30` |
| `בניין` | Building | may be empty |
| `חדר` | Room | int; `0` when unknown |
| `מרצה/מתרגל` | Instructor | string |
| `מס.` | Sequence / slot id | int |

**Stats (spring 201):** 0–44 slots per course; avg ~2.9; **142** courses with empty `schedule`.

**Exam dates** live under `general`, not `schedule`.

### 4.7 Hebrew / English

| Field | Hebrew | English |
|-------|--------|---------|
| Titles, syllabus, faculty | Primary | Essentially absent (5 titles with Latin chars in spring) |
| PDF narrative | Hebrew (+ some English program names) | Partial |

### 4.8 Missing / inconsistent data

| Issue | Impact |
|-------|--------|
| Empty `סילבוס` (22 in 201) | Need fallback description or reject |
| Empty `אחראים` (~50%+) | OK for catalog; useful for offerings |
| Empty `schedule` (142 in 201) | Offering record still valid; planner needs offering optional |
| Credits as strings | Parse to float |
| Prerequisites as prose | Requires dedicated parser + catalog resolution |
| University-wide dump vs DDS-only | Must filter by faculty/program for DDS import |
| Summer file missing some spring-only fields | Normalizer must tolerate optional keys |
| Course in JSON may not appear in PDF elective lists (and vice versa) | Merge strategy needed later |

---

## 5) DDS catalog PDF — inspection summary

### 5.1 Extraction feasibility

| Tool | Result |
|------|--------|
| `pypdf` text extraction | **Works** — all 13 pages yield text (~4,300 chars/page avg) |
| Hebrew readability | **Poor** — RTL / visual-order reversal on many lines |
| Tables | **Partial** — course lists and semester matrices extract as lines, not structured tables |
| Warnings | Multiple `Ignoring wrong pointing object` PDF structure warnings |

**Conclusion:** Text extraction is **feasible** for discovery and RAG chunks, but **not sufficient** for reliable structured import without:

- Better extractor (`pymupdf` / `pdfplumber`) with RTL post-processing, and/or
- Manual curation for requirement tables, and/or
- Hybrid table OCR for semester matrices (pages 5–8)

### 5.2 Document sections identified

| Section | Pages (approx.) | Content |
|---------|-----------------|---------|
| Faculty introduction | 1–2 | Mission, DDS scope, English program names |
| **Data Science & Engineering** track | 3–4 | Program code `009216-1-000`, credit totals, elective pools, course list |
| **Management & Operations Engineering** | 5–6 | Program code `009009-1-000`, semester tables, faculty electives |
| **Information Systems Engineering** | 7–8 | Program code `009118-1-000`, semester tables |
| Cross-faculty / track tables | 9–11 | Dense course-number tables (multi-faculty) |
| Policies / notes | 12–13 | Narrative rules, footnotes (`*`, `**`, `***`) |

### 5.3 Degree programs / tracks (PDF)

| Program code (PDF) | Program (inferred) | Catalog year |
|--------------------|-------------------|--------------|
| `009216-1-000` | הנדסה ומדעי הנתונים (Data Science & Engineering) | 2025/2026 |
| `009009-1-000` | הנדסה וניהול שיטות (Management & Operations Engineering) | 2025/2026 |
| `009118-1-000` | הנדסת מערכות מידע (Information Systems Engineering) | 2025/2026 |

These map to a future **`NormalizedDegreeProgram`** / `degrees.code` — not present in Phase 4 models.

### 5.4 Degree requirements (PDF)

Example — Data Science & Engineering (`009216-1-000`, page 3):

| Requirement bucket | Credits (נ״ז) | Notes |
|--------------------|-----------------|-------|
| Total degree | **155.0** | Overall BSc |
| Mandatory (`חובה`) | **108.0** | Includes faculty core |
| Data-science electives | **24.5** | Listed course pool |
| Faculty electives | **10.5** | |
| General electives | **12.0** | |
| Humanities (`#`) | **6.0** | Footnote marker |
| Physical education (`##`) | **2.0** | Footnote marker |

**Requirement types in PDF:**

- Mandatory courses by semester (`רטסמס` 5–8 matrices)
- **Elective pools** — choose N courses from long lists (pages 4, 6–7)
- **Track / chain selection** — e.g. statistics vs operations research chains
- **Capstone / project** sequences (`פרויקט תכן`, `טקיורפ`)
- Free-choice rules with minimum credits

**Parsing difficulty:** High — tables mix semester index, credits, course numbers, and footnote markers (`*`, `&`, `&&`).

### 5.5 Course requirement groups

- Page 4: elective list for DS track (course numbers `00960401`, `00970412`, …)
- Pages 6–7: faculty-elective groups with “choose 1 from list”, “choose 3 from chain”
- Pages 9–11: large cross-program tables — likely need **manual extraction** or semi-automated curation

### 5.6 Free choice / electives

Represented as:

- Credit minimums without fixed course lists (`ללכ הריחב` — general electives)
- Named pools with course lists (faculty / DS electives)
- “Pick one course from statistics chain” style rules

Maps best to `NormalizedDegreeRequirement` with `requirementType: elective` and `ruleExpression` such as `{ type: "course_pool", operator: "choose_n" }` — **not implemented today**.

---

## 6) Field mapping — `NormalizedCourse`

Target model: `services/data-engineering/app/models/normalized_course.py`

| NormalizedCourse field | Source | Transform / notes |
|------------------------|--------|-------------------|
| `institutionId` | constant | `"technion"` |
| `subject` | `מספר מקצוע` | chars 0–3 |
| `number` | `מספר מקצוע` | chars 4–7 |
| `title` | `שם מקצוע` | direct |
| `credits` | `נקודות` | `float()` |
| `description` | `סילבוס` | direct; reject or placeholder if empty |
| `level` | `מסגרת לימודים` | map e.g. `לימודי הסמכה` → `undergraduate` |
| `tags` | derived | faculty prefix, semester code, `dds` if applicable |
| `prerequisiteCourseIds` | `מקצועות קדם` | **GAP** — needs parser → course numbers → catalog ObjectIds at import time |
| `corequisiteCourseIds` | `מקצועות צמודים` | **GAP** — same; often single number string |
| `catalogYear` | file metadata | `2025` from `courses_2025_*` |
| `catalogVersion` | manifest | e.g. `2025-201` or `2025-2026` |
| `version` | manifest | align with `catalogVersion` |
| `status` | constant | `staging` until promoted |
| `metadata` | multiple | `faculty`, `studyFramework`, `notes`, `overlapRules`, `isRealTechnionData: true` |
| `sourceRefs` | file path | e.g. `locator: course:00940139@2025-201` |

### Fields **not** in `NormalizedCourse` (belong elsewhere)

| Source data | Proposed future model |
|-------------|----------------------|
| `schedule[]` | `NormalizedCourseOffering` / `course_offerings` |
| `מועד א` / `מועד ב` | offering or exam metadata on offering |
| `אחראים`, per-slot instructors | offering |
| `מקצועות ללא זיכוי נוסף` | `metadata.overlapRules` or `NormalizedCourseOverlapRule` |
| Parsed prerequisite AST | `NormalizedPrerequisiteExpression` |

---

## 7) Field mapping — `NormalizedDegreeRequirement`

Target model: `services/data-engineering/app/models/normalized_degree_requirement.py`

| NormalizedDegreeRequirement | PDF source | Transform / notes |
|-----------------------------|------------|-------------------|
| `degreeId` | program code `009216-1-000` | **GAP** — resolve to `degrees._id` after program import |
| `version` | catalog | `2025-2026` |
| `catalogYear` | catalog | `2025` |
| `catalogVersion` | catalog | `2025-2026` or `תשפ״ו` |
| `requirementType` | section | map: `חובה`→`core`, `הריחב`→`elective`, credit totals→`credit`, projects→`capstone` |
| `title` | section heading | Hebrew title |
| `ruleExpression` | table / prose | **GAP** — needs rich schema (`semester_matrix`, `choose_n`, `credit_pool`) |
| `minCredits` | נ״ז column | float |
| `courseIds` | course lists | resolve 7/8-digit numbers → catalog ids |
| `priority` | semester / order | from `רטסמס` index |
| `isMandatory` | section | true for core tables |
| `status` | constant | `staging` |
| `metadata` | footnotes | `semester`, `footnoteMarkers`, `programCode` |
| `sourceRefs` | PDF page | `locator: pdf:09-מדעי-הנתונים-וההחלטות-תשפ״ו.pdf#page=3` |

---

## 8) Future models (documentation only — not implemented)

### `NormalizedDegreeProgram` (maps to `degrees`)

| Field | PDF source |
|-------|------------|
| `institutionId` | `technion` |
| `code` | `009216-1-000` |
| `name` | Hebrew + English program name |
| `faculty` | DDS |
| `catalogYear`, `catalogVersion` | 2025 / 2025-2026 |
| `totalCredits` | 155.0 |
| `metadata.tracks` | nested paths if any |

### `NormalizedDegreePath` (optional track within program)

For statistics vs OR chains, IS track variants, etc.

| Field | Source |
|-------|--------|
| `programCode` | `009216-1-000` |
| `pathCode` | derived |
| `title` | chain name from PDF |
| `requirementIds` | links to requirements |

### `NormalizedCourseOffering`

| Field | JSON source |
|-------|-------------|
| `courseNumber` | `מספר מקצוע` |
| `semesterCode` | `2025-201` / `2025-2022` |
| `schedule` | `schedule[]` |
| `examDates` | `מועד א`, `מועד ב` |

### `NormalizedPrerequisiteExpression`

AST for parsed `מקצועות קדם` before ObjectId resolution.

---

## 9) Gaps between sources and current models

| Gap | Severity | Recommendation |
|-----|----------|----------------|
| Prerequisites are prose + course numbers, not ObjectIds | **High** | Add parser + `NormalizedPrerequisiteExpression`; resolve ids at staging import |
| JSON is semester offerings, not canonical catalog | **High** | Merge across semesters; PDF + dedupe for canonical course facts |
| Schedule / exams not in `NormalizedCourse` | **High** | Add `NormalizedCourseOffering` in Phase 6+ |
| No `degrees` / program model in data-engineering | **High** | Add `NormalizedDegreeProgram` before requirement import |
| `ruleExpression` too simple for PDF tables | **High** | Extend schema: `semester_matrix`, `choose_n`, `credit_pool`, `chain_pick` |
| PDF Hebrew RTL extraction quality | **Medium** | Use `pymupdf`/`pdfplumber` + RTL fix; expect manual curation |
| Overlap / no-additional-credit rules | **Medium** | Store in `metadata` initially; optional dedicated model later |
| `requirementType` enum missing `humanities`, `pe`, `project` | **Low** | Extend enum or use `metadata.category` |
| English titles absent in JSON | **Low** | Optional `titleEn` in future model |
| Sports / PE courses in university JSON | **Low** | Filter by faculty/program scope for DDS import |

---

## 10) Risks and limitations

1. **Licensing / redistribution** — raw JSON and PDF are gitignored; team must confirm terms before public repo publishing.
2. **No live scraping** — files are point-in-time snapshots; refresh process undefined.
3. **PDF table fidelity** — automated alone will not produce trustworthy requirement rows; plan for human review (`data/reviewed/`).
4. **Cross-source conflicts** — credits/titles in JSON may disagree with PDF; need precedence rules (PDF for degree rules, JSON for offerings).
5. **University-wide JSON noise** — DDS import must filter (faculty + program course lists).
6. **Prerequisite graph complexity** — Boolean expressions require test suite from real samples before staging import.

---

## 11) Recommended next phases (not in scope now)

| Phase | Work |
|-------|------|
| 6 | Technion JSON normalizer (raw → intermediate dict) + prerequisite lexer |
| 7 | PDF extraction spike with RTL fix; manual YAML/JSON for requirement tables |
| 8 | Staging import of **validated** DDS subset only |
| 9 | Production promotion + Python catalog APIs |

---

## 12) Committed artifacts for this phase

| Path | Purpose |
|------|---------|
| `services/data-engineering/data/raw/technion/README.md` | Local raw file policy |
| `services/data-engineering/data/raw/technion/manifest.json` | Source metadata (counts, no content) |
| `services/data-engineering/data/samples/technion_course_list_synthetic.json` | Shape reference for tests |
| `docs/data-sources/TECHNION_DDS_SOURCE_MAPPING.md` | This document |

**Confirmation:** Phase 5 performed **no MongoDB writes** and **no changes** to production collections or `import-sample` behavior.
