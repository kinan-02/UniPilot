# UniPilot AI Domain Model

Last updated: 2026-06-20  
Status: Aligned with `docs/API_SPEC.md`, `docs/DATABASE_SCHEMA.md`, and `docs/PROJECT_CONTEXT.md`

This document defines the academic domain model for UniPilot AI and guides API, database, and feature implementation.

## Scope and Assumptions

- Primary institution: Technion (`institutionId: "technion"`).
- Catalog data is promoted Technion DDS production data (not placeholder seed).
- API exposes catalog as read-only `/catalog/*` routes backed by `degree_programs`, `courses`, `degree_requirements`, and `catalog_rules`.

## Core Entity Relationship Overview

- `User` 1:1 `StudentProfile`
- `StudentProfile` 1:N `CompletedCourse`
- `StudentProfile` 1:N `SemesterPlan`
- `SemesterPlan` 1:N embedded `Semester`
- `Degree` 1:N `DegreeRequirement`
- `Course` 1:N `CourseOffering`
- `StudentProfile` N:1 `Degree` (active degree track)
- `AIRecommendation` links to `User`, optionally `SemesterPlan` and `SimulationScenario`
- `SimulationScenario` 1:N `SimulationResult`
- `AcademicRisk` links to `User`, optionally `SemesterPlan`, `SimulationResult`
- `CareerGoal` 1:N with `User`

---

## Core Entities

### 1) User

- **Purpose:** Authentication principal and security boundary root.
- **Attributes:** `id`, `email`, `passwordHash`, `createdAt`, `updatedAt`, `status` (active/disabled), `lastLoginAt`.
- **Relationships:** 1:1 with `StudentProfile`; 1:N with `AIRecommendation`, `SimulationScenario`, `SimulationResult`, `AcademicRisk`, `CareerGoal`.
- **Validation rules:** email normalized lowercase and unique; password hash required; no plaintext password persistence.
- **Ownership:** User-owned identity record (system-managed for auth concerns).
- **Future extensibility:** MFA settings, OAuth identities, refresh token families, account recovery metadata.

### 2) StudentProfile

- **Purpose:** Student academic context for planning/recommendation decisions.
- **Attributes:** `id`, `userId`, `institutionId`, `programType`, `degreeId`, `catalogYear`, `currentSemesterCode`, `preferences`, `createdAt`, `updatedAt`.
- **Relationships:** belongs to `User`; references `Degree`; has many `CompletedCourse`, `SemesterPlan`, `CareerGoal`.
- **Validation rules:** `userId` unique; `catalogYear` bounded; semester code format (`YYYY-T`); referenced degree must exist.
- **Ownership:** Strictly owned by the authenticated user.
- **Future extensibility:** advisor notes, transfer-credit policy version, localization/timezone, accessibility accommodations.

### 3) Degree

- **Purpose:** Catalog-level definition of academic program.
- **Attributes:** `id`, `institutionId`, `code`, `name`, `version`, `effectiveFrom`, `effectiveTo`, `status`, `metadata`.
- **Relationships:** has many `DegreeRequirement`; referenced by many `StudentProfile`.
- **Validation rules:** `(institutionId, code, version)` unique; effective date interval valid.
- **Ownership:** Institution/admin-managed shared data.
- **Future extensibility:** multi-campus variants, optional tracks/minors, accreditation metadata.

### 4) DegreeRequirement

- **Purpose:** Machine-readable graduation rule unit.
- **Attributes:** `id`, `degreeId`, `requirementType` (core/elective/credit/GPA/capstone), `ruleExpression`, `minCredits`, `courseSet`, `priority`, `version`, `isMandatory`.
- **Relationships:** belongs to `Degree`; evaluated against `CompletedCourse`, `SemesterPlan`, `Course`.
- **Validation rules:** requirement expression schema-valid; priority integer; version monotonic per degree.
- **Ownership:** Institution/admin-managed shared data.
- **Future extensibility:** prerequisite graph constraints, waivers, substitution policies, cross-listed rule support.

### 5) Course

- **Purpose:** Canonical course catalog entry independent of term offerings.
- **Attributes:** `id`, `institutionId`, `subject`, `number`, `title`, `credits`, `description`, `level`, `tags`, `prerequisites`, `corequisites`, `status`, `version`.
- **Relationships:** has many `CourseOffering`; referenced by `CompletedCourse`, `Semester` (planned items), `DegreeRequirement`.
- **Validation rules:** `(institutionId, subject, number, version)` unique; credits in accepted range; prerequisite references valid.
- **Ownership:** Institution/admin-managed shared data.
- **Future extensibility:** competency outcomes, modality constraints, historical renames/equivalencies.

### 6) CourseOffering

- **Purpose:** Term-specific offering details for a course.
- **Attributes:** `id`, `courseId`, `semesterCode`, `section`, `instructorId`, `schedule`, `modality`, `capacity`, `enrolled`, `status`.
- **Relationships:** belongs to `Course`; can be referenced in `Semester` planned selections and simulation feasibility checks.
- **Validation rules:** unique `(courseId, semesterCode, section)`; capacity non-negative; enrolled <= capacity.
- **Ownership:** Institution/admin-managed shared data.
- **Future extensibility:** waitlist policies, delivery constraints, classroom resources, cancellation events.

