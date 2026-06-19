# UniPilot AI API Specification

Last updated: 2026-06-19  
Source of truth inputs: `docs/DOMAIN_MODEL.md`, `docs/PROJECT_CONTEXT.md`

## 1) Scope and Release Boundaries

### MVP scope (design now, implement incrementally)
- Auth
- Student profile
- Completed courses
- Course catalog
- Degree requirements
- Graduation progress
- Semester plans

### Later scope (not MVP)
- AI advisor endpoints
- Simulation endpoints

## 2) API Conventions

- Base URL: `http://<host>:<API_PORT>`
- Content type: `application/json`
- Auth: `Authorization: Bearer <accessToken>` for protected routes
- Response envelope:
  - Success: `{ "success": true, "data": <payload>, "error": null }`
  - Error: `{ "success": false, "data": null, "error": "<message>" }`
- Status codes:
  - `200` success read/update
  - `201` created
  - `400` validation failure
  - `401` missing/invalid auth
  - `403` ownership/authorization violation
  - `404` resource not found
  - `409` conflict (e.g., duplicate email)
  - `429` rate limited
  - `500` internal error (non-leaky)

## 3) Entity Availability Matrix

| Entity | API Exposure | Phase |
|---|---|---|
| User | Auth + self info only | MVP (partially implemented) |
| StudentProfile | Full self CRUD (singleton `/student-profile`) | MVP (implemented) |
| Degree | Read-only (`GET /degrees`, `GET /degrees/:id`) | MVP (implemented) |
| DegreeRequirement | Read-only (`GET /degrees/:id/requirements`) | MVP (implemented) |
| Course | Read-only (`GET /courses`, `GET /courses/:id`) | MVP (implemented) |
| CourseOffering | Read-only | MVP |
| CompletedCourse | User-owned CRUD | MVP |
| SemesterPlan | User-owned CRUD/versioned | MVP |
| Semester | Embedded in SemesterPlan | MVP |
| AIRecommendation | Read-only to user | Later |
| SimulationScenario | User-owned CRUD | Later |
| SimulationResult | User-owned read | Later |
| AcademicRisk | User-owned analyze + history | Phase 8 |
| CareerGoal | User-owned CRUD | Later (optional MVP extension) |

## 4) Endpoints

## 4.1 Authentication (MVP)

### Implemented now
- `POST /auth/register`
  - Body: `{ "email": string, "password": string }`
  - Returns: `201` + `accessToken` + public user
- `POST /auth/login`
  - Body: `{ "email": string, "password": string }`
  - Returns: `200` + `accessToken` + public user
- `GET /auth/me` (protected)
  - Returns current authenticated user summary

### Validation & security
- Email normalized lowercase, max 254.
- Password policy enforced; bcrypt hash persisted only.
- Auth routes rate-limited (`429` on exceed).
- Invalid credentials return generic message.

---

## 4.2 Student Profile (MVP)

**Status:** Implemented (Phase 3).

`/student-profile` is a **self-scoped singleton resource**: each authenticated user has at most one profile. All operations apply only to the profile owned by the JWT subject (`token.sub`). There is no profile id in the URL and clients must not send `userId` or `_id` in request bodies.

### Shared profile object shape

Returned by `POST`, `GET`, and `PUT` inside `data.profile`:

```json
{
  "id": "665f2b0f2a3f7b2a1a9a7f11",
  "userId": "665f2b0f2a3f7b2a1a9a7f10",
  "institutionId": "uni-main",
  "programType": "BSc",
  "degreeId": "665f2b0f2a3f7b2a1a9a7f12",
  "catalogYear": 2025,
  "currentSemesterCode": "2025-1",
  "preferences": {
    "maxCreditsPerSemester": 18
  },
  "revision": 1,
  "createdAt": "2026-06-19T12:00:00.000Z",
  "updatedAt": "2026-06-19T12:00:00.000Z"
}
```

Notes:
- `userId` is **server-assigned** from the JWT and returned for the authenticated owner only; clients must not send it on write requests.
- `degreeId` may be `null` when not set.
- `revision` increments on each successful update.

