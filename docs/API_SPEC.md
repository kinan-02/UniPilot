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
| AcademicRisk | User-owned read/ack | Later |
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

### Planned MVP endpoints
- `GET /completed-courses` (protected, user-owned list)
- `POST /completed-courses` (protected, add transcript record)
- `PUT /completed-courses/:id` (protected, correction policy)
- `DELETE /completed-courses/:id` (protected, soft-delete preferred)

### Request fields
- `courseId` (required)
- `courseOfferingId` (optional)
- `semesterCode`, `grade`, `gradePoints`, `creditsEarned`, `attempt`, `source`

### Rules
- User can only manage own records.
- Grade/credits/attempt validation enforced.
- No plaintext sensitive data involved.

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

## 4.6 Graduation Progress (MVP)

### Planned MVP endpoints
- `GET /graduation-progress` (protected)

### Output shape (high-level)
- `degreeId`, `catalogVersion`
- `requirementProgress[]`
- `creditsCompleted`, `creditsRemaining`
- `estimatedSemestersRemaining`
- `blockingRequirements[]`

### Rules
- Computed from user transcript + degree requirements.
- Must be deterministic and explainable.

---

## 4.7 Semester Plans (MVP)

### Planned MVP endpoints
- `GET /semester-plans` (protected)
- `POST /semester-plans` (protected)
- `GET /semester-plans/:planId` (protected)
- `PUT /semester-plans/:planId` (protected)
- `POST /semester-plans/:planId/versions` (protected, creates new plan version)
- `DELETE /semester-plans/:planId` (protected, archive/soft delete)

### Rules
- Plans are user-owned and versioned.
- `Semester` objects are embedded.
- One active plan per user (policy-level constraint).

---

## 4.8 AI Advisor (Later)

### Not in MVP
- `POST /ai/recommendations`
- `GET /ai/recommendations`
- `GET /ai/recommendations/:id`

### Design intent
- Async processing through worker/queue.
- Result artifacts persisted and user-owned.
- Rate limiting mandatory.

---

## 4.9 Simulation (Later)

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
