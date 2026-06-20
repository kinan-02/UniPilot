# UniPilot AI API Specification

Last updated: 2026-06-20  
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

| Entity | API Exposure | Status |
|---|---|---|
| User | Auth + self info only | Implemented |
| StudentProfile | Full self CRUD (`/student-profile`) | Implemented |
| DegreeProgram | Read-only (`/catalog/degree-programs/*`) | Implemented |
| DegreeRequirement | Read-only (hard requirements under `/catalog/degree-programs/{code}/requirements`) | Implemented |
| CatalogRule | Read-only (advisory rules under `/catalog/degree-programs/{code}/advisory-rules`) | Implemented |
| Course | Read-only (`/catalog/courses/*`) | Implemented |
| CourseOffering | Read-only (`/catalog/courses/{number}/offerings`) | Implemented |
| CompletedCourse | User-owned CRUD | Implemented |
| SemesterPlan | User-owned CRUD + versioning | Implemented |
| AcademicRisk | User-owned analyze + history | Implemented |
| AIRecommendation | Read-only to user | Later |
| SimulationScenario | User-owned CRUD | Later |
| SimulationResult | User-owned read | Later |
| CareerGoal | User-owned CRUD | Later (optional) |

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

**Status:** Implemented. User-owned transcript records backed by MongoDB `completed_courses`.

**Python (`services/api`):** Same route contract (`POST/GET/PUT/DELETE /completed-courses`, record id in path). `courseId` must reference a published document in the **production** `courses` collection (Phase 12 promotion). Does not calculate graduation progress; does not read advisory `catalog_rules`.

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
| `grade` | yes | number 0–100 (Technion numeric scale; pass strictly above 55) |
| `gradePoints` | no | number 0–100 (optional; when set, used for pass/fail if present) |
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
- Course reference validated against published production catalog (`courses` collection).

### Official / imported records (not public API)

`source: official` and `source: imported` records **cannot** be created via `POST /completed-courses`. The public API always stores `manual` on create and rejects `official` / `imported` in the request body.

Future transcript ingestion or registrar sync will insert `official` / `imported` rows through **internal trusted import logic** (worker/admin pipeline writing directly to MongoDB), not through client-facing endpoints. Those records remain readable by the owning user but are not editable or deletable via `PUT` / `DELETE` (returns `403`).

---

## 4.4 Course Catalog (read-only, production DDS)

**Status:** Implemented. Data source: **production** MongoDB collections promoted via `data-engineering` (Phase 12): `courses`, `course_offerings`, `degree_programs`, `degree_requirements`, `catalog_rules`.

**Auth:** JWT required (`Authorization: Bearer <accessToken>`).

**Prefix:** `/catalog`

> **Note:** Legacy routes `GET /courses` and `GET /degrees` from the removed Node backend are **not** part of the current API. Use `/catalog/*` below.

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

**Status:** Implemented. Deterministic progress computed from the authenticated user's `StudentProfile`, `CompletedCourses`, selected degree program (`degree_programs._id` via profile `degreeId`), hard `degree_requirements`, linked `course_pool` rules, and course catalog. No LLM involvement.

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
- Profile `degreeId` must reference a published `degree_programs` document (`400` if unknown).
- Uses published hard requirements from `degree_requirements` (`credit_bucket` only in Python Phase 15).
- Linked elective pools (`course_pool` in `catalog_rules`) are enforced for DS and faculty elective buckets via naming convention (`elective-ds` ↔ `elective-ds-pool`, `elective-faculty` ↔ `elective-faculty-pool`).
- `semester_matrix` and track-specific rules are planning-only — never block graduation in Phase 15.
- Passing grades count toward progress (numeric score **strictly above 55** on the 0–100 scale); 55 and below are ignored.
- Multiple attempts on the same course use the best passing `creditsEarned`.
- Top-level `completedCredits` counts each completed course once; bucket allocation may assign credits to specific requirements without inflating the global total.
- Credit math supports fractional values (0.5 increments).
- `requirementProgress[].eligibilityEnforcement`: `strict_pool` (linked pool) or `credit_bucket_only` (heuristic fill).
- Response includes `assumptions` documenting Phase 15 scope limits.

---

## 4.7 Semester Plans (Phase 7 — deterministic generate + history)

### Implemented endpoints
- `POST /semester-plans/generate` (protected) — generate and persist a deterministic next-semester plan
- `POST /semester-plans` (protected) — create a student-built manual plan
- `GET /semester-plans` (protected) — list own planning history (`?page=1&limit=50`)
- `GET /semester-plans/:id` (protected) — get one owned plan by id
- `PUT /semester-plans/:planId` (protected) — update manual plan courses and weekly schedule
- `DELETE /semester-plans/:planId` (protected) — archive (soft delete)
- `POST /semester-plans/:planId/versions` (protected) — fork a new draft plan version from an owned plan

### Not implemented yet (later)
- Plan lineage listing endpoint (optional; versions appear in `GET /semester-plans` history)

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

### POST /semester-plans (manual create)

**Body (strict):**
```json
{
  "name": "My Spring Plan",
  "status": "draft",
  "semesterCode": "2025-2",
  "plannedCourses": [
    { "courseId": "665f2b0f2a3f7b2a1a9a7c01", "category": "manual", "reason": "Optional note" }
  ],
  "weeklySchedule": {
    "entries": [
      {
        "courseId": "665f2b0f2a3f7b2a1a9a7c01",
        "academicYear": 2025,
        "semesterCode": 201,
        "scheduleGroups": [{ "day": "Sunday", "time": "10:30-12:30" }]
      }
    ]
  }
}
```

- `plannerType` is set to `"manual"` server-side.
- `scheduleGroups` optional when a published offering exists for the course/year/semesterCode; otherwise required.
- Each semester may include `weeklySchedule` with `status`, `entries`, `conflicts`, `weekView`, and `summary`.

### PUT /semester-plans/:planId

Updates `name`, `status` (`draft`/`active`), and/or full `semesters` array (planned courses + weekly schedule). Increments `version`. Archived plans return `400`.

### DELETE /semester-plans/:planId

Soft-deletes by setting `status` to `archived`.

### POST /semester-plans/:planId/versions

**Body (strict, optional):**
```json
{
  "name": "Optional label for the forked version"
}
```

**Response `201`:**
```json
{
  "success": true,
  "data": {
    "sourcePlanId": "...",
    "semesterPlan": {
      "id": "...",
      "basePlanId": "...",
      "version": 2,
      "status": "draft",
      "plannerType": "manual",
      "semesters": [ ]
    }
  },
  "error": null
}
```

- Creates a **new** `semester_plans` document copied from the source plan.
- Sets `basePlanId` to the source plan id and `version` to `source.version + 1`.
- Resets `status` to `draft`. Default name: `{source.name} v{version}` when `name` omitted.
- Cannot fork archived plans (`400`).
- Cross-user fork returns `404`.

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