### Shared validation rules (create and update)

| Field | Create | Update | Rules |
|---|---|---|---|
| `institutionId` | required | optional | string, trimmed, 1–100 chars |
| `programType` | required | optional | string, trimmed, 1–100 chars |
| `degreeId` | optional | optional | 24-char hex ObjectId string; must reference an existing **published** degree in MongoDB when provided |
| `catalogYear` | required | optional | integer, 1990–2100 |
| `currentSemesterCode` | required | optional | string matching `YYYY-1` or `YYYY-2` (e.g. `2025-1`) |
| `preferences` | optional | optional | object; only `maxCreditsPerSemester` (integer, 1–36) allowed; nested unknown fields rejected |
| `userId` | **forbidden** | **forbidden** | rejected as unknown field |
| `_id` | **forbidden** | **forbidden** | rejected as unknown field |
| other fields | **forbidden** | **forbidden** | strict schema rejects unknown keys |

Update-specific rule: at least one updatable field must be present; an empty `{}` body is rejected.

### Shared ownership behavior

- Profile `userId` is always set from `Authorization: Bearer <accessToken>` — never from the request body.
- `GET`, `PUT`, and `DELETE` resolve the profile by the authenticated user's id only.
- Cross-user access is impossible: there is no endpoint to read or modify another user's profile.
- `403` is not used for student profile routes in the current implementation; unauthorized access is prevented by scoping and strict validation (`401` for auth failures, `400` for invalid payloads).

---

### `POST /student-profile`

Create the authenticated user's profile (one profile per user).

**Authentication:** Required (`Authorization: Bearer <accessToken>`).

**Request body:**

```json
{
  "institutionId": "uni-main",
  "programType": "BSc",
  "degreeId": "665f2b0f2a3f7b2a1a9a7f11",
  "catalogYear": 2025,
  "currentSemesterCode": "2025-1",
  "preferences": {
    "maxCreditsPerSemester": 18
  }
}
```

**Success response (`201`):**

```json
{
  "success": true,
  "data": {
    "profile": { }
  },
  "error": null
}
```

`data.profile` uses the shared profile object shape above.

**Error responses:**

| Status | Condition | Example `error` |
|---|---|---|
| `400` | Validation failure or unknown field | `"Semester code must match YYYY-1 or YYYY-2 format"` |
| `401` | Missing or invalid JWT | `"Authentication token is required"` |
| `409` | Profile already exists for this user | `"Student profile already exists for this user"` |
| `500` | Unexpected server error | `"Internal server error"` |

**Ownership:** `userId` is assigned from the JWT subject at creation time. Client-supplied `userId` is rejected.

---

### `GET /student-profile`

Read the authenticated user's profile.

**Authentication:** Required (`Authorization: Bearer <accessToken>`).

**Request body:** None.

**Success response (`200`):**

```json
{
  "success": true,
  "data": {
    "profile": { }
  },
  "error": null
}
```

**Error responses:**

| Status | Condition | Example `error` |
|---|---|---|
| `401` | Missing or invalid JWT | `"Authentication token is invalid or expired"` |
| `404` | No profile exists for this user | `"Student profile not found"` |
| `500` | Unexpected server error | `"Internal server error"` |

**Ownership:** Returns only the profile where `profile.userId == token.sub`.

---

### `PUT /student-profile`

Update the authenticated user's existing profile. This is **not** an upsert; use `POST` to create first.

**Authentication:** Required (`Authorization: Bearer <accessToken>`).

**Request body** (at least one field):

```json
{
  "programType": "BSc-Honors",
  "currentSemesterCode": "2025-2",
  "preferences": {
    "maxCreditsPerSemester": 21
  }
}
```

**Success response (`200`):**

```json
{
  "success": true,
  "data": {
    "profile": { }
  },
  "error": null
}
```

`data.profile` reflects the updated document; `revision` is incremented.

**Error responses:**

