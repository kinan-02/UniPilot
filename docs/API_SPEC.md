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
| StudentProfile | Full self CRUD-lite | MVP |
| Degree | Read-only | MVP |
| DegreeRequirement | Read-only | MVP |
| Course | Read-only | MVP |
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

### Planned MVP endpoints
- `GET /student-profile` (protected)
- `PUT /student-profile` (protected, idempotent upsert shape)

### Request/response notes
- Profile is scoped to token user; no cross-user access.
- Update body may include: `institutionId`, `programType`, `degreeId`, `catalogYear`, `currentSemesterCode`, `preferences`.
- `degreeId` must reference existing degree.

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

### Planned MVP endpoints
- `GET /courses` (filter/sort/pagination)
- `GET /courses/:courseId`
- `GET /course-offerings` (optional query by `semesterCode`, `courseId`)
- `GET /course-offerings/:offeringId`

### Rules
- Read-only for students.
- Response can include denormalized metadata for planning UI.

---

## 4.5 Degree Requirements (MVP, read-only)

### Planned MVP endpoints
- `GET /degrees`
- `GET /degrees/:degreeId`
- `GET /degrees/:degreeId/requirements`

### Rules
- Degree catalog version is explicit in responses.
- Requirements remain immutable per published catalog version.

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
