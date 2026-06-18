# Playbook — Feature Development

## When to Use
Whenever building a new UniPilot AI feature from the backlog. One feature at a time, backend-first.

## Team Involved
Architect → Backend Engineer / AI Engineer → QA Engineer → Security Engineer → DevOps Engineer → Documentation Engineer.

## Workflow
1. **Select** one feature from `docs/planning/FEATURE_BACKLOG.md` matching the current phase.
2. **Explore** (prompt `01-explore-repo.md`) — confirm current state and gaps. Read-only.
3. **Design** (Architect, prompt `02-plan-feature.md`): API contract, data model + indexes, async flow, validation, auth/ownership, rate-limit needs, test plan. Record an ADR if architectural.
4. **Implement TDD** (Backend/AI Engineer, prompt `03-implement-feature.md`):
   - Write failing tests first (RED).
   - Minimal implementation (GREEN); refactor (IMPROVE).
   - `api` handles requests; long AI work enqueued to Redis → `worker` → internal `ai` service.
   - MongoDB persistence via repository pattern; immutable updates.
5. **Test** (QA, prompt `04-write-tests.md`): unit, integration, E2E, stress, security; coverage ≥ 80%.
6. **Security review** (Security Engineer, prompt `05-security-review.md`).
7. **Docker check** (DevOps, prompt `06-docker-check.md`).
8. **Docs** (Documentation Engineer, prompt `07-readme-update.md`).
9. **Commit** following `.cursor/rules/unipilot-git-workflow.mdc` (conventional message; ensure all members contribute over time).

## Required Checks
- [ ] Backend-first; matches current phase.
- [ ] API contract + validation on all inputs.
- [ ] JWT + ownership on student endpoints.
- [ ] Rate limiting on auth/AI endpoints.
- [ ] Long AI work async via Redis + worker; AI service internal only.
- [ ] Persistent data in MongoDB.
- [ ] bcrypt for passwords; no plaintext; no secrets in code.
- [ ] All five test types; coverage ≥ 80%.
- [ ] Docker clean-run still works; only API exposed.
- [ ] README updated.

## Final Deliverables
- Feature code (backend) merged behind passing tests.
- Updated tests + coverage report.
- Passing security review + Docker readiness.
- Updated README and (if applicable) ADR.
- Conventional commit(s) pushed.
