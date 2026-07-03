# UniPilot AI Database Schema (MongoDB)

Last updated: 2026-06-20  
Source of truth inputs: `docs/DOMAIN_MODEL.md`, `docs/PROJECT_CONTEXT.md`

## 1) Scope and Principles

- Database: MongoDB (required by assignment)
- Primary design goals:
  - Strong ownership isolation by `userId`
  - Catalog/reference integrity
  - Version-safe planning artifacts
  - Query efficiency with explicit indexes
- MVP vs later is explicitly separated below.

## 2) Collection Inventory

### MVP collections (implemented)
- `users`
- `student_profiles`
- `degree_programs` (promoted DDS catalog; API: `/catalog/degree-programs`)
- `degree_requirements` (hard executable rules)
- `catalog_rules` (advisory / non-executable rules)
- `courses`
- `course_offerings`
- `completed_courses`
- `semester_plans`
- `academic_risks`

### Staging collections (data-engineering only)
- `staging_courses`, `staging_course_offerings`, `staging_degree_programs`, `staging_degree_requirements`, `staging_catalog_rules`, `staging_ingestion_runs`

### Later collections
- `ai_recommendations`
- `simulation_scenarios`
- `simulation_results`
- `career_goals`

> **Naming note:** Production catalog uses `degree_programs` (with `programCode`) rather than a generic `degrees` collection. Legacy docs may refer to `degrees` — treat as the same domain concept.

## 3) Detailed Collection Schemas

## 3.1 users (MVP, implemented partially)

- **Purpose:** auth principal
- **Fields:**
  - `_id` (ObjectId)
  - `email` (string, lowercase, unique)
  - `passwordHash` (string, bcrypt hash only)
  - `status` (enum: `active|disabled`) default `active`
  - `createdAt` (date)
  - `updatedAt` (date)
  - `lastLoginAt` (date, nullable)
- **Validation rules:**
  - required: `email`, `passwordHash`, `createdAt`, `updatedAt`
  - `email` max 254, normalized lowercase
  - never store plaintext password
- **Ownership rules:**
  - user can only access own user summary
  - password hash never returned by API
- **Indexes:**
  - unique: `{ email: 1 }`

---

## 3.2 student_profiles (MVP)

- **Purpose:** user academic context
- **Fields:**
  - `_id`
  - `userId` (ObjectId -> users._id)
  - `institutionId` (string)
  - `programType` (enum/string)
  - `degreeId` (ObjectId -> degrees._id)
  - `catalogYear` (int)
  - `currentSemesterCode` (string, format `YYYY-T`)
  - `preferences` (object)
  - `revision` (int, optimistic concurrency)
  - `createdAt`, `updatedAt`
- **Validation rules:**
  - `userId` required and unique
  - `catalogYear` bounded to valid institutional range
  - referenced degree must exist
- **Ownership rules:**
  - strict owner access: only `userId` owner
- **Indexes:**
  - unique: `{ userId: 1 }`
  - secondary: `{ degreeId: 1 }`

---

## 3.3 degrees (MVP, read-only catalog — implemented Phase 4)

- **Purpose:** degree definitions by institution/catalog version
- **Fields:**
  - `_id`
  - `institutionId`
  - `code`
  - `name`
  - `version`
  - `catalogYear` (int)
  - `catalogVersion` (string, e.g. `2025.1`)
  - `effectiveFrom`, `effectiveTo`
  - `status` (`published` for active seed/API reads)
  - `metadata` (object; includes `isCuratedPlaceholder` on Phase 4 seed)
  - `sourceRefs` (array)
  - `createdAt`, `updatedAt`
- **Validation rules:**
  - unique tuple `(institutionId, code, version)`
  - valid date interval
- **Ownership rules:**
  - system/admin-managed; student read-only
- **Indexes:**
  - unique compound: `{ institutionId: 1, code: 1, version: 1 }`
  - `{ institutionId: 1, catalogYear: 1, status: 1 }`

---

## 3.4 degree_requirements (MVP, read-only catalog — implemented Phase 4)