| Status | Condition | Example `error` |
|---|---|---|
| `400` | Validation failure, empty body, or unknown field (including `_id`, `userId`) | `"At least one field is required for update"` |
| `401` | Missing or invalid JWT | `"Authentication token is required"` |
| `404` | No profile exists for this user | `"Student profile not found"` |
| `500` | Unexpected server error | `"Internal server error"` |

**Ownership:** Updates only the profile owned by `token.sub`. Clients must not send `_id` or `userId`; those fields are rejected by strict validation.

---

### `DELETE /student-profile`

Hard-delete the authenticated user's profile.

**Authentication:** Required (`Authorization: Bearer <accessToken>`).

**Request body:** None.

**Success response (`200`):**

```json
{
  "success": true,
  "data": {
    "deleted": true
  },
  "error": null
}
```

**Error responses:**

| Status | Condition | Example `error` |
|---|---|---|
| `401` | Missing or invalid JWT | `"Authentication token is required"` |
| `404` | No profile exists for this user | `"Student profile not found"` |
| `500` | Unexpected server error | `"Internal server error"` |

**Ownership:** Deletes only the profile owned by `token.sub`. Other users' profiles are unaffected.

---

## 4.3 Completed Courses (MVP)

**Status:** Implemented (Phase 5). User-owned transcript records backed by MongoDB `completed_courses`.

All routes require `Authorization: Bearer <accessToken>`. Records are scoped to the authenticated user (`token.sub`). Clients must not send `userId`.

### `GET /completed-courses`

List the authenticated user's completed course records (newest first).

**Query parameters (optional):**

| Param | Rules |
|---|---|
| `page` | integer ≥ 1, default `1` |
| `limit` | integer 1–100, default `50` |

Unknown query fields are rejected (`400`).

**Success (`200`):**

```json
{
  "success": true,
  "data": {
    "completedCourses": [ ],
    "pagination": { "total": 1, "page": 1, "limit": 50 }
  },
  "error": null
}
```

### `POST /completed-courses`

Create a manual transcript record for the authenticated user.

**Request body:**

| Field | Required | Rules |
|---|---|---|
| `courseId` | yes | ObjectId; must exist in published course catalog |
| `semesterCode` | yes | `YYYY-1` or `YYYY-2` |
| `grade` | yes | `A+`, `A`, `A-`, `B+`, `B`, `B-`, `C+`, `C`, `C-`, `D`, `F`, `Pass`, `Fail` |
| `gradePoints` | no | number 0–100 |
| `creditsEarned` | yes | number 0–36 in **0.5 increments** (e.g. `0`, `1`, `1.5`, `2`, `3.5`) |
| `attempt` | no | integer 1–5, default `1` |
| `metadata` | no | `{ notes?: string (max 500) }` |

`source` is always stored as `manual` for API-created records. `userId`, `official`, and `imported` source values are rejected on create.

**Success (`201`):** `{ success, data: { completedCourse }, error: null }`

**Errors:** `400` validation / unknown course, `409` duplicate `(user, courseId, attempt)`

### `GET /completed-courses/:id`

Fetch one owned record by id.

**Success (`200`):** `{ success, data: { completedCourse }, error: null }`

**Errors:** `404` when not found or not owned (no cross-user leakage)

### `PUT /completed-courses/:id`

Update a **manual** record only. `official` and `imported` records return `403`.

Updatable fields: `semesterCode`, `grade`, `gradePoints`, `creditsEarned`, `metadata` (at least one required).

**Success (`200`):** updated `completedCourse` DTO

**Errors:** `400`, `403` (non-manual), `404`

### `DELETE /completed-courses/:id`

Delete a **manual** record only. `official` and `imported` records return `403`.

**Success (`200`):** `{ success, data: { deleted: true }, error: null }`

**Errors:** `403` (non-manual), `404`

### Public DTO fields

`id`, `courseId`, `courseNumber`, `courseTitle`, `semesterCode`, `grade`, `gradePoints`, `creditsEarned`, `attempt`, `source`, `metadata`, `recordedAt`, `createdAt`, `updatedAt`

### Rules

