# Prompt 03 — Implement a Feature

Use this prompt to implement the feature planned in `02-plan-feature.md`.

## Goal
Implement ONE backend feature following TDD and the UniPilot rules.

## Preconditions
- An approved plan exists (from prompt 02).
- You know the API contract, data model, and required tests.

## Instructions (TDD)
1. Write the failing tests first (RED) — start with unit, then integration.
2. Implement the minimal code to pass (GREEN).
3. Refactor for clarity and small files (IMPROVE), keep tests green.
4. Wire the feature into the correct container:
   - Request handling in `api` only.
   - Long AI work in `worker` via the Redis queue.
   - Model calls in the internal `ai` service.
5. Enforce security inline:
   - Protect student endpoints with JWT middleware + ownership checks.
   - Hash passwords with bcrypt; never return hashes.
   - Validate every request body with a schema.
   - Apply rate limiting to auth/AI endpoints (Redis-backed).
6. Persist data in MongoDB using the repository pattern; use immutable update patterns.
7. Handle errors explicitly; never leak secrets/stack traces to clients.

## After Coding
- Run lints and fix issues you introduced.
- Run the test suite; confirm it passes and coverage stays ≥ 80%.
- Update README if run/test commands changed.

## Constraints
- Backend-first; do not over-build the UI.
- No secrets in code; load from environment, provide `.env.example`.
- Keep files focused (200–400 lines typical, 800 max).