- **Purpose:** normalized graduation rules
- **Fields:**
  - `_id`
  - `degreeId` (ObjectId -> degrees._id)
  - `version`
  - `catalogYear` (int)
  - `catalogVersion` (string)
  - `requirementType`
  - `title` (string)
  - `ruleExpression` (structured object)
  - `minCredits` (number, optional)
  - `courseSet` (array<ObjectId>, optional; exposed as `courseIds` in API)
  - `priority` (int)
  - `isMandatory` (bool)
  - `status`
  - `metadata` (object)
  - `sourceRefs` (array)
  - `createdAt`, `updatedAt`
- **Validation rules:**
  - `degreeId`, `version`, `requirementType`, `priority` required
  - `ruleExpression` must conform to approved schema
- **Ownership rules:**
  - system/admin-managed; student read-only
- **Indexes:**
  - `{ degreeId: 1, version: 1, priority: 1 }`
  - `{ degreeId: 1, requirementType: 1 }`

---

## 3.5 courses (MVP, read-only catalog — implemented Phase 4)

- **Purpose:** canonical course data
- **Fields:**
  - `_id`
  - `institutionId`
  - `subject`
  - `number`
  - `title`
  - `credits`
  - `description`
  - `level`
  - `tags` (array<string>)
  - `prerequisites` (array<ObjectId>; exposed as `prerequisiteIds` in API)
  - `corequisites` (array<ObjectId>; exposed as `corequisiteIds` in API)
  - `catalogYear` (int)
  - `catalogVersion` (string)
  - `status`
  - `version`
  - `metadata` (object)
  - `sourceRefs` (array)
  - `createdAt`, `updatedAt`
- **Validation rules:**
  - unique tuple `(institutionId, subject, number, version)`
  - credits in valid range (institution policy)
- **Ownership rules:**
  - system/admin-managed; student read-only
- **Indexes:**
  - unique compound: `{ institutionId: 1, subject: 1, number: 1, version: 1 }`
  - `{ institutionId: 1, catalogYear: 1, status: 1 }`

---

## 3.6 course_offerings (MVP, read-only catalog)

- **Purpose:** term-specific sections
- **Fields:**
  - `_id`
  - `courseId` (ObjectId -> courses._id)
  - `semesterCode`
  - `section`
  - `instructorId` (string/ObjectId, optional)
  - `schedule` (object)
  - `modality`
  - `capacity` (int)
  - `enrolled` (int)
  - `status`
- **Validation rules:**
  - unique `(courseId, semesterCode, section)`
  - `enrolled <= capacity`
- **Ownership rules:**
  - system/admin-managed; student read-only
- **Indexes:**
  - unique compound: `{ courseId: 1, semesterCode: 1, section: 1 }`
  - `{ semesterCode: 1, status: 1 }`

---

## 3.7 completed_courses (MVP, user-owned)

**Status:** Implemented (Phase 5).

- **Purpose:** transcript records per student
- **Import note:** Technion **summary** official PDFs list one row per course (latest grade only). Full retake history is not on that PDF; students may add extra attempts manually (`source: manual`). Progress logic still resolves multiple stored attempts to the latest when present.
- **Fields:**
  - `_id`
  - `userId` (ObjectId -> users._id)
  - `courseId` (ObjectId -> courses._id)
  - `courseOfferingId` (ObjectId -> course_offerings._id, nullable; not set via public API in Phase 5)
  - `semesterCode`
  - `grade`
  - `gradePoints` (nullable)
  - `creditsEarned`
  - `attempt`
  - `source` (`official|imported|manual`)
  - `metadata` (object, e.g. `{ notes }` for manual records)
  - `supersedesRecordId` (ObjectId, optional; reserved for future correction model)
  - `recordedAt`
  - `createdAt`
  - `updatedAt`
- **Validation rules:**
  - required: `userId`, `courseId`, `semesterCode`, `grade`, `creditsEarned`, `attempt`, `source`, `recordedAt`
  - grade enum (see `docs/API_SPEC.md` §4.3)
  - `creditsEarned` number >= 0, max 36, in **0.5 increments** (Technion-style half credits allowed)
  - `attempt` integer > 0 (API: 1–10)
  - `courseId` must reference a published `courses` document (production catalog after Phase 12 promotion on Python API)
  - unique `(userId, courseId, attempt)`
- **Ownership rules:**
  - strict owner access by `userId`; cross-user reads return 404
  - public API never accepts `userId` from clients