- User can only read/list own records.
- Duplicate `(userId, courseId, attempt)` conflicts with `409`.
- Grade and credits validation enforced at boundary.
- Course reference validated against seeded catalog (`findCourseById`).

### Official / imported records (not public API)

`source: official` and `source: imported` records **cannot** be created via `POST /completed-courses`. The public API always stores `manual` on create and rejects `official` / `imported` in the request body.

Future transcript ingestion or registrar sync will insert `official` / `imported` rows through **internal trusted import logic** (worker/admin pipeline writing directly to MongoDB), not through client-facing endpoints. Those records remain readable by the owning user but are not editable or deletable via `PUT` / `DELETE` (returns `403`).

---

## 4.4 Course Catalog (MVP, read-only)

**Status:** Implemented (Phase 4). Data source: curated Technion-style **placeholder** seed in `data/validated/technion/2025/` (not official Technion extracts).

Shared academic catalog data — **not student-owned**. All routes require `Authorization: Bearer <accessToken>`.

### `GET /courses`

List published courses for an institution and catalog year.

**Query parameters (required unless noted):**

| Param | Required | Rules |
|---|---|---|
| `institutionId` | yes | string, 1–100 chars (e.g. `technion`) |
| `catalogYear` | yes | integer, 1990–2100 |
| `page` | no | integer ≥ 1, default `1` |
| `limit` | no | integer 1–100, default `50` |

Unknown query fields are rejected (`400`).

**Success (`200`):**

```json
{
  "success": true,
  "data": {
    "courses": [ ],
    "pagination": { "total": 12, "page": 1, "limit": 50 }
  },
  "error": null
}
```

Each course includes: `id`, `institutionId`, `subject`, `number`, `title`, `credits`, `description`, `level`, `tags`, `prerequisiteIds`, `corequisiteIds`, `catalogYear`, `catalogVersion`, `version`, `status`, `metadata`, `sourceRefs`, timestamps.

**Errors:** `400` validation, `401` missing/invalid JWT, `500` internal.

---

### `GET /courses/:courseId`

Get a single published course by MongoDB id.

**Success (`200`):** `{ "success": true, "data": { "course": { } }, "error": null }`  
**Errors:** `400` invalid id, `401` auth, `404` not found, `500` internal.

---

### Not implemented yet

- `GET /course-offerings`
- `GET /course-offerings/:offeringId`

---

## 4.5 Degree Requirements (MVP, read-only)

**Status:** Implemented (Phase 4). Uses same curated placeholder seed as §4.4.

Shared academic catalog data — **not student-owned**. All routes require JWT.

### `GET /degrees`

List published degrees for an institution and catalog year.

**Query parameters:**

| Param | Required | Rules |
|---|---|---|
| `institutionId` | yes | string, 1–100 chars |
| `catalogYear` | yes | integer, 1990–2100 |

**Success (`200`):**

```json
{
  "success": true,
  "data": { "degrees": [ ] },
  "error": null
}
```

Each degree includes: `id`, `institutionId`, `code`, `name`, `version`, `catalogYear`, `catalogVersion`, `effectiveFrom`, `effectiveTo`, `status`, `metadata`, `sourceRefs`, timestamps.

**Errors:** `400`, `401`, `500`.

---

### `GET /degrees/:degreeId`

Get a single published degree.

**Success (`200`):** `{ "success": true, "data": { "degree": { } }, "error": null }`  
**Errors:** `400` invalid id, `401`, `404`, `500`.

---

### `GET /degrees/:degreeId/requirements`

List published requirements for a degree, filtered to the degree's `version`.

**Success (`200`):**

```json
{
  "success": true,
  "data": {
    "degreeId": "...",
    "catalogYear": 2025,
    "catalogVersion": "2025.1",
    "requirements": [ ]
  },
  "error": null
}
```

Each requirement includes: `id`, `degreeId`, `version`, `catalogYear`, `catalogVersion`, `requirementType`, `title`, `ruleExpression`, `minCredits`, `courseIds`, `priority`, `isMandatory`, `status`, `metadata`, `sourceRefs`, timestamps.

