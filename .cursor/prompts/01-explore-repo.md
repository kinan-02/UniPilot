# Prompt 01 — Explore the Repository

Use this prompt at the start of a session or when onboarding to UniPilot AI.

## Goal
Build an accurate mental model of the current state of the repo before changing anything.

## Instructions
1. Read the project rules first: all files in `.cursor/rules/unipilot-*.mdc`.
2. Read planning docs: `docs/planning/IMPLEMENTATION_PHASES.md` and `docs/planning/FEATURE_BACKLOG.md`.
3. Read architecture: `docs/architecture/ARCHITECTURE.md`.
4. Map the actual code against the intended architecture:
   - Backend containers present (api, worker, ai)?
   - `docker-compose.yml` services and which ports are exposed?
   - MongoDB + Redis wiring?
   - Auth (JWT), password hashing (bcrypt), rate limiting?
   - Async AI job flow (queue, worker, status endpoint)?
5. Identify what exists, what is stubbed, and what is missing.
6. Check test coverage: which of unit / integration / E2E / stress / security exist.

## Output
Produce a short report:
- **Current state**: implemented features and containers.
- **Gaps**: missing pieces vs. the backlog and rules.
- **Risks/blockers**: anything that would break Docker first-run.
- **Recommended next feature** to pick from `FEATURE_BACKLOG.md`.

## Constraints
- Read-only. Do not modify code in this step.
- Prefer search/read tools over guessing.