- **Source policy:**
  - Public `POST /completed-courses` always creates `source: manual`
  - `official` and `imported` records are created only by future **internal trusted import** logic (ingestion/worker), not by client API
  - `PUT` / `DELETE` via public API allowed only when `source === manual`
- **Indexes:**
  - unique compound: `{ userId: 1, courseId: 1, attempt: 1 }`
  - `{ userId: 1, semesterCode: 1 }`
  - `{ userId: 1, recordedAt: -1 }`

---

## 3.8 semester_plans (MVP, user-owned, versioned)

- **Purpose:** versioned academic plans (deterministic generation in Phase 7)
- **Fields:**
  - `_id`
  - `userId` (ObjectId -> users._id)
  - `name`
  - `status` (`draft|active|archived`)
  - `version` (int)
  - `basePlanId` (ObjectId, optional)
  - `plannerType` (`deterministic` for Phase 7; future: `ai-assisted`)
  - `assumptions` (object; generation inputs snapshot)
  - `explanation` (object; rule-based planner output, not LLM)
  - `semesters` (embedded array)
    - each semester:
      - `semesterCode`
      - `goalCredits`
      - `plannedCourses` (array of course snapshots)
        - `courseId`, `courseNumber`, `courseTitle`, `credits`, `category`, `reason`
      - `notes`
      - `constraintsSnapshot`
      - `order`
  - `createdAt`, `updatedAt`
- **Validation rules:**
  - `userId`, `name`, `status`, `version` required
  - unique `semesterCode` inside same plan version
  - course duplicates disallowed inside same semester
- **Ownership rules:**
  - strict owner access by `userId`
- **Indexes:**
  - `{ userId: 1, status: 1 }`
  - `{ userId: 1, updatedAt: -1 }`

---

## 3.9 ai_recommendations (Later)

- user-owned immutable recommendation artifacts.
- indexes: `{ userId: 1, createdAt: -1 }`, `{ userId: 1, planId: 1, createdAt: -1 }`.

## 3.10 simulation_scenarios (Later)

- user-owned scenario definitions.
- index: `{ userId: 1, createdAt: -1 }`.

## 3.11 simulation_results (Later)

- immutable results linked to scenarios.
- indexes: `{ scenarioId: 1, generatedAt: -1 }`, `{ userId: 1, generatedAt: -1 }`.

## 3.12 academic_risks (Phase 8, user-owned analysis reports)

- **Purpose:** persisted deterministic academic risk analyses for semester plans or ad-hoc proposals
- **Fields:**
  - `_id`
  - `userId` (ObjectId -> users._id)
  - `planId` (ObjectId -> semester_plans._id, optional for ad-hoc analysis)
  - `semesterCode`
  - `analyzerType` (`deterministic`)
  - `analysisSource` (`semester_plan` | `adhoc_courses`)
  - `status` (`open|mitigated|accepted`)
  - `summary` (object)
    - `totalRisks`, `highestSeverity`, `counts: { low, medium, high }`
  - `risks` (embedded array)
    - `riskType`, `severity`, `title`, `explanation`, `evidence`, `suggestedFixes`, `source`, `relatedCourseIds`
  - `contextSnapshot` (object; degree/plan workload snapshot, planned course ids/snapshots, completed course count)
  - `createdAt`, `updatedAt`
- **Validation rules:**
  - `userId`, `semesterCode`, `analyzerType`, `status`, `summary`, `risks` required
  - each risk requires `riskType`, `severity`, `title`, `explanation`, `source`
- **Ownership rules:**
  - strict owner access by `userId`
- **Indexes:**
  - `{ userId: 1, createdAt: -1 }`
  - `{ userId: 1, status: 1, "summary.highestSeverity": 1 }`
  - `{ userId: 1, planId: 1, createdAt: -1 }`

## 3.13 career_goals (Later)

- user-owned goals.
- index: `{ userId: 1, active: 1, priority: 1 }`.

## 4) Embedded vs Referenced Decisions

### Embedded
- `semesters` inside `semester_plans`
- small snapshots only (display labels/version snapshots)

### Referenced
- all cross-aggregate links (user/profile/degree/course/offering/transcript/etc.)
- all unbounded-growth entities
- all shared institution-managed catalog entities