### 7) CompletedCourse

- **Purpose:** Student historical transcript fact.
- **Attributes:** `id`, `userId`, `courseId`, `courseOfferingId` (optional), `semesterCode`, `grade`, `gradePoints`, `creditsEarned`, `attempt`, `source` (official/imported/manual), `recordedAt`.
- **Relationships:** belongs to `User`; references `Course` and optional `CourseOffering`; used by requirement/risk engines.
- **Validation rules:** grade enum; credits >= 0; course reference required; attempt positive integer.
- **Ownership:** User-owned academic record (with possible institutional sync source).
- **Future extensibility:** transfer credit provenance, grade replacement policy, audit trails.

### 8) SemesterPlan

- **Purpose:** Versioned plan object for future semesters and strategy alternatives.
- **Attributes:** `id`, `userId`, `name`, `status` (draft/active/archived), `version`, `basePlanId` (optional), `assumptions`, `createdAt`, `updatedAt`.
- **Relationships:** belongs to `User`; embeds `Semester`; linked by `AIRecommendation`, `SimulationScenario`, `AcademicRisk`.
- **Validation rules:** one active plan per user (policy-driven); version monotonic per logical plan lineage.
- **Ownership:** User-owned.
- **Future extensibility:** collaborative planning, advisor review workflow, branch/merge of plan alternatives.

### 9) Semester

- **Purpose:** Term container inside a semester plan.
- **Attributes:** `semesterCode`, `goalCredits`, `plannedCourses` (array of course or offering refs), `notes`, `constraintsSnapshot`, `order`.
- **Relationships:** embedded child of `SemesterPlan`; references `Course`/`CourseOffering`.
- **Validation rules:** unique `semesterCode` inside a plan version; no duplicate course in same semester; credit load limits.
- **Ownership:** Owned via parent `SemesterPlan`.
- **Future extensibility:** alternate scenarios per semester, confidence score, lock state after registration.

### 10) AIRecommendation

- **Purpose:** Persisted AI-generated advice artifact for traceability.
- **Attributes:** `id`, `userId`, `planId` (optional), `scenarioId` (optional), `model`, `promptVersion`, `inputSnapshotRef`, `recommendationType`, `content`, `explanations`, `confidence`, `createdAt`.
- **Relationships:** belongs to `User`; optionally references `SemesterPlan` and `SimulationScenario`; may produce `AcademicRisk`.
- **Validation rules:** recommendationType enum; content non-empty; model metadata required.
- **Ownership:** User-owned output derived from system processing.
- **Future extensibility:** feedback loop labels, human override markers, A/B prompt lineage.

### 11) SimulationScenario

- **Purpose:** User-defined what-if input scenario.
- **Attributes:** `id`, `userId`, `name`, `planId`, `changes` (drop/add/delay/retake assumptions), `objectiveWeights`, `createdAt`, `status`.
- **Relationships:** belongs to `User`; references `SemesterPlan`; has many `SimulationResult`.
- **Validation rules:** at least one change operation; objective weights normalize; target plan exists and is owned.
- **Ownership:** User-owned.
- **Future extensibility:** reusable scenario templates, batch scenario sets, advisor-shared scenarios.

### 12) SimulationResult

- **Purpose:** Immutable computed outcome for a scenario execution.
- **Attributes:** `id`, `userId`, `scenarioId`, `runId`, `engineVersion`, `resultSummary`, `metrics` (time-to-degree, credit load variance, requirement completion), `riskScore`, `generatedAt`.
- **Relationships:** belongs to `User`; belongs to `SimulationScenario`; may drive `AcademicRisk` and `AIRecommendation`.
- **Validation rules:** scenario ownership match; engineVersion required; metrics schema strict.
- **Ownership:** User-owned computed artifact.
- **Future extensibility:** explainability traces, stochastic distributions, Monte Carlo run aggregation.

### 13) AcademicRisk

- **Purpose:** Structured risk signal surfaced to the student.
- **Attributes:** `id`, `userId`, `riskType` (delay/GPA/overload/prerequisite/capstone), `severity`, `evidenceRefs`, `source` (rule/ai/hybrid), `status` (open/mitigated/accepted), `createdAt`, `resolvedAt`.
- **Relationships:** belongs to `User`; optionally references `SemesterPlan`, `SimulationResult`, `AIRecommendation`.
- **Validation rules:** severity enum; evidence required; status transitions valid.
- **Ownership:** User-owned operational insight.
- **Future extensibility:** intervention workflows, advisor assignment, SLA alerts.

### 14) CareerGoal