**Errors:** `400`, `401`, `404` degree not found, `500`.

### Catalog access rules

- Read-only for authenticated students; no write endpoints.
- Only `status: "published"` records are returned.
- `catalogYear` + `catalogVersion` are explicit on all catalog entities.
- Seeded records include `metadata.isCuratedPlaceholder: true` until real Technion ingestion replaces them.

---

## 4.4.1 Python DDS Catalog API (Phase 13, read-only)

**Status:** Implemented. Data source: **production** MongoDB collections promoted in Phase 12 (`courses`, `course_offerings`, `degree_programs`, `degree_requirements`, `catalog_rules`).

**Auth:** JWT required (`Authorization: Bearer <accessToken>`), matching Node §4.4–4.5.

**Prefix:** `/catalog` (Python migration path; Node legacy uses `/courses` and `/degrees` with ObjectId keys).

### `GET /catalog/courses`

| Param | Required | Rules |
|---|---|---|
| `q` | no | text search over course number, Hebrew title, faculty |
| `faculty` | no | case-insensitive contains |
| `courseNumber` | no | exact 8-digit Technion number |
| `limit` | no | 1–200, default 50 |
| `offset` | no | ≥ 0, default 0 |
| `includeOfferings` | no | boolean, default false |

**Success (`200`):** `{ success, data: { items, total, limit, offset }, error: null }`

### `GET /catalog/courses/{course_number}`

8-digit course number path param. Optional `includeOfferings=true`.

### `GET /catalog/courses/{course_number}/offerings`

Optional `academicYear`, `semesterCode` (`200|201|202`).

### `GET /catalog/degree-programs`

Lists DDS programs from `degree_programs` (e.g. 3 programs after Phase 12 promotion).

### `GET /catalog/degree-programs/{program_code}`

Program code format: `009216-1-000`.

### `GET /catalog/degree-programs/{program_code}/requirements`

Returns **hard executable** requirement groups from `degree_requirements` only. Each item includes `requirementEnforcement: "hard"`. Advisory `catalog_rules` are **excluded**.

### `GET /catalog/degree-programs/{program_code}/advisory-rules`

Returns advisory/manual-review metadata from `catalog_rules` only. Each item includes `advisoryOnly: true`, `enforceInGraduationProgress: false`, `notHardRequirement: true`. Not used for automatic graduation enforcement.

### `GET /catalog/degree-programs/{program_code}/catalog-summary`

Combined program + hard requirements + advisory rules + counts.

**Errors:** `400` validation, `401` auth, `404` not found, `500` internal.

---

## 4.6 Graduation Progress (MVP)

**Status:** Implemented (Phase 6). Deterministic progress computed from the authenticated user's `StudentProfile`, `CompletedCourses`, selected `Degree`, `DegreeRequirements`, and course catalog. No LLM involvement.

### `GET /graduation-progress`

Calculate graduation progress for the authenticated user.

**Auth:** `Authorization: Bearer <accessToken>` required.

**Success (`200`):**

```json
{
  "success": true,
  "data": {
    "graduationProgress": {
      "degreeId": "665f2b0f2a3f7b2a1a9a7d01",
      "degreeCode": "CS-BSC",
      "degreeName": "BSc Computer Science / Software Engineering",
      "catalogYear": 2025,
      "catalogVersion": "2025.1",
      "completedCredits": 6.5,
      "totalRequiredCredits": 155,
      "creditsRemaining": 148.5,
      "completionPercentage": 4.19,
      "completedMandatoryCourses": [],
      "remainingMandatoryCourses": [],
      "completedElectiveCredits": 3.5,
      "remainingElectiveCredits": 2.5,
      "requirementProgress": [],
      "missingRequirements": [],
      "statusSummary": "in_progress"
    }
  },
  "error": null
}
```

**`statusSummary` values:** `not_started`, `in_progress`, `mandatory_requirements_met`, `complete`

**Errors:**

| Code | When |
|---|---|
| `401` | Missing/invalid JWT |
| `404` | Student profile not found |
| `400` | Profile has no `degreeId` selected |
| `400` | Profile `degreeId` not found in catalog |

