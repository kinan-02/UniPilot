# Real Technion DDS Data Alignment Plan

Last updated: 2026-06-19  
Status: Planning (pre-implementation)  
Related docs: `docs/planning/PYTHON_BACKEND_MIGRATION_PLAN.md`, `docs/DATA_INGESTION_ARCHITECTURE.md`, `docs/DOMAIN_MODEL.md`, `docs/DATABASE_SCHEMA.md`, `docs/PROJECT_CONTEXT.md`

## 1) Purpose

Define how UniPilot transitions from **curated placeholder catalog data** to **real Technion Faculty of Data and Decision Sciences (DDS)** academic data, and how that transition gates Python backend features that depend on the catalog.

This plan answers:

1. What real DDS data we collect and from where
2. How we process and validate it
3. Whether it matches our domain and database models
4. When we update the schema
5. When we import into MongoDB
6. Which Python backend features must wait until import is complete

## 2) Scope

### In scope (initial DDS subset)

- At least one DDS undergraduate program/track (e.g., Data Science and Engineering or equivalent official naming from source documents)
- Core courses: number, title, credits, prerequisites/corequisites where published
- Degree requirements: mandatory sets, credit pools, total credits
- Catalog year and version metadata
- Provenance (`sourceRefs`, retrieval dates, source locators)

### Out of scope (initial subset)

- Full university-wide Technion catalog
- All faculties beyond DDS
- Official transcript import (`official` / `imported` completed courses) — later phase
- Full RAG index generation — parallel track after validated text exists
- Automated nightly refresh — later phase

## 3) Why Real Data Gates the Python Catalog Features

The Node backend was built against a **small curated placeholder** in `data/validated/technion/2025/` (`isCuratedPlaceholder: true`). That was correct for proving APIs and deterministic planners.

Re-implementing catalog-dependent features in Python against the same placeholder would:

- Duplicate rework when real DDS structure differs
- Encode wrong prerequisites, credit rules, or requirement types
- Force premature `StudentProfile.degreeId` FK assumptions

Therefore:

| Can proceed before real DDS import | Must wait for validated DDS import |
|---|---|
| Python FastAPI skeleton | Course Catalog APIs |
| Auth | Degree Requirements APIs |
| Student Profile (`degreeId` optional) | Completed Courses (catalog FK) |
| Data-engineering container | Graduation Progress |
| Raw DDS collection + processing | Semester Planner |
| Validation + schema alignment | Academic Risk Analyzer |
| | AI services grounded in catalog facts |

## 4) Source Collection Strategy

### 4.1 Target sources (DDS)

| Source type | Examples | Expected outputs |
|---|---|---|
| Degree / program pages | DDS faculty degree descriptions | `degrees` metadata, RAG text |
| Course catalogs | PDF/HTML course lists for DDS tracks | `courses`, offerings |
| Requirement documents | Degree requirements, track checklists | `degree_requirements` |
| Course pages | Per-course prerequisites, credits, descriptions | `courses`, RAG chunks |
| Policy snippets | Prerequisites policy, overload rules | RAG (mostly unstructured) |

### 4.2 Repository layout (DDS-specific)

```text
data/
  raw/technion/dds/<catalogYear>/
    manifest.json
    pdfs/
    html/
    url-list.txt
  extracted/technion/dds/<catalogYear>/
  normalized/technion/dds/<catalogYear>/
    degrees.json
    courses.json
    degree_requirements.json
    course_offerings.json
  validated/technion/dds/<catalogYear>/   # import-ready
```

Follow the global pipeline stages in `docs/DATA_INGESTION_ARCHITECTURE.md`; DDS uses a dedicated namespace so placeholder CS seed (`data/validated/technion/2025/`) remains available for Node reference tests.

### 4.3 Manifest requirements

Each source entry in `manifest.json` must include:

- `sourceId`, `type` (pdf/html/url), `locator`, `retrievedAt`
- `catalogYear`, `faculty` = `dds`
- `licenseOrTermsNote` (how the team may use/store the file)
- `reviewStatus` (pending / approved / rejected)

## 5) Processing Pipeline (Data-Engineering Container)

Executed inside `services/data-engineering` (Python Phase 4+):

| Step | Command (planned) | Output |
|---|---|---|
| 1. Collect | `collect --faculty dds --year <Y>` | `data/raw/...` |
| 2. Extract | `extract --manifest ...` | `data/extracted/...` |
| 3. Normalize | `normalize --year <Y>` | `data/normalized/...` |
| 4. Validate | `validate --year <Y>` | `data/validated/...` + report |
| 5. Import | `import --year <Y>` | MongoDB collections |

**Rule:** Only **validated** artifacts may be imported. Low-confidence extractions go to manual review, not MongoDB.

