# Prompt 02 — Plan a Feature

Use this prompt before implementing any feature in UniPilot AI.

## Goal
Produce a concrete, reviewable plan for ONE feature — backend first — that satisfies the project rules.

## Inputs
- The feature picked from `docs/planning/FEATURE_BACKLOG.md`.
- The current phase from `docs/planning/IMPLEMENTATION_PHASES.md`.

## Instructions
1. Restate the feature and its acceptance criteria in one paragraph.
2. Identify the affected layers/containers: `api`, `worker`, `ai`, MongoDB, Redis.
3. Define the API contract (if applicable):
   - Route(s), method, request body schema, response envelope, status codes.
   - Auth requirement (protected? ownership check?).
   - Rate-limiting needs (auth/AI endpoints).
4. Define data model changes (MongoDB collections, indexes).
5. Define async flow if AI is involved (enqueue → worker → job status → result).
6. List validation rules for all request bodies.
7. List the tests required: unit, integration, E2E, stress, security.
8. Note README updates needed.
9. Break the work into small, ordered steps (TDD-friendly).

## Output
A plan with: scope, API contract, data model, async flow, validation, test list, step-by-step tasks, and risks.

## Constraints
- One feature only. Do not plan the whole project.
- Backend-first. UI is secondary (project is graded on backend).
- Every external boundary must be validated and (where needed) protected + rate-limited.