### Rules

- Progress is computed only for `token.sub`.
- Uses published degree requirements from MongoDB; does not invent rules.
- Passing grades count toward progress (`A+` … `D`, `Pass`); `F` / `Fail` are ignored.
- Multiple attempts on the same course use the best passing `creditsEarned`.
- Top-level `completedCredits` counts each completed course once; the same credits may also appear inside individual requirement buckets without inflating the global total.
- Credit math supports fractional values (0.5 increments).
- `requirementProgress` evaluates seeded rule types: `course_set` (`all_of`), `credit_pool`, `total_credits`.

---

## 4.7 Semester Plans (Phase 7 — deterministic generate + history)

### Implemented endpoints
- `POST /semester-plans/generate` (protected) — generate and persist a deterministic next-semester plan
- `GET /semester-plans` (protected) — list own planning history (`?page=1&limit=50`)
- `GET /semester-plans/:id` (protected) — get one owned plan by id

### Not implemented yet (later)
- `POST /semester-plans` (manual create)
- `PUT /semester-plans/:planId` (update)
- `POST /semester-plans/:planId/versions` (new plan version)
- `DELETE /semester-plans/:planId` (archive/soft delete)

### POST /semester-plans/generate

**Body (strict):**
```json
{
  "semesterCode": "2025-2",
  "maxCredits": 12,
  "minCredits": 9,
  "name": "Optional plan label"
}
```

- `semesterCode` required (`YYYY-S` format).
- `maxCredits` / `minCredits` optional; 0.5 increments; 0–36.
- `userId` and other unknown fields rejected.
- `maxCredits` defaults to `studentProfile.preferences.maxCreditsPerSemester`, then `18`.

**Response `201`:**
```json
{
  "success": true,
  "data": {
    "semesterPlan": {
      "id": "...",
      "name": "...",
      "status": "draft",
      "version": 1,
      "plannerType": "deterministic",
      "assumptions": { },
      "explanation": {
        "summary": "...",
        "rulesApplied": ["..."],
        "partialPlan": false,
        "emptyPlan": false
      },
      "semesters": [
        {
          "semesterCode": "2025-2",
          "goalCredits": 12,
          "plannedCourses": [
            {
              "courseId": "...",
              "courseNumber": "02340101",
              "courseTitle": "...",
              "credits": 3,
              "category": "mandatory",
              "reason": "Remaining mandatory degree requirement"
            }
          ]
        }
      ]
    }
  },
  "error": null
}
```

### Rules
- Plans are user-owned; `userId` is set server-side from JWT (`token.sub`).
- Cross-user access returns `404` (not `403`) on `GET /semester-plans/:id`.
- `Semester` objects are embedded in the stored plan.
- Planner is deterministic and rule-based (no LLM / AI explanations).
- Excludes completed passing courses; failed attempts (`F`) do not count as completed.
- Prioritizes remaining mandatory courses before electives.
- Respects prerequisites from catalog `courses.prerequisites`.
- Supports fractional credits (0.5 increments).
- Treats courses scheduled earlier in the same plan as satisfying prerequisites for later recommendations.
- `explanation.blockedByPrerequisites` includes `missingPrerequisites` (course id/number/title) and a human-readable `reason`.
- `explanation.partialPlan` is `true` when `minCredits` or `maxCredits` targets cannot be fully met.
- Returns partial/empty plans with structured `explanation` when workload or eligibility limits apply.

### Errors
- `404` — student profile not found.
- `400` — profile has no `degreeId`, invalid payload, or referenced degree missing from catalog.

---

## 4.8 Academic Risks (Phase 8 — deterministic analyze + history)

### Implemented endpoints
- `POST /academic-risks/analyze` (protected) — analyze a persisted semester plan or ad-hoc proposed courses and persist results
- `GET /academic-risks` (protected) — list own analysis history (`?page=1&limit=50`)
- `GET /academic-risks/:id` (protected) — get one owned analysis by id