- **Purpose:** Student long-term objective anchor used in recommendations.
- **Attributes:** `id`, `userId`, `title`, `targetRole`, `industry`, `preferredSkills`, `timeHorizon`, `priority`, `active`, `createdAt`, `updatedAt`.
- **Relationships:** belongs to `User`; influences `AIRecommendation` and `SimulationScenario` objective weighting.
- **Validation rules:** at least one active goal optional but bounded; priority range constrained.
- **Ownership:** User-owned.
- **Future extensibility:** job-market linkage, goal progress score, external portfolio links.

---

## Immutability and Versioning Strategy

### Immutable entities (or immutable records)

- `CompletedCourse` (append-only corrections via superseding record, not overwrite)
- `SimulationResult` (never mutate computed output)
- `AIRecommendation` content payload (append new recommendation instead of editing old)
- Historical versions of `Degree`, `DegreeRequirement`, `Course` once published

### Versioned entities

- `Degree` (catalog-year and policy evolution)
- `DegreeRequirement` (rule changes over time)
- `Course` (catalog revisions/equivalencies)
- `SemesterPlan` (explicit user plan versions/branches)
- `StudentProfile` (lightweight revision stamp recommended for conflict safety)

---

## MongoDB Modeling: Embed vs Reference

### Should be embedded

- `Semester` inside `SemesterPlan` (bounded, always read with plan)
- Small denormalized display snapshots:
  - e.g., `courseTitleSnapshot` within planned course entries
  - e.g., `degreeNameSnapshot` in profile for display only

### Should be referenced

- `User` -> `StudentProfile` (1:1)
- `StudentProfile` -> `Degree`
- `Degree` -> `DegreeRequirement`
- `CourseOffering` -> `Course`
- `CompletedCourse` -> `Course` / `CourseOffering`
- `AIRecommendation` -> `SimulationScenario` / `SemesterPlan` (optional refs)
- `SimulationResult` -> `SimulationScenario`
- `AcademicRisk` -> related scenario/result/recommendation refs
- `CareerGoal` as separate collection (query/filter independently)

### Rationale

- Embed only bounded, lifecycle-coupled data.
- Reference unbounded growth entities and shared catalog entities.
- Preserve historical reproducibility by storing minimal snapshots on write.

---

## Required Indexes (Initial)

### User/Auth

- `users.email` unique (case-normalized)

### Student context

- `student_profiles.userId` unique
- `student_profiles.degreeId`

### Catalog

- `degrees` unique compound: `(institutionId, code, version)`
- `degree_requirements`: `(degreeId, version)`, `(degreeId, requirementType)`
- `courses` unique compound: `(institutionId, subject, number, version)`
- `course_offerings` unique compound: `(courseId, semesterCode, section)`
- `course_offerings`: `(semesterCode, status)`

### Student records and planning

- `completed_courses`: `(userId, semesterCode)`, `(userId, courseId)`, unique optional `(userId, courseId, attempt)`
- `semester_plans`: `(userId, status)`, `(userId, updatedAt desc)`
- `career_goals`: `(userId, active, priority)`

### AI, simulation, risk

- `ai_recommendations`: `(userId, createdAt desc)`, `(userId, planId, createdAt desc)`
- `simulation_scenarios`: `(userId, createdAt desc)`
- `simulation_results`: `(scenarioId, generatedAt desc)`, `(userId, generatedAt desc)`
- `academic_risks`: `(userId, status, severity)`, `(userId, createdAt desc)`

---

## Design Flaws to Resolve Before Implementation

1. **Catalog version drift risk**  
   Recommendations or simulation results can become invalid when degree/course rules change.
   - Mitigation: persist `catalogVersionSnapshot` in scenario/result/recommendation records.

2. **Requirement expression complexity explosion**  
   Free-form requirement DSL can become unmaintainable.
   - Mitigation: start with constrained typed rules + validated schema before introducing full expression language.

3. **Transcript correction semantics unclear**  
   Overwriting `CompletedCourse` breaks auditability.
   - Mitigation: append-only correction model with `supersedesRecordId`.

4. **Plan mutation race conditions**  
   Concurrent edits can silently overwrite plan changes.
   - Mitigation: optimistic concurrency via `version` and conditional updates.

5. **AI recommendation reproducibility gap**  
   If input snapshots are not persisted, recommendations cannot be explained/audited.
   - Mitigation: store immutable input references and prompt/model version metadata.

6. **Over-embedding risk in semester plans**  
   Excessive embedded details (full course objects) can create document bloat.
   - Mitigation: embed only minimal snapshots and refs.

7. **Ownership leakage risk across users**  
   Cross-entity refs may allow unauthorized traversal.
   - Mitigation: enforce `userId` ownership checks on every student-owned query path.

8. **Index under-provisioning for timeline views**  
   Without descending time indexes, recommendation/simulation history queries degrade quickly.
   - Mitigation: create and validate indexes listed above before feature rollout.

---

## Implementation Guardrails (Non-Functional)

- Keep student-owned entities keyed by `userId` and always query with ownership predicates.
- Persist immutable analytical outputs (`AIRecommendation`, `SimulationResult`) for auditability.
- Enforce schema validation at API boundary and DB write boundary.
- Do not implement student profile features until this model is reviewed and accepted.
