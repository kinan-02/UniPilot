# UniPilot AI Database Schema (MongoDB)

Last updated: 2026-06-19  
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

### MVP collections
- `users`
- `student_profiles`
- `degrees`
- `degree_requirements`
- `courses`
- `course_offerings`
- `completed_courses`
- `semester_plans`

### Later collections
- `ai_recommendations`
- `simulation_scenarios`
- `simulation_results`
- `academic_risks`
- `career_goals`

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

- **Purpose:** transcript records per student
- **Fields:**
  - `_id`
  - `userId` (ObjectId -> users._id)
  - `courseId` (ObjectId -> courses._id)
  - `courseOfferingId` (ObjectId -> course_offerings._id, nullable)
  - `semesterCode`
  - `grade`
  - `gradePoints`
  - `creditsEarned`
  - `attempt`
  - `source` (`official|imported|manual`)
  - `supersedesRecordId` (ObjectId, optional for correction model)
  - `recordedAt`
- **Validation rules:**
  - required: `userId`, `courseId`, `semesterCode`, `attempt`, `recordedAt`
  - grade enum + credits >= 0 + attempt > 0
- **Ownership rules:**
  - strict owner access by `userId`
- **Indexes:**
  - `{ userId: 1, semesterCode: 1 }`
  - `{ userId: 1, courseId: 1 }`
  - optional unique: `{ userId: 1, courseId: 1, attempt: 1 }`

---

## 3.8 semester_plans (MVP, user-owned, versioned)

- **Purpose:** versioned academic plans
- **Fields:**
  - `_id`
  - `userId` (ObjectId -> users._id)
  - `name`
  - `status` (`draft|active|archived`)
  - `version` (int)
  - `basePlanId` (ObjectId, optional)
  - `assumptions` (object)
  - `semesters` (embedded array)
    - each semester:
      - `semesterCode`
      - `goalCredits`
      - `plannedCourses` (array of refs/snapshots)
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

## 3.12 academic_risks (Later)

- user-owned risk signal records.
- indexes: `{ userId: 1, status: 1, severity: 1 }`, `{ userId: 1, createdAt: -1 }`.

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

## 7) MVP Simplicity Constraints

- Do not implement full requirement DSL engine in MVP.
- Do not implement scenario/result/risk collections yet.
- Keep correction/version behavior explicit but minimal (append-only where practical).
- Prefer deterministic, explainable progress calculations before advanced AI augmentation.