### POST /academic-risks/analyze

**Analyze persisted plan (strict):**
```json
{
  "planId": "665f2b0f2a3f7b2a1a9a7fff"
}
```

**Analyze ad-hoc proposed courses (strict):**
```json
{
  "semesterCode": "2025-2",
  "courseIds": ["665f2b0f2a3f7b2a1a9a7c01", "665f2b0f2a3f7b2a1a9a7c07"],
  "maxCredits": 12,
  "minCredits": 9
}
```

- Provide either `planId` **or** (`semesterCode` + `courseIds`).
- `userId` and other unknown fields rejected.
- Analyzer is deterministic and rule-based (no LLM).

**Response `201`:**
```json
{
  "success": true,
  "data": {
    "academicRiskAnalysis": {
      "id": "...",
      "planId": "...",
      "semesterCode": "2025-2",
      "analyzerType": "deterministic",
      "analysisSource": "semester_plan",
      "status": "open",
      "summary": {
        "totalRisks": 2,
        "highestSeverity": "high",
        "counts": { "low": 0, "medium": 1, "high": 1 }
      },
      "risks": [
        {
          "riskType": "unmet_prerequisites",
          "severity": "high",
          "title": "Unmet prerequisites",
          "explanation": "...",
          "evidence": {},
          "suggestedFixes": ["..."],
          "source": "rule",
          "relatedCourseIds": ["..."]
        }
      ],
      "contextSnapshot": {}
    }
  },
  "error": null
}
```

### Detected risk types (rule-based)
- `empty_plan`, `partial_plan`
- `credit_overload`, `too_few_credits`
- `unmet_prerequisites`, `course_already_completed`, `failed_course_retake`
- `no_mandatory_progress`, `insufficient_graduation_progress`
- `deferred_prerequisite_blocked_courses`, `deferred_workload_limited_courses` (from persisted planner explanation)
- `too_many_advanced_courses` (only when course `level`/tags metadata supports it)
- `unknown_catalog_course`, `catalog_course_out_of_scope`, `duplicate_planned_course`

### Rules
- Plans/analyses are user-owned; `userId` is set server-side from JWT (`token.sub`).
- Cross-user access returns `404` on `GET /academic-risks/:id` and foreign `planId` analysis.
- Uses student profile, completed courses, catalog, degree requirements, graduation progress, and semester plan data only.
- Does not invent academic rules beyond stored catalog/requirement facts.

### Errors
- `404` — student profile not found, semester plan not found, or analysis not found.
- `400` — profile has no `degreeId`, invalid payload, or referenced degree missing from catalog.

---

## 4.9 AI Advisor (Later)

### Not in MVP
- `POST /ai/recommendations`
- `GET /ai/recommendations`
- `GET /ai/recommendations/:id`

### Design intent
- Async processing through worker/queue.
- Result artifacts persisted and user-owned.
- Rate limiting mandatory.

---

## 4.10 Simulation (Later)

### Not in MVP
- `POST /simulations/scenarios`
- `GET /simulations/scenarios`
- `POST /simulations/scenarios/:id/run`
- `GET /simulations/results/:id`

### Design intent
- Scenario CRUD then asynchronous simulation run.
- Immutable simulation results.

## 5) Ownership and Authorization Policy

- Every student-owned endpoint must enforce `resource.userId == token.sub`.
- Read-only catalog endpoints do not require ownership checks.
- `401`: auth absent/invalid.
- `403`: authenticated but unauthorized ownership.

## 6) Validation Policy

- Validate body, params, query for every endpoint.
- Reject unknown fields on write endpoints.
- Strict enum/range checks for grades, credits, semester code, requirement types.

## 7) Rate Limiting Policy

- Auth endpoints: enforced now.
- AI and simulation endpoints: mandatory when implemented.
- Return `429` with generic retry-later message.

## 8) MVP Non-Goals

- Student profile intelligence/recommendation generation logic.
- Complex requirement DSL execution engine.
- Advisor collaboration workflows.
- Full simulation analytics and risk lifecycle APIs.