## 5) Ownership and Access Rules (Global)

- Student-owned collections must include `userId`.
- Query/write filters for protected endpoints must include `userId == token.sub`.
- Catalog collections (`degrees`, `degree_requirements`, `courses`, `course_offerings`) are read-only from student-facing APIs.

## 6) Validation Enforcement Layers

- API boundary validation (strict schema, reject unknown fields).
- Database write validation (required fields and type checks).
- Referential checks at service layer for key foreign references.
- Security checks (auth + ownership) before data mutation.

## 6.5) DDS production collections (Phase 12 — data-engineering promoted)

Written only via `promote-dds-to-production --i-confirm-dangerous-production-write` after Phase 11 gate passes.

| Collection | Purpose | Stable key |
|---|---|---|
| `degree_programs` | DDS program shells (3 programs) | `productionKey` e.g. `technion-dds:program:{code}:{catalogVersion}` |
| `degree_requirements` | Executable `credit_bucket` groups only (19) | `technion-dds:requirement:{groupId}:{catalogVersion}` |
| `catalog_rules` | Advisory/non-executable rules (44) | `technion-dds:advisory-rule:…` |
| `courses` | Technion course metadata from staging JSON | `technion:course:{courseNumber}` |
| `course_offerings` | Semester offerings for promoted courses | `technion:course-offering:{courseNumber}:{year}:{semesterCode}` |
| `promotion_runs` | Audit/rollback manifest | `promotionRunId` |

Common promoted fields: `sourceName`, `catalogVersion`, `promotedAt`, `promotionRunId`, `status: published`. Advisory rules always have `enforceInGraduationProgress: false`. Staging flags (`isStaging`, `productionEligible`) are **not** copied.

Rollback: `rollback-dds-production-promotion` deletes production docs where `promotionRunId` matches; staging collections are untouched.

**Phase 13 consumers:** `services/api` read-only `/catalog/*` endpoints query these collections; see `docs/API_SPEC.md` §4.4.1.

---

## 7) MVP Simplicity Constraints

- Do not implement full requirement DSL engine in MVP.
- Do not implement scenario/result/risk collections yet.
- Keep correction/version behavior explicit but minimal (append-only where practical).
- Prefer deterministic, explainable progress calculations before advanced AI augmentation.

## 8) Graduation progress computation (Phase 15 — Python)

Graduation progress is **computed at read time** — not stored in a separate collection.

**Inputs (MongoDB):**
- `student_profiles` for the authenticated `userId` (`degreeId` required — references `degree_programs._id`)
- `completed_courses` for the authenticated `userId`
- `degree_programs`, `degree_requirements`, `catalog_rules` (`course_pool` only), `courses` for the profile's degree/catalog context

**Rule classes (Phase 15):**
| Class | Collection | Enforced in graduation progress |
|---|---|---|
| `credit_bucket` | `degree_requirements` | Yes — min credits per bucket |
| `course_pool` | `catalog_rules` | Yes — when linked via Phase 15.1 `linkedCreditBucketId` or Phase 15.0 naming convention |
| `semester_matrix` | `catalog_rules` | No — planning-only |

**Allocation:**
- Bucket evaluation order: `required` / matrix mandatory first, then faculty electives (strict pools), then technion-wide (enrichment, PE, free), then legacy `core` (skipped when required + technion split exist)
- Required bucket: semester-matrix courses and overlap/cross-track substitutes only (not PE overlap groups)
- Passing numeric grades only (grade ≥ 55); 55 and below excluded
- One effective completion per `courseId` (latest by semester, then attempt number, then `recordedAt`; must be passing)
- Top-level `completedCredits` and `transcriptCreditsTotal` match official transcript accumulated credits (latest passing row per course, credits > 0)
- `degreeAppliedCredits` counts only credits assigned to requirement buckets (pool/overlap placement)
- Catalog overlap groups still flag duplicate rows in `ineligibleCredits`; they do not reduce headline transcript totals
- Strict pools: only pool-eligible courses count toward linked buckets
- Other buckets: greedy credit fill from unassigned passing completions

**API:** `GET /graduation-progress` (JWT, self-scoped). See `docs/API_SPEC.md` §4.6.