## 6) Domain Model Alignment

### 6.1 Entity mapping checklist

For each validated record, confirm alignment with `docs/DOMAIN_MODEL.md`:

| Domain entity | Required fields | DDS validation question |
|---|---|---|
| `Degree` | `institutionId`, `code`, `name`, `catalogYear`, `catalogVersion` | Is DDS program code stable and unique? |
| `Course` | `number`, `title`, `credits`, `prerequisites` | Are credits fractional? Are prereqs explicit? |
| `DegreeRequirement` | `requirementType`, `ruleExpression`, `courseSet`, `minCredits` | Do DDS rules match `course_set`, `credit_pool`, `total_credits`? |
| `CourseOffering` | optional for MVP | Needed for semester availability? |

### 6.2 Validation report deliverable

Produce `docs/reports/DDS_DATA_VALIDATION_REPORT.md` containing:

- Record counts per entity
- Field coverage (% courses with prerequisites, credits, descriptions)
- Schema mismatches (fields in data but not in schema, and vice versa)
- Rule types not expressible in current `ruleExpression` model
- Recommended schema changes (if any)
- Sign-off checklist for team

### 6.3 Schema update policy

If real DDS data does not fit the current schema:

1. **Do not** bend import logic to silently drop important facts
2. Propose schema changes in `docs/DATABASE_SCHEMA.md`
3. Update `docs/DOMAIN_MODEL.md` if domain concepts change
4. Add ADR if the change affects API contract
5. Update Node reference **only if** team decides to keep Node in sync (optional during Python-first period)
6. Re-run validation before import

**StudentProfile impact:**

- Keep `degreeId` **optional** in Python until import completes
- After import, enable FK validation: `degreeId` must reference a DDS degree matching `institutionId` + `catalogYear`
- Document valid DDS `degreeId` values in README after import

## 7) Database Import Criteria

Import (Python Phase 7) may proceed only when:

- [ ] Validation report signed off
- [ ] `data/validated/technion/dds/<catalogYear>/` exists with `metadata.isCuratedPlaceholder: false`
- [ ] All records include `sourceRefs`, `catalogYear`, `catalogVersion`
- [ ] Indexes match `docs/DATABASE_SCHEMA.md`
- [ ] Import CLI is idempotent
- [ ] Integration test verifies degree + course + requirement counts

**Institution ID:** continue using `institutionId: "technion"` with faculty/track metadata distinguishing DDS (e.g., `metadata.faculty: "dds"`).

## 8) Impact on Python Backend Features

After successful import, implement Python features in this order (see `PYTHON_BACKEND_MIGRATION_PLAN.md` §5 Phase 8):

1. Catalog read APIs (`/courses`, `/degrees`, requirements)
2. Completed courses (with catalog FK validation)
3. Graduation progress (deterministic)
4. Semester planner (deterministic)
5. Academic risk analyzer (deterministic)
6. AI / RAG services (grounded in MongoDB + retrieved chunks)

Each feature must use **imported DDS data** in integration tests, not the placeholder CS seed.

## 9) Node Reference Backend During Alignment

- Node backend **stays unchanged** and continues to use placeholder seed for its test suite
- Node remains the behavioral reference for API envelopes, auth, and profile patterns
- Catalog-dependent Node behavior is a reference for **logic patterns**, not for **DDS factual data**
- Do not delete placeholder seed until team approves and Python parity is verified

## 10) Risks and Mitigations

| Risk | Mitigation |
|---|---|
| DDS sources change format mid-project | Version by `catalogYear` + `catalogVersion`; manifest snapshots |
| Prerequisites incomplete in sources | Mark confidence; block import of uncertain edges; manual review |
| Requirement rules too complex for current DSL | Extend `ruleExpression` via schema ADR; do not hack planner |
| Team imports before validation | Gate import CLI on validation report token/file |
| Python and Node catalog diverge | Single validated JSON source of truth; Node not required to import DDS |

## 11) Exit Criteria (Real Data Alignment Complete)

- [ ] Real DDS subset collected and documented in manifest
- [ ] Data-engineering container processes raw → validated JSON
- [ ] Validation report approved
- [ ] Schema/docs updated for any mismatches
- [ ] MongoDB populated from validated DDS data
- [ ] README documents DDS import and valid degree/course identifiers
- [ ] Python catalog-dependent implementation unblocked

## 12) Immediate Next Steps

1. Approve this plan alongside `PYTHON_BACKEND_MIGRATION_PLAN.md`
2. Identify official DDS source URLs/PDFs and assign collection owners
3. Build data-engineering container (Python Phase 4)
4. Collect first DDS subset into `data/raw/technion/dds/<catalogYear>/`
5. Run validation report before any Python catalog API work
